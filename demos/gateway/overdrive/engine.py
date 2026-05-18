"""StarGate Overdrive Lite — Lane Evaluation Engine."""

import uuid
from datetime import datetime, timezone
from pathlib import Path

from .models import InferenceRequest, Route, Check, Decision
from .matrix import load_config, match_lane, get_fallback
from .rubric import load_rubrics, evaluate_route, route_passes


class OverdriveEngine:
    def __init__(self, config_path: Path, rubric_dir: Path):
        self.config = load_config(config_path)
        self.rubrics = load_rubrics(rubric_dir)
        self.routes = self._build_routes()

    def _build_routes(self) -> dict:
        routes = {}
        for lane_id, lane_cfg in self.config["lanes"].items():
            routes[lane_id] = Route(
                route_id=lane_id,
                lane=lane_id,
                target_endpoint=lane_cfg["target_endpoint"],
                capabilities=lane_cfg["capabilities"],
                max_token_estimate=lane_cfg["max_token_estimate"],
                healthy=True,
                model=lane_cfg.get("model", ""),
                accelerator=lane_cfg.get("accelerator", ""),
            )
        return routes

    def evaluate(self, request: InferenceRequest) -> Decision:
        all_checks = []
        evaluated = []
        reason_codes = []

        # 1. Match lane from routing matrix
        target_lane = match_lane(
            request.task_type, request.token_estimate,
            request.priority, request.latency_target_ms, self.config,
        )

        if target_lane is None:
            known_tasks = set()
            for rule in self.config.get("routing_matrix", []):
                known_tasks.add(rule.get("task_type", ""))
            if request.task_type in known_tasks:
                reasons = [
                    f"task_{request.task_type}_no_matching_rule",
                    f"token_estimate_{request.token_estimate}",
                    f"priority_{request.priority}",
                ]
            else:
                reasons = ["unknown_task_type", f"task_{request.task_type}_not_in_matrix"]
            return Decision(
                decision_id=f"dec-{uuid.uuid4().hex[:8]}",
                request_id=request.request_id,
                outcome="indeterminate",
                selected_route=None,
                evaluated_routes=list(self.routes.keys()),
                checks=all_checks,
                reason_codes=reasons,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

        # 2. Try the target lane — run full rubric evaluation
        route = self.routes.get(target_lane)
        if route:
            evaluated.append(target_lane)
            rubric = self.rubrics.get(target_lane, {})
            checks = evaluate_route(request, route, rubric)
            all_checks.extend(checks)

            if route_passes(checks):
                reason_codes.append(f"task_type_{request.task_type}")
                reason_codes.append(f"{target_lane}_ready")
                return Decision(
                    decision_id=f"dec-{uuid.uuid4().hex[:8]}",
                    request_id=request.request_id,
                    outcome="route",
                    selected_route=target_lane,
                    evaluated_routes=evaluated,
                    checks=all_checks,
                    reason_codes=reason_codes,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
            reason_codes.append(f"{target_lane}_failed")

        # 3. Try fallback — only require the fallback route to be healthy
        fallback_lane = get_fallback(
            target_lane, request.task_type, request.token_estimate, self.config,
        )
        if fallback_lane:
            fb_route = self.routes.get(fallback_lane)
            if fb_route:
                evaluated.append(fallback_lane)
                # For fallback, only check health — the request may exceed
                # normal rubric limits, but a degraded route is better than
                # no route at all.
                health_check = Check(
                    name="endpoint_health_pass",
                    route=fb_route.route_id,
                    result="pass" if fb_route.healthy else "fail",
                    reason=None if fb_route.healthy else "endpoint health check failed",
                )
                all_checks.append(health_check)

                if fb_route.healthy:
                    reason_codes.append(f"fallback_to_{fallback_lane}")
                    reason_codes.append(f"{target_lane}_unhealthy")
                    return Decision(
                        decision_id=f"dec-{uuid.uuid4().hex[:8]}",
                        request_id=request.request_id,
                        outcome="fallback",
                        selected_route=fallback_lane,
                        evaluated_routes=evaluated,
                        checks=all_checks,
                        reason_codes=reason_codes,
                        timestamp=datetime.now(timezone.utc).isoformat(),
                    )
                reason_codes.append(f"{fallback_lane}_failed")

        # 4. Nothing worked
        return Decision(
            decision_id=f"dec-{uuid.uuid4().hex[:8]}",
            request_id=request.request_id,
            outcome="queue",
            selected_route=None,
            evaluated_routes=evaluated,
            checks=all_checks,
            reason_codes=reason_codes + ["no_viable_route"],
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def set_route_health(self, route_id: str, healthy: bool):
        if route_id in self.routes:
            self.routes[route_id].healthy = healthy

    def get_route_state(self) -> dict:
        return {
            rid: {
                "healthy": r.healthy,
                "load": r.current_load,
                "endpoint": r.target_endpoint,
                "model": r.model,
                "accelerator": r.accelerator,
                "capabilities": r.capabilities,
            }
            for rid, r in self.routes.items()
        }
