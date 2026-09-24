"""Read-only trusted-TLS preflight for Flightpath Launchpad browser routes."""

from __future__ import annotations

import argparse
import json
import socket
import ssl
from collections.abc import Callable
from datetime import UTC, datetime

DEFAULT_HOSTS = (
    "launchpad-candidate.apps.flightpath.fm2aihpcsed.com",
    "launchpad-admin-candidate.apps.flightpath.fm2aihpcsed.com",
    "launchpad-api-candidate.apps.flightpath.fm2aihpcsed.com",
)


def _probe_host(host: str, timeout: float = 10) -> dict:
    result = {"host": host, "trusted": False, "http_status": None}
    try:
        context = ssl.create_default_context()
        with (
            socket.create_connection((host, 443), timeout=timeout) as connection,
            context.wrap_socket(connection, server_hostname=host) as tls,
        ):
            certificate = tls.getpeercert()
            not_after = certificate.get("notAfter", "")
            expires_at = datetime.fromtimestamp(
                ssl.cert_time_to_seconds(not_after), tz=UTC
            )
            result.update(
                {
                    "trusted": True,
                    "expires_at": expires_at.isoformat(),
                    "valid_for_days": int(
                        (expires_at - datetime.now(UTC)).total_seconds() // 86400
                    ),
                }
            )
            request = (
                f"HEAD / HTTP/1.1\r\nHost: {host}\r\n"
                "Connection: close\r\nUser-Agent: launchpad-tls-preflight/1\r\n\r\n"
            )
            tls.sendall(request.encode("ascii"))
            status_line = tls.recv(256).split(b"\r\n", 1)[0].decode("ascii", "replace")
            parts = status_line.split()
            if len(parts) >= 2 and parts[1].isdigit():
                result["http_status"] = int(parts[1])
    except ssl.SSLCertVerificationError:
        result["failure"] = "certificate-verification-failed"
    except socket.gaierror:
        result["failure"] = "dns-resolution-failed"
    except TimeoutError:
        result["failure"] = "connection-timeout"
    except OSError:
        result["failure"] = "connection-failed"
    return result


def evaluate(
    hosts: tuple[str, ...] = DEFAULT_HOSTS,
    min_validity_days: int = 30,
    prober: Callable[[str], dict] = _probe_host,
) -> dict:
    results = []
    for host in hosts:
        check = prober(host)
        check["passed"] = (
            check.get("trusted") is True
            and check.get("valid_for_days", -1) >= min_validity_days
            and isinstance(check.get("http_status"), int)
            and 200 <= check["http_status"] < 500
        )
        results.append(check)
    return {
        "schema_version": "launchpad.redhat.com/browser-tls-preflight/v1",
        "mutates_cluster": False,
        "minimum_validity_days": min_validity_days,
        "passed": bool(results) and all(item["passed"] for item in results),
        "hosts": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", action="append", dest="hosts")
    parser.add_argument("--minimum-validity-days", type=int, default=30)
    args = parser.parse_args()
    report = evaluate(
        tuple(args.hosts) if args.hosts else DEFAULT_HOSTS,
        args.minimum_validity_days,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
