from sqlalchemy import func, select

from app.models import Event


def post_event(client, payload):
    return client.post("/api/v1/events", json=payload)


def event_count(session_factory) -> int:
    db = session_factory()
    try:
        return db.scalar(select(func.count()).select_from(Event)) or 0
    finally:
        db.close()


def load_event(session_factory, event_id: str) -> Event | None:
    db = session_factory()
    try:
        return db.get(Event, event_id)
    finally:
        db.close()


SALE = {
    "business_id": "business_123",
    "language": "en",
    "event_type": "sale",
    "data": {
        "item": "shirts",
        "quantity": 3,
        "amount": 900,
        "currency": "ETB",
        "customer": None,
        "date": "2026-09-17",
    },
}


def test_valid_sale_is_persisted(client, session_factory):
    response = post_event(client, SALE)
    assert response.status_code == 201
    body = response.json()
    assert body["success"] is True
    assert body["event"]["event_type"] == "sale"
    assert body["event"]["id"].startswith("event_")
    assert body["event"]["data"]["item"] == "shirts"
    assert body["event"]["data"]["quantity"] == 3
    assert body["event"]["data"]["amount"] == 900
    assert body["event"]["data"]["currency"] == "ETB"
    assert body["event"]["data"]["date"] == "2026-09-17"
    assert "Sale recorded successfully" in body["message"]

    stored = load_event(session_factory, body["event"]["id"])
    assert stored is not None
    assert stored.business_id == "business_123"
    assert stored.event_type == "sale"
    assert stored.language == "en"
    assert stored.data["item"] == "shirts"
    assert stored.created_at is not None


def test_invalid_sale_missing_item_is_rejected(client, session_factory):
    payload = {
        "business_id": "business_123",
        "language": "en",
        "event_type": "sale",
        "data": {"quantity": 3, "amount": 900, "currency": "ETB"},
    }
    response = post_event(client, payload)
    assert response.status_code == 400
    body = response.json()
    assert body["success"] is False
    assert body["status"] == "needs_clarification"
    assert "item" in body["missing_fields"]
    assert event_count(session_factory) == 0


def test_valid_expense(client, session_factory):
    response = post_event(
        client,
        {
            "business_id": "business_123",
            "language": "en",
            "event_type": "expense",
            "data": {
                "description": "transportation",
                "amount": 2000,
                "currency": "ETB",
                "category": "transportation",
                "date": "2026-09-17",
            },
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["event"]["event_type"] == "expense"
    assert body["event"]["data"]["description"] == "transportation"
    assert body["event"]["data"]["amount"] == 2000
    assert load_event(session_factory, body["event"]["id"]) is not None


def test_valid_purchase_preserves_inventory_fields(client, session_factory):
    response = post_event(
        client,
        {
            "business_id": "shop_a",
            "language": "en",
            "event_type": "purchase",
            "data": {
                "item": "shirts",
                "quantity": 20,
                "amount": 8000,
                "currency": "ETB",
                "supplier": None,
                "date": "2026-09-17",
            },
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["event"]["event_type"] == "purchase"
    stored = load_event(session_factory, body["event"]["id"])
    assert stored is not None
    assert stored.business_id == "shop_a"
    assert stored.data["item"] == "shirts"
    assert stored.data["quantity"] == 20
    assert stored.data["amount"] == 8000


def test_valid_inventory_adjustment(client, session_factory):
    response = post_event(
        client,
        {
            "business_id": "business_123",
            "language": "en",
            "event_type": "inventory_adjustment",
            "data": {
                "item": "shirts",
                "quantity": -2,
                "reason": "damaged",
                "date": "2026-09-17",
            },
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["event"]["data"]["quantity"] == -2
    assert body["event"]["data"]["reason"] == "damaged"
    stored = load_event(session_factory, body["event"]["id"])
    assert stored is not None
    assert stored.event_type == "inventory_adjustment"


def test_valid_customer_debt(client, session_factory):
    response = post_event(
        client,
        {
            "business_id": "business_123",
            "language": "en",
            "event_type": "customer_debt",
            "data": {
                "customer": "Hana",
                "amount": 600,
                "currency": "ETB",
                "direction": "owed_to_business",
                "date": "2026-09-17",
            },
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["event"]["event_type"] == "customer_debt"
    assert body["event"]["data"]["direction"] == "owed_to_business"
    assert body["event"]["data"]["customer"] == "Hana"
    assert "Hana owes 600 ETB" in body["message"]
    stored = load_event(session_factory, body["event"]["id"])
    assert stored is not None
    assert stored.data["direction"] == "owed_to_business"


def test_unsupported_event_type(client, session_factory):
    response = post_event(
        client,
        {
            "business_id": "business_123",
            "language": "en",
            "event_type": "payroll",
            "data": {"amount": 100},
        },
    )
    assert response.status_code == 400
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert "Unsupported event_type" in body["error"]["message"]
    assert event_count(session_factory) == 0


def test_missing_required_sale_amount(client, session_factory):
    response = post_event(
        client,
        {
            "business_id": "business_123",
            "language": "en",
            "event_type": "sale",
            "data": {
                "item": "shirts",
                "quantity": 3,
                "date": "2026-09-17",
            },
        },
    )
    assert response.status_code == 400
    body = response.json()
    assert body["success"] is False
    assert body["status"] == "needs_clarification"
    assert "amount" in body["missing_fields"]
    assert body["error"]["code"] == "NEEDS_CLARIFICATION"
    assert event_count(session_factory) == 0


def test_invalid_amount(client, session_factory):
    response = post_event(
        client,
        {
            "business_id": "business_123",
            "language": "en",
            "event_type": "sale",
            "data": {
                "item": "shirts",
                "quantity": 3,
                "amount": 0,
                "currency": "ETB",
                "date": "2026-09-17",
            },
        },
    )
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert "greater than zero" in body["error"]["message"]
    assert event_count(session_factory) == 0


def test_invalid_quantity(client, session_factory):
    response = post_event(
        client,
        {
            "business_id": "business_123",
            "language": "en",
            "event_type": "purchase",
            "data": {
                "item": "shirts",
                "quantity": -5,
                "amount": 8000,
                "currency": "ETB",
                "date": "2026-09-17",
            },
        },
    )
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert "greater than zero" in body["error"]["message"]
    assert event_count(session_factory) == 0


def test_zero_inventory_adjustment_quantity_rejected(client, session_factory):
    response = post_event(
        client,
        {
            "business_id": "business_123",
            "language": "en",
            "event_type": "inventory_adjustment",
            "data": {
                "item": "shirts",
                "quantity": 0,
                "reason": "noop",
                "date": "2026-09-17",
            },
        },
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert event_count(session_factory) == 0


def test_invalid_debt_direction(client, session_factory):
    response = post_event(
        client,
        {
            "business_id": "business_123",
            "language": "en",
            "event_type": "customer_debt",
            "data": {
                "customer": "Hana",
                "amount": 600,
                "currency": "ETB",
                "direction": "maybe",
                "date": "2026-09-17",
            },
        },
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert event_count(session_factory) == 0


def test_missing_business_id(client, session_factory):
    response = post_event(
        client,
        {
            "language": "en",
            "event_type": "sale",
            "data": {"item": "shirts", "quantity": 1, "amount": 100},
        },
    )
    assert response.status_code == 400
    assert response.json()["success"] is False
    assert event_count(session_factory) == 0


def test_business_id_is_not_hard_coded(client, session_factory):
    first = post_event(
        client,
        {
            "business_id": "shop_one",
            "language": "en",
            "event_type": "expense",
            "data": {"description": "rent", "amount": 100, "currency": "ETB"},
        },
    )
    second = post_event(
        client,
        {
            "business_id": "shop_two",
            "language": "am",
            "event_type": "expense",
            "data": {"description": "rent", "amount": 200, "currency": "ETB"},
        },
    )
    assert first.status_code == 201
    assert second.status_code == 201
    assert load_event(session_factory, first.json()["event"]["id"]).business_id == "shop_one"
    assert load_event(session_factory, second.json()["event"]["id"]).business_id == "shop_two"
    assert load_event(session_factory, second.json()["event"]["id"]).language == "am"
