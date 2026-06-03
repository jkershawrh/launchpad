from __future__ import annotations

import logging
from typing import List, Optional

from app.domain.models import CatalogItem, LabRequest
from app.domain.orchestration import (
    DeepFieldSignal,
    HealthAlert,
    OrchestrationDecision,
    RebalanceAction,
)
from app.domain.placement import ClusterCapacity

logger = logging.getLogger("launchpad.orchestration_brain")


class OrchestrationBrain:

    def __init__(
        self,
        classifier=None,
        placement=None,
        feedback_tracker=None,
        deepfield=None,
    ):
        self.classifier = classifier
        self.placement = placement
        self.feedback_tracker = feedback_tracker
        self.deepfield = deepfield

    def decide(
        self, request: LabRequest, catalog_item: CatalogItem,
    ) -> OrchestrationDecision:
        signals_used = []
        confidence_factors = []

        workload_profile = None
        hw = catalog_item.default_hardware_profile or "xeon-basic"
        qp = catalog_item.default_quota_profile or "standard"

        if self.classifier:
            try:
                workload_profile = self.classifier.classify(catalog_item, request)
                matches = self.classifier.match_hardware(workload_profile)
                if matches:
                    hw = matches[0].hardware_profile
                    qp = matches[0].right_sized_quota or qp
                signals_used.append("workload_classification")
                confidence_factors.append(workload_profile.confidence)
            except Exception as e:
                logger.debug("Workload classification failed: %s", e)

        cluster = None
        fallback_chain = []

        if self.placement and self.placement._cache_is_valid():
            try:
                candidates = list(self.placement._capacity_cache.values())

                deepfield_penalties = {}
                if self.deepfield:
                    try:
                        fleet = self.deepfield.get_fleet_overview()
                        if fleet:
                            signals_used.append("deepfield_metrics")
                            confidence_factors.append(0.7)
                            for cname, sigs in fleet.items():
                                critical_count = sum(1 for s in sigs if s.status == "critical")
                                if critical_count > 0:
                                    deepfield_penalties[cname] = 0.3 * critical_count
                    except Exception as e:
                        logger.debug("DeepField fleet overview failed: %s", e)

                scored = []
                for c in candidates:
                    if c.health_status != "healthy":
                        continue
                    score = c.score
                    if c.cluster_name in deepfield_penalties:
                        score *= max(0.1, 1.0 - deepfield_penalties[c.cluster_name])

                    if self.feedback_tracker:
                        if self.feedback_tracker.should_avoid(
                            catalog_item.catalog_item_id, c.cluster_name, hw,
                        ):
                            continue
                        summary = self.feedback_tracker.get_summary(
                            catalog_item.catalog_item_id, c.cluster_name, hw,
                        )
                        if summary and summary.total_attempts >= 5:
                            score *= summary.success_rate
                            if "feedback_history" not in signals_used:
                                signals_used.append("feedback_history")
                                confidence_factors.append(summary.confidence)

                    scored.append((c.cluster_name, score))

                scored.sort(key=lambda x: -x[1])
                if scored:
                    cluster = scored[0][0]
                    fallback_chain = [name for name, _ in scored[1:3]]
                    signals_used.append("stargate_capacity")
                    confidence_factors.append(0.8)
            except Exception as e:
                logger.debug("Placement decision failed: %s", e)
        elif self.feedback_tracker:
            rankings = self.feedback_tracker.get_cluster_rankings(
                catalog_item.catalog_item_id, hw,
            )
            if rankings:
                cluster = rankings[0].cluster_name
                fallback_chain = [r.cluster_name for r in rankings[1:3]]
                signals_used.append("feedback_history")
                confidence_factors.append(rankings[0].confidence)

        if confidence_factors:
            avg_confidence = sum(confidence_factors) / len(confidence_factors)
            diversity = len(signals_used)
            if diversity <= 1:
                confidence = avg_confidence * 0.4
            elif diversity == 2:
                confidence = avg_confidence * 0.7
            else:
                confidence = min(1.0, avg_confidence * 0.8 + 0.1)
        else:
            confidence = 0.2

        rationale_parts = []
        if "workload_classification" in signals_used:
            rationale_parts.append(f"workload classified as {workload_profile.workload_type.value}")
        if cluster:
            rationale_parts.append(f"cluster {cluster} selected")
        rationale_parts.append(f"hardware {hw}, quota {qp}")
        if "deepfield_metrics" in signals_used:
            rationale_parts.append("DeepField fleet signals incorporated")
        if "feedback_history" in signals_used:
            rationale_parts.append("historical outcomes considered")
        rationale = "; ".join(rationale_parts)

        return OrchestrationDecision(
            request_id=request.request_id,
            workload_profile=workload_profile,
            recommended_cluster=cluster,
            recommended_hardware=hw,
            recommended_quota=qp,
            confidence=confidence,
            rationale=rationale,
            signals_used=signals_used,
            fallback_chain=fallback_chain,
        )

    def proactive_health_check(self) -> List[HealthAlert]:
        if not self.deepfield:
            return []

        alerts = []
        try:
            fleet = self.deepfield.get_fleet_overview()
            for cluster_name, signals in fleet.items():
                critical_signals = [s for s in signals if s.status == "critical"]
                if critical_signals:
                    alerts.append(HealthAlert(
                        cluster_name=cluster_name,
                        alert_type="critical_signals_detected",
                        severity="critical",
                        recommended_action=f"investigate {len(critical_signals)} critical signal(s)",
                        signals=critical_signals,
                    ))
        except Exception as e:
            logger.debug("Proactive health check failed: %s", e)

        return alerts

    def rebalance_check(self) -> List[RebalanceAction]:
        return []
