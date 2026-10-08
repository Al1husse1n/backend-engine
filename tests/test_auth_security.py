import time
from sqlalchemy import select

from app.business_time import business_today
from app.models import Event
from tests.conftest import TEST_JWT_SECRET, auth_headers, make_test_token


USER_A_UUID = "d3b07384-d9a0-4c8b-a123-123456789abc"
USER_B_UUID = "e4c18495-e0b1-5d9c-b234-234567890def"

DERIVED_BIZ_A = f"biz_{USER_A_UUID}"
DERIVED_BIZ_B = f"biz_{USER_B_UUID}"


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
    bad_token = make_test_token(sub=USER_A_UUID, secret="wrong-secret-key-999")
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


def test_token_missing_sub_claim_is_rejected(client):
    from jose import jwt

    token_without_sub = jwt.encode(
        {"aud": "authenticated", "role": "authenticated", "exp": 9999999999},
        TEST_JWT_SECRET,
        algorithm="HS256",
    )
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


def test_client_business_id_in_request_body_is_ignored_and_overridden(client, session_factory):
    # User A sends request with spoofed/different business_id in body
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

    # Verify directly in the DB that the event is tagged with User A's derived ID, NOT the body ID
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
    # Still only returns User A's amount (1000), NOT User B's (250)
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
    # Still only returns User B's amount (250), NOT User A's (1000)
    assert query_b_spoof.json()["result"]["amount"] == 250
