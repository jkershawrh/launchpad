from __future__ import annotations

import json
import os
import subprocess
from typing import Any, Dict, List


PODMAN_BIN = "/opt/podman/bin/podman"
_PODMAN_AVAILABLE = os.path.isfile(PODMAN_BIN)


class SystemMonitor:
    def get_status(self) -> Dict[str, Any]:
        containers = self.list_containers()
        running = [c for c in containers if c["status"].startswith("Up")]
        return {
            "healthy": len(running) > 0,
            "containers": len(containers),
            "containers_running": len(running),
            "containers_list": containers,
        }

    def list_containers(self) -> List[Dict[str, Any]]:
        if not _PODMAN_AVAILABLE:
            return []
        result = subprocess.run(
            [PODMAN_BIN, "ps", "-a", "--format", "json"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return []
        try:
            raw = json.loads(result.stdout)
        except json.JSONDecodeError:
            return []
        containers = []
        for c in raw:
            name = c.get("Names", [""])[0] if isinstance(c.get("Names"), list) else c.get("Names", "")
            containers.append({
                "name": name,
                "image": c.get("Image", ""),
                "status": c.get("Status", c.get("State", "")),
                "ports": self._format_ports(c.get("Ports", [])),
                "uptime": c.get("Status", ""),
                "id": c.get("Id", "")[:12],
            })
        return containers

    def get_container_logs(self, container_name: str, lines: int = 100) -> Dict[str, Any]:
        if not _PODMAN_AVAILABLE:
            return {"name": container_name, "logs": "", "success": False}
        result = subprocess.run(
            [PODMAN_BIN, "logs", "--tail", str(lines), container_name],
            capture_output=True, text=True, timeout=15,
        )
        return {
            "name": container_name,
            "logs": result.stdout + result.stderr if result.returncode == 0 else f"Error: {result.stderr}",
            "success": result.returncode == 0,
        }

    def restart_container(self, container_name: str) -> Dict[str, Any]:
        if not _PODMAN_AVAILABLE:
            return {"name": container_name, "success": False, "message": "Podman not available"}
        result = subprocess.run(
            [PODMAN_BIN, "restart", container_name],
            capture_output=True, text=True, timeout=30,
        )
        return {
            "name": container_name,
            "success": result.returncode == 0,
            "message": "Restarted" if result.returncode == 0 else result.stderr.strip(),
        }

    def get_container_stats(self) -> List[Dict[str, Any]]:
        if not _PODMAN_AVAILABLE:
            return []
        result = subprocess.run(
            [PODMAN_BIN, "stats", "--no-stream", "--format", "json"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            return []
        try:
            raw = json.loads(result.stdout)
        except json.JSONDecodeError:
            return []
        stats = []
        for s in raw:
            stats.append({
                "name": s.get("Name", s.get("name", "")),
                "cpu_percent": s.get("CPU", s.get("cpu_percent", "0%")),
                "memory_usage": s.get("MemUsage", s.get("mem_usage", "")),
                "memory_percent": s.get("MemPerc", s.get("mem_percent", "0%")),
            })
        return stats

    def _format_ports(self, ports: Any) -> str:
        if isinstance(ports, str):
            return ports
        if isinstance(ports, list):
            parts = []
            for p in ports:
                if isinstance(p, dict):
                    host = p.get("hostPort", p.get("host_port", ""))
                    container = p.get("containerPort", p.get("container_port", ""))
                    if host and container:
                        parts.append(f"{host}->{container}")
                elif isinstance(p, str):
                    parts.append(p)
            return ", ".join(parts) if parts else ""
        return str(ports)
