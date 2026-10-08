from datetime import datetime, timezone

from app.business_time import BUSINESS_ZONE, business_today

# 22:30 UTC is still 7 October; Addis Ababa (UTC+3) is already 8 October.
ADDIS_AHEAD_OF_UTC = datetime(2026, 10, 7, 22, 30, tzinfo=timezone.utc)


def _use_addis_clock(monkeypatch, instant: datetime) -> None:
    localized = instant.astimezone(BUSINESS_ZONE)

    def _frozen() -> datetime:
        return localized

    monkeypatch.setattr("app.business_time.business_now", _frozen)


from tests.conftest import auth_headers


def post_event(client, payload, headers=None):
    if headers is None:
        sub = payload.get("business_id", "test_user") if isinstance(payload, dict) else "test_user"
        headers = auth_headers(sub)
    return client.post("/api/v1/events", json=payload, headers=headers)


def post_query(client, query, business_id="business_123", headers=None):
    if headers is None:
        headers = auth_headers(business_id)
    return client.post(
        "/api/v1/query",
        json={"business_id": business_id, "language": "en", "query": query},
        headers=headers,
    )


def test_implicit_today_follows_addis_ababa_not_utc(client, monkeypatch):
    _use_addis_clock(monkeypatch, ADDIS_AHEAD_OF_UTC)
    assert business_today().isoformat() == "2026-10-08"
    assert ADDIS_AHEAD_OF_UTC.astimezone(timezone.utc).date().isoformat() == "2026-10-07"

    omitted = post_event(
        client,
        {
            "business_id": "business_123",
            "language": "en",
            "event_type": "sale",
            "data": {"item": "tea", "quantity": 1, "amount": 40, "currency": "ETB"},
        },
    )
    assert omitted.status_code == 201
    assert omitted.json()["event"]["data"]["date"] == "2026-10-08"

    explicit = post_event(
        client,
        {
            "business_id": "business_123",
            "language": "en",
            "event_type": "sale",
            "data": {
                "item": "tea",
                "quantity": 1,
                "amount": 15,
                "currency": "ETB",
                "date": "2026-10-07",
            },
        },
    )
    assert explicit.status_code == 201

    today = post_query(client, "How much did I sell today?").json()
    assert today["result"]["amount"] == 40
    assert today["result"]["period"] == {"start": "2026-10-08", "end": "2026-10-08"}


def test_supported_week_and_month_use_addis_calendar(client, monkeypatch):
    _use_addis_clock(monkeypatch, ADDIS_AHEAD_OF_UTC)
    # Thursday 2026-10-08. Week starts Monday 2026-10-05. Month starts 2026-10-01.
    amounts = {
        "2026-09-30": 5,
        "2026-10-04": 7,
        "2026-10-05": 11,
        "2026-10-08": 13,
    }
    for day, amount in amounts.items():
        response = post_event(
            client,
            {
                "business_id": "business_123",
                "language": "en",
                "event_type": "sale",
                "data": {
                    "item": "tea",
                    "quantity": 1,
                    "amount": amount,
                    "currency": "ETB",
                    "date": day,
                },
            },
        )
        assert response.status_code == 201

    week = post_query(client, "How much did I sell this week?").json()
    assert week["result"]["amount"] == 24
    assert week["result"]["period"] == {"start": "2026-10-05", "end": "2026-10-08"}

    month = post_query(client, "How much did I sell this month?").json()
    assert month["result"]["amount"] == 31
    assert month["result"]["period"] == {"start": "2026-10-01", "end": "2026-10-08"}


def test_unsupported_time_phrases_clarify(client):
    post_event(
        client,
        {
            "business_id": "business_123",
            "language": "en",
            "event_type": "sale",
            "data": {
                "item": "tea",
                "quantity": 1,
                "amount": 900,
                "currency": "ETB",
                "date": "2026-09-17",
            },
        },
    )
    for question in (
        "How much did I sell yesterday?",
        "How much did I sell last week?",
        "How much did I sell last month?",
        "How much did I sell in the last 7 days?",
        "How much did I sell on 2026-09-17?",
    ):
        response = post_query(client, question)
        assert response.status_code == 400, question
        body = response.json()
        assert body["success"] is False
        assert body["status"] == "needs_clarification"
        assert body["error"]["code"] == "NEEDS_CLARIFICATION"
        assert "period" in body["missing_fields"]


def test_all_time_sales_when_no_period_is_given(client):
    post_event(
        client,
        {
            "business_id": "business_123",
            "language": "en",
            "event_type": "sale",
            "data": {
                "item": "tea",
                "quantity": 1,
                "amount": 900,
                "currency": "ETB",
                "date": "2026-09-17",
            },
        },
    )
    body = post_query(client, "How much did I sell?").json()
    assert body["success"] is True
    assert body["query_type"] == "sales_total"
    assert body["result"]["amount"] == 900
    assert "period" not in body["result"]


def test_shirt_and_shirts_share_stock_across_events(client):
    purchase = post_event(
        client,
        {
            "business_id": "business_123",
            "language": "en",
            "event_type": "purchase",
            "data": {"item": "shirt", "quantity": 20, "amount": 8000, "currency": "ETB"},
        },
    )
    sale = post_event(
        client,
        {
            "business_id": "business_123",
            "language": "en",
            "event_type": "sale",
            "data": {"item": "shirts", "quantity": 3, "amount": 900, "currency": "ETB"},
        },
    )
    adjustment = post_event(
        client,
        {
            "business_id": "business_123",
            "language": "en",
            "event_type": "inventory_adjustment",
            "data": {"item": "shirt", "quantity": -2, "reason": "damaged"},
        },
    )
    assert purchase.status_code == 201
    assert sale.status_code == 201
    assert adjustment.status_code == 201

    plural = post_query(client, "How many shirts do I have?").json()
    singular = post_query(client, "How many shirt do I have left?").json()
    assert plural["result"]["quantity"] == 15
    assert singular["result"]["quantity"] == 15

    sold = post_query(client, "How many shirts did I sell?").json()
    assert sold["query_type"] == "sales_total"
    assert sold["result"]["quantity"] == 3
    assert sold["result"]["amount"] == 900


def test_shorts_are_not_treated_as_short(client):
    post_event(
        client,
        {
            "business_id": "business_123",
            "language": "en",
            "event_type": "purchase",
            "data": {"item": "shorts", "quantity": 5, "amount": 1500, "currency": "ETB"},
        },
    )
    post_event(
        client,
        {
            "business_id": "business_123",
            "language": "en",
            "event_type": "purchase",
            "data": {"item": "short", "quantity": 2, "amount": 400, "currency": "ETB"},
        },
    )
    shorts = post_query(client, "How many shorts do I have?").json()
    short = post_query(client, "How many short do I have?").json()
    assert shorts["result"]["quantity"] == 5
    assert short["result"]["quantity"] == 2


def test_zero_inventory_adjustment_is_rejected(client):
    response = post_event(
        client,
        {
            "business_id": "business_123",
            "language": "en",
            "event_type": "inventory_adjustment",
            "data": {"item": "shirt", "quantity": 0, "reason": "noop"},
        },
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_single_and_multi_word_customers_and_netting(client):
    events = [
        ("Hana", 600, "owed_to_business", "ETB"),
        ("Hana", 100, "owed_by_business", "ETB"),
        ("Abebe Kebede", 800, "owed_to_business", "ETB"),
        ("Sara", 50, "owed_by_business", "ETB"),
    ]
    for customer, amount, direction, currency in events:
        response = post_event(
            client,
            {
                "business_id": "business_123",
                "language": "en",
                "event_type": "customer_debt",
                "data": {
                    "customer": customer,
                    "amount": amount,
                    "currency": currency,
                    "direction": direction,
                    "date": "2026-09-17",
                },
            },
        )
        assert response.status_code == 201

    hana = post_query(client, "How much does Hana owe me?").json()
    assert hana["result"]["customer"] == "Hana"
    assert hana["result"]["amount"] == 500
    assert hana["result"]["direction"] == "owed_to_business"
    assert hana["result"]["currency"] == "ETB"

    abebe = post_query(client, "How much does Abebe Kebede owe?").json()
    assert abebe["result"]["customer"] == "Abebe Kebede"
    assert abebe["result"]["amount"] == 800
    assert "Abebe Kebede owes you 800 ETB" in abebe["message"]

    unknown = post_query(client, "How much does Liya Bekele owe me?").json()
    assert unknown["result"]["customer"] == "Liya Bekele"
    assert unknown["result"]["amount"] == 0
    assert unknown["result"]["currency"] == "ETB"

    sara = post_query(client, "How much does Sara owe me?").json()
    assert sara["result"]["amount"] == -50
    assert sara["result"]["direction"] == "owed_by_business"
    assert "You owe Sara 50 ETB" in sara["message"]

    listing = post_query(client, "Who owes me money?").json()
    names = [row["customer"] for row in listing["result"]["customers"]]
    assert names == ["Abebe Kebede", "Hana"]
    assert listing["result"]["total"] == 1300
    assert "Sara" not in names


def test_same_currency_aggregates_and_mixed_currencies_clarify(client):
    def sale(amount, currency, item="tea"):
        response = post_event(
            client,
            {
                "business_id": "shop_etb" if currency == "ETB" else "shop_usd",
                "language": "en",
                "event_type": "sale",
                "data": {
                    "item": item,
                    "quantity": 1,
                    "amount": amount,
                    "currency": currency,
                    "date": "2026-09-17",
                },
            },
        )
        assert response.status_code == 201

    sale(900, "ETB")
    sale(100, "ETB")
    etb = post_query(client, "How much did I sell?", business_id="shop_etb").json()
    assert etb["result"]["amount"] == 1000
    assert etb["result"]["currency"] == "ETB"

    sale(40, "USD")
    sale(10, "USD")
    usd = post_query(client, "How much did I sell?", business_id="shop_usd").json()
    assert usd["result"]["amount"] == 50
    assert usd["result"]["currency"] == "USD"

    mixed = post_event(
        client,
        {
            "business_id": "shop_etb",
            "language": "en",
            "event_type": "sale",
            "data": {
                "item": "tea",
                "quantity": 1,
                "amount": 25,
                "currency": "USD",
                "date": "2026-09-17",
            },
        },
    )
    assert mixed.status_code == 201
    response = post_query(client, "How much did I sell?", business_id="shop_etb")
    assert response.status_code == 400
    body = response.json()
    assert body["status"] == "needs_clarification"
    assert "currency" in body["missing_fields"]
    assert "1000 ETB" not in body["message"]


def test_mixed_debt_currencies_clarify(client):
    for amount, currency in ((600, "ETB"), (20, "USD")):
        response = post_event(
            client,
            {
                "business_id": "business_123",
                "language": "en",
                "event_type": "customer_debt",
                "data": {
                    "customer": "Hana",
                    "amount": amount,
                    "currency": currency,
                    "direction": "owed_to_business",
                    "date": "2026-09-17",
                },
            },
        )
        assert response.status_code == 201

    named = post_query(client, "How much does Hana owe me?")
    listing = post_query(client, "Who owes me money?")
    for response in (named, listing):
        assert response.status_code == 400
        body = response.json()
        assert body["status"] == "needs_clarification"
        assert "currency" in body["missing_fields"]
