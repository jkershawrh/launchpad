"""Minimal fail-closed OIDC access-token verification for workforce access.

The browser login is performed by oauth2-proxy.  Launchpad still verifies the
signed access token at the API boundary instead of trusting caller-controlled
forwarded identity headers.
"""
from __future__ import annotations

import base64
import json
import os
import threading
import time
from typing import Any

import requests
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa


class OIDCTokenError(ValueError):
    """Raised when an OIDC token cannot be authenticated."""


OIDC_ISSUER = os.environ.get("OIDC_ISSUER", "").rstrip("/") + (
    "/" if os.environ.get("OIDC_ISSUER", "") else ""
)
OIDC_JWKS_URL = os.environ.get("OIDC_JWKS_URL", "")
OIDC_AUDIENCES = set(filter(None, os.environ.get("OIDC_AUDIENCES", "").split(",")))
OIDC_CLOCK_SKEW_SECONDS = int(os.environ.get("OIDC_CLOCK_SKEW_SECONDS", "30"))
OIDC_JWKS_CACHE_SECONDS = int(os.environ.get("OIDC_JWKS_CACHE_SECONDS", "300"))

_jwks_cache: tuple[float, dict[str, Any]] | None = None
_jwks_lock = threading.Lock()


def _decode_segment(value: str) -> bytes:
    try:
        padding_length = (-len(value)) % 4
        return base64.urlsafe_b64decode(value + ("=" * padding_length))
    except (ValueError, TypeError) as exc:
        raise OIDCTokenError("malformed token encoding") from exc


def _load_jwks() -> dict[str, Any]:
    global _jwks_cache
    if not OIDC_JWKS_URL:
        raise OIDCTokenError("OIDC JWKS URL is not configured")

    now = time.monotonic()
    with _jwks_lock:
        if _jwks_cache and now - _jwks_cache[0] < OIDC_JWKS_CACHE_SECONDS:
            return _jwks_cache[1]
        try:
            response = requests.get(OIDC_JWKS_URL, timeout=5)
            response.raise_for_status()
            jwks = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise OIDCTokenError("OIDC signing keys are unavailable") from exc
        if not isinstance(jwks, dict) or not isinstance(jwks.get("keys"), list):
            raise OIDCTokenError("OIDC signing key response is invalid")
        _jwks_cache = (now, jwks)
        return jwks


def _json_segment(value: str, label: str) -> dict[str, Any]:
    try:
        decoded = json.loads(_decode_segment(value))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise OIDCTokenError(f"malformed token {label}") from exc
    if not isinstance(decoded, dict):
        raise OIDCTokenError(f"malformed token {label}")
    return decoded


def _select_signing_key(jwks: dict[str, Any], kid: str) -> dict[str, Any]:
    for key in jwks.get("keys", []):
        if (
            isinstance(key, dict)
            and key.get("kid") == kid
            and key.get("kty") == "RSA"
            and key.get("alg", "RS256") == "RS256"
            and key.get("use", "sig") == "sig"
        ):
            return key
    raise OIDCTokenError("token signing key is not trusted")


def _verify_signature(signing_input: bytes, signature: bytes, jwk: dict[str, Any]) -> None:
    try:
        modulus = int.from_bytes(_decode_segment(str(jwk["n"])), "big")
        exponent = int.from_bytes(_decode_segment(str(jwk["e"])), "big")
        public_key = rsa.RSAPublicNumbers(exponent, modulus).public_key()
        public_key.verify(signature, signing_input, padding.PKCS1v15(), hashes.SHA256())
    except (KeyError, ValueError, TypeError, InvalidSignature) as exc:
        raise OIDCTokenError("token signature verification failed") from exc


def _validate_claims(claims: dict[str, Any]) -> None:
    if not OIDC_ISSUER or not OIDC_AUDIENCES:
        raise OIDCTokenError("OIDC issuer and audience are not configured")
    if claims.get("iss") != OIDC_ISSUER:
        raise OIDCTokenError("token issuer is not trusted")

    audience = claims.get("aud")
    token_audiences = {audience} if isinstance(audience, str) else set(audience or [])
    if not token_audiences & OIDC_AUDIENCES:
        raise OIDCTokenError("token audience is not accepted")

    now = int(time.time())
    try:
        expires_at = int(claims["exp"])
    except (KeyError, TypeError, ValueError) as exc:
        raise OIDCTokenError("token expiration is missing or invalid") from exc
    if expires_at < now - OIDC_CLOCK_SKEW_SECONDS:
        raise OIDCTokenError("token has expired")

    for claim_name in ("nbf", "iat"):
        if claim_name in claims:
            try:
                claim_time = int(claims[claim_name])
            except (TypeError, ValueError) as exc:
                raise OIDCTokenError(f"token {claim_name} is invalid") from exc
            if claim_time > now + OIDC_CLOCK_SKEW_SECONDS:
                raise OIDCTokenError(f"token {claim_name} is in the future")

    if not isinstance(claims.get("sub"), str) or not claims["sub"].strip():
        raise OIDCTokenError("token subject is missing")


def verify_oidc_token(token: str) -> dict[str, Any]:
    """Verify an RS256 OIDC token and return its authenticated claims."""
    parts = token.split(".")
    if len(parts) != 3:
        raise OIDCTokenError("malformed token")
    header = _json_segment(parts[0], "header")
    claims = _json_segment(parts[1], "claims")
    if header.get("alg") != "RS256":
        raise OIDCTokenError("token algorithm is not accepted")
    kid = header.get("kid")
    if not isinstance(kid, str) or not kid:
        raise OIDCTokenError("token signing key identifier is missing")

    jwk = _select_signing_key(_load_jwks(), kid)
    _verify_signature(
        f"{parts[0]}.{parts[1]}".encode("ascii"),
        _decode_segment(parts[2]),
        jwk,
    )
    _validate_claims(claims)
    return claims
