#!/usr/bin/env python3
"""Fail-closed external DNS/TLS/HTTP certification probe."""
from __future__ import annotations

import argparse
import json
import socket
import ssl
import sys
import time
import urllib.request
from datetime import datetime, timezone


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--evidence", default="-")
    args = parser.parse_args()
    started = time.monotonic()
    evidence = {"id": "PA-DNS-001", "host": args.host, "timestamp": datetime.now(timezone.utc).isoformat(), "checks": {}}
    try:
        addresses = sorted({item[4][0] for item in socket.getaddrinfo(args.host, 443, type=socket.SOCK_STREAM)})
        evidence["checks"]["dns"] = {"pass": bool(addresses), "addresses": addresses}
        context = ssl.create_default_context()
        with socket.create_connection((args.host, 443), timeout=10) as raw:
            with context.wrap_socket(raw, server_hostname=args.host) as tls:
                certificate = tls.getpeercert()
                evidence["checks"]["tls"] = {"pass": True, "not_after": certificate.get("notAfter"), "subject_alt_names": certificate.get("subjectAltName", [])}
        with urllib.request.urlopen(f"https://{args.host}/health", timeout=10) as response:
            body = json.loads(response.read())
            evidence["checks"]["http"] = {"pass": response.status == 200 and body.get("service") == "public-access-gateway", "status": response.status}
    except Exception as exc:
        evidence["error"] = f"{type(exc).__name__}: {exc}"
    evidence["elapsed_ms"] = round((time.monotonic() - started) * 1000, 2)
    evidence["pass"] = all(item.get("pass") for item in evidence["checks"].values()) and len(evidence["checks"]) == 3
    rendered = json.dumps(evidence, indent=2, sort_keys=True)
    if args.evidence == "-": print(rendered)
    else:
        with open(args.evidence, "x", encoding="utf-8") as stream: stream.write(rendered + "\n")
    return 0 if evidence["pass"] else 1


if __name__ == "__main__": sys.exit(main())
