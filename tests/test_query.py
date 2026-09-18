from datetime import date


def post_event(client, payload):
    return client.post("/api/v1/events", json=payload)


def post_query(client, business_id, query, language="en"):
    return client.post(
        "/api/v1/query",
        json={"business_id": business_id, "language": language, "query": query},
    )


def test_sales_total_today_uses_persisted_events(client):
    today = date.today().isoformat()
    post_event(
        client,
        {
            "business_id": "business_123",
            "language": "en",
            "event_type": "sale",
            "data": {
                "item": "shirts",
                "quantity": 3,
                "amount": 900,
                "currency": "ETB",
                "date": today,
            },
        },
    )
    post_event(
        client,
        {
            "business_id": "business_123",
            "language": "en",
            "event_type": "sale",
            "data": {
                "item": "shirts",
                "quantity": 2,
                "amount": 3600,
                "currency": "ETB",
                "date": today,
            },
        },
    )
    other_day = post_event(
        client,
        {
            "business_id": "business_123",
            "language": "en",
            "event_type": "sale",
            "data": {
                "item": "shirts",
                "quantity": 1,
                "amount": 100,
                "currency": "ETB",
                "date": "2020-01-01",
            },
        },
    )
    assert other_day.status_code == 201

    response = post_query(client, "business_123", "How much did I sell today?")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["query_type"] == "sales_total"
    assert body["result"]["amount"] == 4500
    assert body["result"]["currency"] == "ETB"
    assert body["result"]["period"]["start"] == today
    assert "4,500 ETB" in body["message"]


def test_query_is_scoped_to_business_id(client):
    today = date.today().isoformat()
    post_event(
        client,
        {
            "business_id": "shop_one",
            "language": "en",
            "event_type": "sale",
            "data": {"item": "shirts", "quantity": 1, "amount": 900, "date": today},
        },
    )
    post_event(
        client,
        {
            "business_id": "shop_two",
            "language": "en",
            "event_type": "sale",
            "data": {"item": "shirts", "quantity": 1, "amount": 50, "date": today},
        },
    )
    body = post_query(client, "shop_one", "How much did I sell today?").json()
    assert body["result"]["amount"] == 900


def test_expenses_total(client):
    today = date.today().isoformat()
    post_event(
        client,
        {
            "business_id": "business_123",
            "language": "en",
            "event_type": "expense",
            "data": {
                "description": "transportation",
                "amount": 2000,
                "currency": "ETB",
                "date": today,
            },
        },
    )
    body = post_query(client, "business_123", "What did I spend this week?").json()
    assert body["query_type"] == "expenses_total"
    assert body["result"]["amount"] == 2000
    assert "2,000 ETB" in body["message"]


def test_inventory_quantity_from_events(client):
    post_event(
        client,
        {
            "business_id": "business_123",
            "language": "en",
            "event_type": "purchase",
            "data": {"item": "shirts", "quantity": 20, "amount": 8000, "date": "2026-09-01"},
        },
    )
    post_event(
        client,
        {
            "business_id": "business_123",
            "language": "en",
            "event_type": "sale",
            "data": {"item": "shirts", "quantity": 3, "amount": 900, "date": "2026-09-17"},
        },
    )
    body = post_query(client, "business_123", "How many shirts do I have left?").json()
    assert body["query_type"] == "inventory_quantity"
    assert body["result"]["quantity"] == 17
    assert body["result"]["item"] == "shirts"
    assert "17 shirts" in body["message"]


def test_customer_debt_specific_and_list(client):
    post_event(
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
    hana = post_query(client, "business_123", "How much does Hana owe me?").json()
    assert hana["query_type"] == "customer_debt"
    assert hana["result"]["amount"] == 600
    assert hana["result"]["customer"] == "Hana"
    assert "Hana owes you 600 ETB" in hana["message"]

    listing = post_query(client, "business_123", "Who owes me money?").json()
    assert listing["result"]["total"] == 600
    assert listing["result"]["customers"][0]["customer"] == "Hana"


def test_biggest_expenses(client):
    today = date.today().isoformat()
    post_event(
        client,
        {
            "business_id": "business_123",
            "language": "en",
            "event_type": "expense",
            "data": {"description": "rent", "amount": 5000, "date": today},
        },
    )
    post_event(
        client,
        {
            "business_id": "business_123",
            "language": "en",
            "event_type": "expense",
            "data": {"description": "transportation", "amount": 200, "date": today},
        },
    )
    body = post_query(client, "business_123", "What were my biggest expenses this month?").json()
    assert body["query_type"] == "expenses_top"
    assert body["result"]["expenses"][0]["description"] == "rent"
    assert "rent" in body["message"]


def test_unrecognized_query_needs_clarification(client):
    response = post_query(client, "business_123", "Tell me a joke")
    assert response.status_code == 400
    body = response.json()
    assert body["success"] is False
    assert body["status"] == "needs_clarification"
    assert body["error"]["code"] == "NEEDS_CLARIFICATION"


def test_inventory_query_without_item_needs_clarification(client):
    response = post_query(client, "business_123", "How many do I have left?")
    assert response.status_code == 400
    assert "item" in response.json()["missing_fields"]


def test_missing_query_field(client):
    response = client.post(
        "/api/v1/query",
        json={"business_id": "business_123", "language": "en"},
    )
    assert response.status_code == 400
    assert response.json()["success"] is False


def test_inventory_includes_purchase_sale_and_adjustment(client):
    post_event(
        client,
        {
            "business_id": "business_123",
            "language": "en",
            "event_type": "purchase",
            "data": {"item": "shirts", "quantity": 20, "amount": 8000, "date": "2026-09-01"},
        },
    )
    post_event(
        client,
        {
            "business_id": "business_123",
            "language": "en",
            "event_type": "sale",
            "data": {"item": "shirts", "quantity": 3, "amount": 900, "date": "2026-09-17"},
        },
    )
    adjustment = post_event(
        client,
        {
            "business_id": "business_123",
            "language": "en",
            "event_type": "inventory_adjustment",
            "data": {
                "item": "shirts",
                "quantity": -2,
                "reason": "damaged",
                "date": "2026-09-18",
            },
        },
    )
    assert adjustment.status_code == 201
    body = post_query(client, "business_123", "How many shirts do I have left?").json()
    assert body["success"] is True
    assert body["query_type"] == "inventory_quantity"
    assert body["result"]["quantity"] == 15


def test_inventory_adjustment_alone_is_included(client):
    post_event(
        client,
        {
            "business_id": "business_123",
            "language": "en",
            "event_type": "inventory_adjustment",
            "data": {"item": "shirts", "quantity": 4, "reason": "found stock", "date": "2026-09-17"},
        },
    )
    body = post_query(client, "business_123", "How many shirts do I have left?").json()
    assert body["query_type"] == "inventory_quantity"
    assert body["result"]["quantity"] == 4


def test_purchase_wording_with_cost_is_not_treated_as_expense(client):
    post_event(
        client,
        {
            "business_id": "business_123",
            "language": "en",
            "event_type": "purchase",
            "data": {"item": "shirts", "quantity": 20, "amount": 8000, "date": "2026-09-17"},
        },
    )
    post_event(
        client,
        {
            "business_id": "business_123",
            "language": "en",
            "event_type": "expense",
            "data": {"description": "transportation", "amount": 2000, "date": "2026-09-17"},
        },
    )
    response = post_query(client, "business_123", "What's the cost of my purchases?")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["query_type"] == "purchases_total"
    assert body["result"]["amount"] == 8000


def test_spend_buying_stock_is_ambiguous(client):
    post_event(
        client,
        {
            "business_id": "business_123",
            "language": "en",
            "event_type": "expense",
            "data": {"description": "transportation", "amount": 2000, "date": "2026-09-17"},
        },
    )
    response = post_query(client, "business_123", "How much did I spend buying stock?")
    assert response.status_code == 400
    body = response.json()
    assert body["success"] is False
    assert body["status"] == "needs_clarification"


def test_sales_left_to_record_is_ambiguous(client):
    post_event(
        client,
        {
            "business_id": "business_123",
            "language": "en",
            "event_type": "sale",
            "data": {"item": "shirts", "quantity": 3, "amount": 900, "date": "2026-09-17"},
        },
    )
    response = post_query(client, "business_123", "What sales are left to record?")
    assert response.status_code == 400
    body = response.json()
    assert body["success"] is False
    assert body["status"] == "needs_clarification"


def test_supplier_owe_wording_is_not_customer_debt(client):
    post_event(
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
    response = post_query(
        client, "business_123", "How much does the business owe suppliers?"
    )
    assert response.status_code == 400
    body = response.json()
    assert body["success"] is False
    assert body["status"] == "needs_clarification"


def test_who_do_i_owe_needs_clarification(client):
    post_event(
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
    response = post_query(client, "business_123", "Who do I owe?")
    assert response.status_code == 400
    body = response.json()
    assert body["success"] is False
    assert body["status"] == "needs_clarification"


def test_keyword_item_name_does_not_filter_sales(client):
    today = date.today().isoformat()
    post_event(
        client,
        {
            "business_id": "business_123",
            "language": "en",
            "event_type": "sale",
            "data": {"item": "today", "quantity": 1, "amount": 50, "date": today},
        },
    )
    post_event(
        client,
        {
            "business_id": "business_123",
            "language": "en",
            "event_type": "sale",
            "data": {"item": "shirts", "quantity": 1, "amount": 900, "date": today},
        },
    )
    body = post_query(client, "business_123", "How much did I sell today?").json()
    assert body["success"] is True
    assert body["query_type"] == "sales_total"
    assert "item" not in body["result"]
    assert body["result"]["amount"] == 950


def test_non_english_language_needs_clarification(client):
    response = post_query(
        client,
        "business_123",
        "How much did I sell today?",
        language="am",
    )
    assert response.status_code == 400
    body = response.json()
    assert body["success"] is False
    assert body["status"] == "needs_clarification"
