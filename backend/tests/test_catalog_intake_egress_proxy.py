from __future__ import annotations

import socket

from app import catalog_intake_egress_proxy as proxy


def test_proxy_allows_only_approved_https_hosts(monkeypatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("140.82.112.4", 443))
        ],
    )
    assert proxy._allowed_addresses("github.com", 443)
    assert proxy._allowed_addresses("api.github.com", 443)
    assert proxy._allowed_addresses("github.com", 80) == []
    assert proxy._allowed_addresses("example.com", 443) == []


def test_proxy_rejects_private_or_loopback_resolution(monkeypatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.8", 443)),
        ],
    )
    assert proxy._allowed_addresses("github.com", 443) == []
