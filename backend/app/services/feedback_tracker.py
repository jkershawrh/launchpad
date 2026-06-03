from __future__ import annotations

import logging
import math
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from app.domain.feedback import FeedbackSummary, ProvisioningOutcome

logger = logging.getLogger("launchpad.feedback_tracker")

MIN_SAMPLES_FOR_AVOID = 5
AVOID_THRESHOLD = 0.3
PREFERRED_THRESHOLD = 0.8


class FeedbackTracker:

    def __init__(self, db_store=None):
        self._outcomes: List[ProvisioningOutcome] = []
        self._db = db_store
        if self._db:
            try:
                self._outcomes = self._db.list_all()
            except Exception:
                pass

    def record_outcome(self, outcome: ProvisioningOutcome) -> None:
        self._outcomes.append(outcome)
        if self._db:
            try:
                self._db.save(outcome)
            except Exception as e:
                logger.debug("Failed to persist outcome: %s", e)

        if not outcome.success:
            self._check_tarsy_escalation(outcome)

    def get_outcomes(
        self,
        catalog_item_id: Optional[str] = None,
        cluster_name: Optional[str] = None,
    ) -> List[ProvisioningOutcome]:
        results = self._outcomes
        if catalog_item_id:
            results = [o for o in results if o.catalog_item_id == catalog_item_id]
        if cluster_name:
            results = [o for o in results if o.cluster_name == cluster_name]
        return results

    def get_summary(
        self,
        catalog_item_id: str,
        cluster_name: str,
        hardware_profile: str,
    ) -> Optional[FeedbackSummary]:
        matching = [
            o for o in self._outcomes
            if o.catalog_item_id == catalog_item_id
            and o.cluster_name == cluster_name
            and o.hardware_profile == hardware_profile
        ]
        if not matching:
            return None
        return self._compute_summary(catalog_item_id, cluster_name, hardware_profile, matching)

    def get_cluster_rankings(
        self, catalog_item_id: str, hardware_profile: str,
    ) -> List[FeedbackSummary]:
        by_cluster: Dict[str, List[ProvisioningOutcome]] = defaultdict(list)
        for o in self._outcomes:
            if o.catalog_item_id == catalog_item_id and o.hardware_profile == hardware_profile and o.cluster_name:
                by_cluster[o.cluster_name].append(o)

        summaries = [
            self._compute_summary(catalog_item_id, cluster, hardware_profile, outcomes)
            for cluster, outcomes in by_cluster.items()
        ]
        summaries.sort(key=lambda s: -s.success_rate)
        return summaries

    def get_hardware_rankings(self, catalog_item_id: str) -> List[FeedbackSummary]:
        by_hw: Dict[str, List[ProvisioningOutcome]] = defaultdict(list)
        for o in self._outcomes:
            if o.catalog_item_id == catalog_item_id:
                by_hw[o.hardware_profile].append(o)

        summaries = []
        for hw, outcomes in by_hw.items():
            clusters = {o.cluster_name or "unknown" for o in outcomes}
            cluster = next(iter(clusters))
            summaries.append(self._compute_summary(catalog_item_id, cluster, hw, outcomes))
        summaries.sort(key=lambda s: -s.success_rate)
        return summaries

    def should_avoid(
        self, catalog_item_id: str, cluster_name: str, hardware_profile: str,
    ) -> bool:
        summary = self.get_summary(catalog_item_id, cluster_name, hardware_profile)
        if not summary:
            return False
        if summary.total_attempts < MIN_SAMPLES_FOR_AVOID:
            return False
        return summary.success_rate < AVOID_THRESHOLD

    def _check_tarsy_escalation(self, outcome: ProvisioningOutcome) -> None:
        """Escalate to TARSy if provisioning is repeatedly failing."""
        try:
            from app.integrations.tarsy_escalation import (
                check_tarsy_escalation,
                escalate_provision_failure,
            )

            summary = self.get_summary(
                outcome.catalog_item_id,
                outcome.cluster_name or "",
                outcome.hardware_profile,
            )
            if not summary:
                return

            if check_tarsy_escalation(
                catalog_item_id=outcome.catalog_item_id,
                cluster_name=outcome.cluster_name or "",
                hardware_profile=outcome.hardware_profile,
                success_rate=summary.success_rate,
                total_attempts=summary.total_attempts,
            ):
                escalate_provision_failure(
                    session_id=outcome.session_id,
                    catalog_item_id=outcome.catalog_item_id,
                    cluster_name=outcome.cluster_name or "",
                    hardware_profile=outcome.hardware_profile,
                    error_summary=outcome.failure_reason or "Unknown failure",
                    feedback_summary=summary.model_dump(),
                )
        except Exception as e:
            logger.debug("TARSy escalation failed (non-critical): %s", e)

    def _compute_summary(
        self,
        catalog_item_id: str,
        cluster_name: str,
        hardware_profile: str,
        outcomes: List[ProvisioningOutcome],
    ) -> FeedbackSummary:
        total = len(outcomes)
        successes = sum(1 for o in outcomes if o.success)
        success_rate = successes / total if total > 0 else 0.0

        latencies = [o.provision_latency_ms for o in outcomes if o.provision_latency_ms > 0]
        avg_latency = sum(latencies) / len(latencies) if latencies else 0.0

        failures = [o for o in outcomes if not o.success and o.failure_reason]
        last_failure = failures[-1].failure_reason if failures else None

        confidence = min(1.0, math.log2(total + 1) / math.log2(21))

        if success_rate >= PREFERRED_THRESHOLD and total >= MIN_SAMPLES_FOR_AVOID:
            recommendation = "preferred"
        elif success_rate < AVOID_THRESHOLD and total >= MIN_SAMPLES_FOR_AVOID:
            recommendation = "avoid"
        else:
            recommendation = "acceptable"

        return FeedbackSummary(
            catalog_item_id=catalog_item_id,
            cluster_name=cluster_name,
            hardware_profile=hardware_profile,
            total_attempts=total,
            success_count=successes,
            success_rate=success_rate,
            avg_latency_ms=avg_latency,
            last_failure_reason=last_failure,
            confidence=confidence,
            recommendation=recommendation,
        )
