import time
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
from jose import jwk, jwt
import pytest

from app.api.v1 import dependencies as deps
from app.business_time import business_today
from app.config import settings
from app.models import Event
from tests.conftest import (
    TEST_KID,
    TEST_SUPABASE_URL,
    _TEST_PRIVATE_PEM,
    _TEST_PUBLIC_JWK,
    auth_headers,
    make_test_token,
)


USER_A_UUID = "d3b07384-d9a0-4c8b-a123-123456789abc"
USER_B_UUID = "e4c18495-e0b1-5d9c-b234-234567890def"

DERIVED_BIZ_A = f"biz_{USER_A_UUID}"
DERIVED_BIZ_B = f"biz_{USER_B_UUID}"


def test_valid_es256_jwt_succeeds_on_events_and_query(client):
    today = business_today().isoformat()
    token = make_test_token(sub=USER_A_UUID)
    headers = {"Authorization": f"Bearer {token}"}

    # Record event
    response = client.post(
        "/api/v1/events",
        headers=headers,
        json={
            "business_id": "ignored",
            "language": "en",
            "event_type": "sale",
            "data": {"item": "hat", "quantity": 1, "amount": 250, "currency": "ETB", "date": today},
        },
    )
    assert response.status_code == 201
    assert response.json()["success"] is True

    # Query
    q_resp = client.post(
        "/api/v1/query",
        headers=headers,
        json={"business_id": "ignored", "language": "en", "query": "How much did I sell today?"},
    )
    assert q_resp.status_code == 200
    assert q_resp.json()["success"] is True
    assert q_resp.json()["result"]["amount"] == 250


def test_missing_auth_header_is_rejected_on_events(client):
    response = client.post(
        "/api/v1/events",
        json={
            "business_id": "business_123",
            "language": "en",
            "event_type": "sale",
            "data": {"item": "shirts", "quantity": 1, "amount": 100},
        },
    )
    assert response.status_code == 401
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "UNAUTHORIZED"
    assert "Authorization header is required" in body["error"]["message"]


def test_missing_auth_header_is_rejected_on_query(client):
    response = client.post(
        "/api/v1/query",
        json={
            "business_id": "business_123",
            "language": "en",
            "query": "How much did I sell today?",
        },
    )
    assert response.status_code == 401
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "UNAUTHORIZED"
    assert "Authorization header is required" in body["error"]["message"]


def test_malformed_auth_header_is_rejected(client):
    # Not Bearer format
    response = client.post(
        "/api/v1/events",
        headers={"Authorization": "Basic 12345"},
        json={"business_id": "business_123", "language": "en", "event_type": "sale", "data": {}},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"

    # Bearer with empty token
    response2 = client.post(
        "/api/v1/query",
        headers={"Authorization": "Bearer "},
        json={"business_id": "business_123", "language": "en", "query": "How much did I sell today?"},
    )
    assert response2.status_code == 401
    assert response2.json()["error"]["code"] == "UNAUTHORIZED"


def test_invalid_jwt_signature_is_rejected(client):
    # Generate a different EC key that is not in the JWKS
    other_key = ec.generate_private_key(ec.SECP256R1())
    other_pem = other_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()

    # Sign with other key but claim to be TEST_KID
    bad_token = make_test_token(sub=USER_A_UUID, private_key_pem=other_pem, kid=TEST_KID)
    response = client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {bad_token}"},
        json={
            "business_id": "business_123",
            "language": "en",
            "event_type": "sale",
            "data": {"item": "shirts", "quantity": 1, "amount": 100},
        },
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_malformed_jwt_is_rejected(client):
    response = client.post(
        "/api/v1/query",
        headers={"Authorization": "Bearer invalid.token.value"},
        json={"business_id": "business_123", "language": "en", "query": "How much did I sell today?"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_expired_jwt_is_rejected(client):
    past_exp = int(time.time()) - 3600
    expired_token = make_test_token(sub=USER_A_UUID, exp=past_exp)
    response = client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {expired_token}"},
        json={
            "business_id": "business_123",
            "language": "en",
            "event_type": "sale",
            "data": {"item": "shirts", "quantity": 1, "amount": 100},
        },
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_wrong_issuer_is_rejected(client):
    token = make_test_token(sub=USER_A_UUID, iss="https://other-project.supabase.co/auth/v1")
    response = client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "business_id": "business_123",
            "language": "en",
            "event_type": "sale",
            "data": {"item": "shirts", "quantity": 1, "amount": 100},
        },
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_token_missing_sub_claim_is_rejected(client):
    payload = {
        "aud": "authenticated",
        "iss": f"{TEST_SUPABASE_URL}/auth/v1",
        "role": "authenticated",
        "exp": 9999999999,
    }
    token_without_sub = jwt.encode(payload, _TEST_PRIVATE_PEM, algorithm="ES256", headers={"kid": TEST_KID})
    response = client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {token_without_sub}"},
        json={
            "business_id": "business_123",
            "language": "en",
            "event_type": "sale",
            "data": {"item": "shirts", "quantity": 1, "amount": 100},
        },
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_token_invalid_sub_claim_is_rejected(client):
    # Empty string sub
    empty_sub_token = make_test_token(sub="   ")
    response = client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {empty_sub_token}"},
        json={"business_id": "business_123", "language": "en", "event_type": "sale", "data": {}},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_unknown_kid_is_rejected(client):
    token = make_test_token(sub=USER_A_UUID, kid="unknown-kid-999")
    response = client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "business_id": "business_123",
            "language": "en",
            "event_type": "sale",
            "data": {"item": "shirts", "quantity": 1, "amount": 100},
        },
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_jwks_failure_fails_closed(client):
    deps.jwks_cache.clear()
    original_fetch = deps.fetch_jwks
    try:
        def failing_fetch(_url):
            raise RuntimeError("JWKS connection timeout")

        deps.fetch_jwks = failing_fetch
        token = make_test_token(sub=USER_A_UUID)
        response = client.post(
            "/api/v1/events",
            headers={"Authorization": f"Bearer {token}"},
            json={"business_id": "business_123", "language": "en", "event_type": "sale", "data": {}},
        )
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "UNAUTHORIZED"
    finally:
        deps.fetch_jwks = original_fetch
        deps.jwks_cache.clear()


def test_unconfigured_supabase_url_fails_closed(client):
    orig_url = settings.supabase_url
    try:
        settings.supabase_url = ""
        token = make_test_token(sub=USER_A_UUID)
        response = client.post(
            "/api/v1/events",
            headers={"Authorization": f"Bearer {token}"},
            json={"business_id": "business_123", "language": "en", "event_type": "sale", "data": {}},
        )
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "UNAUTHORIZED"
    finally:
        settings.supabase_url = orig_url


def test_jwks_key_rotation_handles_new_kid(client):
    deps.jwks_cache.clear()

    # Key 2
    key2 = ec.generate_private_key(ec.SECP256R1())
    key2_pem = key2.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    key2_jwk = jwk.construct(key2.public_key(), algorithm="ES256").to_dict()
    key2_jwk["kid"] = "rotated-key-id-2"
    key2_jwk["use"] = "sig"
    key2_jwk["alg"] = "ES256"

    # Multi-key JWKS
    rotated_jwks = {"keys": [_TEST_PUBLIC_JWK, key2_jwk]}
    original_fetch = deps.fetch_jwks
    try:
        deps.fetch_jwks = lambda _url: rotated_jwks
        token2 = make_test_token(sub=USER_A_UUID, private_key_pem=key2_pem, kid="rotated-key-id-2")
        response = client.post(
            "/api/v1/events",
            headers={"Authorization": f"Bearer {token2}"},
            json={
                "business_id": "business_123",
                "language": "en",
                "event_type": "sale",
                "data": {"item": "shirts", "quantity": 1, "amount": 100},
            },
        )
        assert response.status_code == 201
    finally:
        deps.fetch_jwks = original_fetch
        deps.jwks_cache.clear()


def test_client_business_id_in_request_body_is_ignored_and_overridden(client, session_factory):
    response = client.post(
        "/api/v1/events",
        headers=auth_headers(USER_A_UUID),
        json={
            "business_id": "biz_some_other_user",
            "language": "en",
            "event_type": "sale",
            "data": {
                "item": "shirts",
                "quantity": 2,
                "amount": 500,
                "currency": "ETB",
                "date": business_today().isoformat(),
            },
        },
    )
    assert response.status_code == 201
    event_id = response.json()["event"]["id"]

    db = session_factory()
    try:
        stored = db.get(Event, event_id)
        assert stored is not None
        assert stored.business_id == DERIVED_BIZ_A
        assert stored.business_id != "biz_some_other_user"
    finally:
        db.close()


def test_user_data_isolation_between_user_a_and_user_b(client):
    today = business_today().isoformat()

    # User A records a sale of 1000 ETB
    resp_a = client.post(
        "/api/v1/events",
        headers=auth_headers(USER_A_UUID),
        json={
            "business_id": "arbitrary_body_id_ignored",
            "language": "en",
            "event_type": "sale",
            "data": {
                "item": "shoes",
                "quantity": 1,
                "amount": 1000,
                "currency": "ETB",
                "date": today,
            },
        },
    )
    assert resp_a.status_code == 201

    # User B records a sale of 250 ETB
    resp_b = client.post(
        "/api/v1/events",
        headers=auth_headers(USER_B_UUID),
        json={
            "business_id": "arbitrary_body_id_ignored",
            "language": "en",
            "event_type": "sale",
            "data": {
                "item": "shoes",
                "quantity": 1,
                "amount": 250,
                "currency": "ETB",
                "date": today,
            },
        },
    )
    assert resp_b.status_code == 201

    # 1. User A query only sees User A's total (1000 ETB)
    query_a = client.post(
        "/api/v1/query",
        headers=auth_headers(USER_A_UUID),
        json={
            "business_id": "arbitrary_id",
            "language": "en",
            "query": "How much did I sell today?",
        },
    )
    assert query_a.status_code == 200
    assert query_a.json()["result"]["amount"] == 1000

    # 2. User B query only sees User B's total (250 ETB)
    query_b = client.post(
        "/api/v1/query",
        headers=auth_headers(USER_B_UUID),
        json={
            "business_id": "arbitrary_id",
            "language": "en",
            "query": "How much did I sell today?",
        },
    )
    assert query_b.status_code == 200
    assert query_b.json()["result"]["amount"] == 250

    # 3. User A attempts to query User B's data by putting User B's business_id in request body
    query_a_spoof = client.post(
        "/api/v1/query",
        headers=auth_headers(USER_A_UUID),
        json={
            "business_id": DERIVED_BIZ_B,
            "language": "en",
            "query": "How much did I sell today?",
        },
    )
    assert query_a_spoof.status_code == 200
    assert query_a_spoof.json()["result"]["amount"] == 1000

    # 4. User B attempts to query User A's data by putting User A's business_id in request body
    query_b_spoof = client.post(
        "/api/v1/query",
        headers=auth_headers(USER_B_UUID),
        json={
            "business_id": DERIVED_BIZ_A,
            "language": "en",
            "query": "How much did I sell today?",
        },
    )
    assert query_b_spoof.status_code == 200
    assert query_b_spoof.json()["result"]["amount"] == 250


def test_unsupported_algorithm_is_rejected(client):
    # 1. HS256 algorithm token
    hs256_token = jwt.encode(
        {"sub": USER_A_UUID, "iss": f"{TEST_SUPABASE_URL}/auth/v1", "exp": 9999999999},
        "some-symmetric-secret-key-12345678",
        algorithm="HS256",
        headers={"kid": TEST_KID},
    )
    resp_hs256 = client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {hs256_token}"},
        json={"business_id": "business_123", "language": "en", "event_type": "sale", "data": {}},
    )
    assert resp_hs256.status_code == 401
    assert resp_hs256.json()["error"]["code"] == "UNAUTHORIZED"

    # 2. 'none' algorithm token
    none_token = "eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0.eyJzdWIiOiJ1c2VyMSJ9."
    resp_none = client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {none_token}"},
        json={"business_id": "business_123", "language": "en", "event_type": "sale", "data": {}},
    )
    assert resp_none.status_code == 401
    assert resp_none.json()["error"]["code"] == "UNAUTHORIZED"


def test_token_missing_kid_header_is_rejected(client):
    payload = {
        "sub": USER_A_UUID,
        "aud": "authenticated",
        "iss": f"{TEST_SUPABASE_URL}/auth/v1",
        "role": "authenticated",
        "exp": 9999999999,
    }
    # Encode with ES256 but omit kid header
    token_no_kid = jwt.encode(payload, _TEST_PRIVATE_PEM, algorithm="ES256")
    response = client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {token_no_kid}"},
        json={"business_id": "business_123", "language": "en", "event_type": "sale", "data": {}},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_malformed_key_in_jwks_fails_closed(client):
    deps.jwks_cache.clear()
    original_fetch = deps.fetch_jwks
    try:
        # Invalid point coordinate that will cause ValueError in jwk.construct
        malformed_jwk = {
            "kty": "EC",
            "crv": "P-256",
            "alg": "ES256",
            "kid": "malformed-point-key",
            "x": "invalid_base64_or_point",
            "y": "invalid_base64_or_point",
        }
        deps.fetch_jwks = lambda _url: {"keys": [malformed_jwk]}
        token = make_test_token(sub=USER_A_UUID, kid="malformed-point-key")
        response = client.post(
            "/api/v1/events",
            headers={"Authorization": f"Bearer {token}"},
            json={"business_id": "business_123", "language": "en", "event_type": "sale", "data": {}},
        )
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "UNAUTHORIZED"
    finally:
        deps.fetch_jwks = original_fetch
        deps.jwks_cache.clear()


def test_invalid_jwks_structure_fails_closed(client):
    deps.jwks_cache.clear()
    original_fetch = deps.fetch_jwks
    try:
        # JWKS returns a list instead of dict {"keys": [...]}
        deps.fetch_jwks = lambda _url: [{"kty": "EC"}]
        token = make_test_token(sub=USER_A_UUID)
        response = client.post(
            "/api/v1/events",
            headers={"Authorization": f"Bearer {token}"},
            json={"business_id": "business_123", "language": "en", "event_type": "sale", "data": {}},
        )
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "UNAUTHORIZED"
    finally:
        deps.fetch_jwks = original_fetch
        deps.jwks_cache.clear()


def test_user_cannot_write_events_into_another_user_business(client, session_factory):
    today = business_today().isoformat()

    # User A submits an event attempting to write into User B's business by passing User B's business_id
    resp = client.post(
        "/api/v1/events",
        headers=auth_headers(USER_A_UUID),
        json={
            "business_id": DERIVED_BIZ_B,
            "language": "en",
            "event_type": "sale",
            "data": {
                "item": "watch",
                "quantity": 1,
                "amount": 5000,
                "currency": "ETB",
                "date": today,
            },
        },
    )
    assert resp.status_code == 201
    event_id = resp.json()["event"]["id"]

    # Verify directly in DB that event is tagged with User A's derived ID, NOT User B's
    db = session_factory()
    try:
        stored = db.get(Event, event_id)
        assert stored is not None
        assert stored.business_id == DERIVED_BIZ_A
        assert stored.business_id != DERIVED_BIZ_B
    finally:
        db.close()

    # Querying as User B must return 0 sales because User A's write went into User A's business
    query_b = client.post(
        "/api/v1/query",
        headers=auth_headers(USER_B_UUID),
        json={
            "business_id": DERIVED_BIZ_B,
            "language": "en",
            "query": "How much did I sell today?",
        },
    )
    assert query_b.status_code == 200
    assert query_b.json()["result"]["amount"] == 0

    # Querying as User A must return the 5000 ETB sale
    query_a = client.post(
        "/api/v1/query",
        headers=auth_headers(USER_A_UUID),
        json={
            "business_id": DERIVED_BIZ_A,
            "language": "en",
            "query": "How much did I sell today?",
        },
    )
    assert query_a.status_code == 200
    assert query_a.json()["result"]["amount"] == 5000

