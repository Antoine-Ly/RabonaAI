import time
from uuid import UUID

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.auth import JWTVerifier
from app.core.errors import AppError, ErrorCode

SUB = "00000000-0000-0000-0000-0000000000aa"
ISSUER = "https://exemple.supabase.co/auth/v1"
KEY = ec.generate_private_key(ec.SECP256R1())
OTHER_KEY = ec.generate_private_key(ec.SECP256R1())


def make_token(key: ec.EllipticCurvePrivateKey = KEY, **overrides: object) -> str:
    now = int(time.time())
    claims = {"sub": SUB, "aud": "authenticated", "iss": ISSUER, "iat": now, "exp": now + 3600}
    claims |= overrides
    return jwt.encode({k: v for k, v in claims.items() if v is not None}, key, algorithm="ES256")


@pytest.fixture
def verifier() -> JWTVerifier:
    return JWTVerifier(
        lambda _token: KEY.public_key(), audience="authenticated", issuer=ISSUER, leeway_seconds=10
    )


def test_valid_token_returns_the_subject(verifier: JWTVerifier) -> None:
    assert verifier.verify(make_token()) == UUID(SUB)


def test_clock_skew_within_leeway_is_tolerated(verifier: JWTVerifier) -> None:
    assert verifier.verify(make_token(iat=int(time.time()) + 5))  # V3 : ≈ 2 s d'écart observé


@pytest.mark.parametrize(
    "overrides",
    [
        {"exp": int(time.time()) - 60},
        {"iat": int(time.time()) + 120},
        {"aud": "autre"},
        {"iss": "https://autre.supabase.co/auth/v1"},
        {"sub": None},
        {"sub": "pas-un-uuid"},
    ],
    ids=["expiré", "émis dans le futur", "audience", "émetteur", "sans sub", "sub invalide"],
)
def test_invalid_claims_are_refused(verifier: JWTVerifier, overrides: dict) -> None:
    with pytest.raises(AppError) as error:
        verifier.verify(make_token(**overrides))
    assert error.value.code is ErrorCode.UNAUTHORIZED


def test_wrong_signature_and_garbage_are_refused(verifier: JWTVerifier) -> None:
    for token in (make_token(OTHER_KEY), make_token()[:-4] + "AAAA", "nimporte.quoi.ici", ""):
        with pytest.raises(AppError) as error:
            verifier.verify(token)
        assert error.value.code is ErrorCode.UNAUTHORIZED


def test_symmetric_algorithm_is_refused(verifier: JWTVerifier) -> None:
    forged = jwt.encode(
        {"sub": SUB, "aud": "authenticated", "iss": ISSUER, "exp": int(time.time()) + 60},
        "x" * 40,
        algorithm="HS256",
    )
    with pytest.raises(AppError):
        verifier.verify(forged)


def test_route_requires_a_valid_bearer_token(app: FastAPI, verifier: JWTVerifier) -> None:
    app.state.auth = verifier
    client = TestClient(app)
    for headers in ({}, {"Authorization": "Bearer faux"}, {"Authorization": "Basic abc"}):
        response = client.get("/conversations", headers=headers)
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "unauthorized"
    assert client.get("/health").status_code == 200  # /health reste public
