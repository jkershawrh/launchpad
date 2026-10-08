import base64
import json
import time

import pytest
from app.auth import oidc
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _key_material():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_numbers = private_key.public_key().public_numbers()
    jwk = {
        "kty": "RSA",
        "kid": "test-key",
        "use": "sig",
        "alg": "RS256",
        "n": _b64url(public_numbers.n.to_bytes((public_numbers.n.bit_length() + 7) // 8, "big")),
        "e": _b64url(public_numbers.e.to_bytes((public_numbers.e.bit_length() + 7) // 8, "big")),
    }
    return private_key, {"keys": [jwk]}


def _token(private_key, claims: dict, *, kid: str = "test-key", alg: str = "RS256") -> str:
    header = _b64url(json.dumps({"alg": alg, "kid": kid, "typ": "JWT"}).encode())
    payload = _b64url(json.dumps(claims).encode())
    signing_input = f"{header}.{payload}".encode("ascii")
    signature = private_key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    return f"{header}.{payload}.{_b64url(signature)}"


def _claims(**overrides):
    now = int(time.time())
    value = {
        "iss": "https://auth.example.com/application/o/launchpad/",
        "aud": "launchpad-requester",
        "sub": "subject-123",
        "iat": now,
        "nbf": now - 1,
        "exp": now + 300,
    }
    value.update(overrides)
    return value


def test_verify_oidc_token_accepts_rs256_issuer_audience_and_subject(monkeypatch):
    private_key, jwks = _key_material()
    monkeypatch.setattr(oidc, "OIDC_ISSUER", "https://auth.example.com/application/o/launchpad/")
    monkeypatch.setattr(oidc, "OIDC_AUDIENCES", {"launchpad-requester", "launchpad-admin"})
    monkeypatch.setattr(oidc, "_load_jwks", lambda: jwks)

    claims = oidc.verify_oidc_token(_token(private_key, _claims()))

    assert claims["sub"] == "subject-123"


@pytest.mark.parametrize(
    ("claim_overrides", "message"),
    [
        ({"iss": "https://evil.example.com/"}, "issuer"),
        ({"aud": "another-client"}, "audience"),
        ({"exp": int(time.time()) - 60}, "expired"),
        ({"sub": ""}, "subject"),
    ],
)
def test_verify_oidc_token_rejects_invalid_security_claims(
    monkeypatch, claim_overrides, message
):
    private_key, jwks = _key_material()
    monkeypatch.setattr(oidc, "OIDC_ISSUER", "https://auth.example.com/application/o/launchpad/")
    monkeypatch.setattr(oidc, "OIDC_AUDIENCES", {"launchpad-requester"})
    monkeypatch.setattr(oidc, "_load_jwks", lambda: jwks)

    with pytest.raises(oidc.OIDCTokenError, match=message):
        oidc.verify_oidc_token(_token(private_key, _claims(**claim_overrides)))


def test_verify_oidc_token_rejects_unknown_key(monkeypatch):
    private_key, jwks = _key_material()
    monkeypatch.setattr(oidc, "OIDC_ISSUER", "https://auth.example.com/application/o/launchpad/")
    monkeypatch.setattr(oidc, "OIDC_AUDIENCES", {"launchpad-requester"})
    monkeypatch.setattr(oidc, "_load_jwks", lambda: jwks)

    with pytest.raises(oidc.OIDCTokenError, match="signing key"):
        oidc.verify_oidc_token(_token(private_key, _claims(), kid="unknown"))


def test_verify_oidc_token_rejects_non_rs256_algorithm(monkeypatch):
    private_key, jwks = _key_material()
    monkeypatch.setattr(oidc, "OIDC_ISSUER", "https://auth.example.com/application/o/launchpad/")
    monkeypatch.setattr(oidc, "OIDC_AUDIENCES", {"launchpad-requester"})
    monkeypatch.setattr(oidc, "_load_jwks", lambda: jwks)

    with pytest.raises(oidc.OIDCTokenError, match="algorithm"):
        oidc.verify_oidc_token(_token(private_key, _claims(), alg="none"))
