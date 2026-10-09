from __future__ import annotations

from datetime import timedelta
import pytest

from app.business_time import business_today
from tests.conftest import auth_headers


def post_event(client, payload, sub: str = "user_123"):
    headers = auth_headers(sub)
    return client.post("/api/v1/events", json=payload, headers=headers)


def get_dashboard(client, sub: str = "user_123", headers=None, params=None):
    if headers is None:
        headers = auth_headers(sub)
    return client.get("/api/v1/dashboard", headers=headers, params=params)


def test_dashboard_requires_authentication(client):
    # Missing Authorization header
    response = client.get("/api/v1/dashboard")
    assert response.status_code == 401
    assert response.json()["success"] is False

    # Missing Authorization header with trailing slash (resolves directly without 307 redirect or 404)
    response_slash = client.get("/api/v1/dashboard/", follow_redirects=False)
    assert response_slash.status_code == 401
    assert response_slash.json()["success"] is False

    # Invalid token format
    response = client.get(
        "/api/v1/dashboard",
        headers={"Authorization": "InvalidTokenFormat"},
    )
    assert response.status_code == 401
    assert response.json()["success"] is False


def test_dashboard_url_paths_resolve_without_redirect_or_404(client):
    headers = auth_headers("test_user")

    # Exact path without trailing slash
    resp_no_slash = client.get("/api/v1/dashboard", headers=headers)
    assert resp_no_slash.status_code == 200

    # Path with trailing slash resolves directly with 200 (not 404, not 307)
    resp_slash = client.get("/api/v1/dashboard/", headers=headers, follow_redirects=False)
    assert resp_slash.status_code == 200
    assert resp_slash.json() == resp_no_slash.json()



def test_dashboard_empty_state_for_new_tenant(client):
    response = get_dashboard(client, sub="empty_tenant")
    assert response.status_code == 200
    body = response.json()

    assert body == {
        "sales_today": {"amount": 0.0, "currency": "ETB", "count": 0},
        "expenses_today": {"amount": 0.0, "currency": "ETB", "count": 0},
        "customer_debt": {"total": 0.0, "currency": "ETB", "customers": []},
        "inventory": {"total_items": 0, "low_stock_count": 0, "items": []},
        "recent_activity": [],
    }


def test_sales_and_expenses_today_aggregation(client):
    sub = "merchant_sales_test"
    today = business_today()
    today_str = today.isoformat()
    yesterday_str = (today - timedelta(days=1)).isoformat()

    # Sales today
    post_event(
        client,
        {
            "business_id": "ignored",
            "language": "en",
            "event_type": "sale",
            "data": {"item": "coffee", "quantity": 2, "amount": 160.0, "currency": "ETB", "date": today_str},
        },
        sub=sub,
    )
    post_event(
        client,
        {
            "business_id": "ignored",
            "language": "en",
            "event_type": "sale",
            "data": {"item": "tea", "quantity": 1, "amount": 40.0, "currency": "ETB", "date": today_str},
        },
        sub=sub,
    )
    # Sale yesterday (should NOT be counted in sales_today)
    post_event(
        client,
        {
            "business_id": "ignored",
            "language": "en",
            "event_type": "sale",
            "data": {"item": "pastry", "quantity": 1, "amount": 100.0, "currency": "ETB", "date": yesterday_str},
        },
        sub=sub,
    )

    # Expenses today
    post_event(
        client,
        {
            "business_id": "ignored",
            "language": "en",
            "event_type": "expense",
            "data": {"description": "milk and sugar", "amount": 75.50, "currency": "ETB", "date": today_str},
        },
        sub=sub,
    )
    # Expense yesterday (should NOT be counted in expenses_today)
    post_event(
        client,
        {
            "business_id": "ignored",
            "language": "en",
            "event_type": "expense",
            "data": {"description": "cleaning supplies", "amount": 50.0, "currency": "ETB", "date": yesterday_str},
        },
        sub=sub,
    )

    response = get_dashboard(client, sub=sub)
    assert response.status_code == 200
    data = response.json()

    # Sales today: 160 + 40 = 200, count = 2
    assert data["sales_today"]["amount"] == 200.0
    assert data["sales_today"]["currency"] == "ETB"
    assert data["sales_today"]["count"] == 2

    # Expenses today: 75.50, count = 1
    assert data["expenses_today"]["amount"] == 75.50
    assert data["expenses_today"]["currency"] == "ETB"
    assert data["expenses_today"]["count"] == 1


def test_customer_debt_aggregation_and_ranking(client):
    sub = "debt_test_merchant"
    today_str = business_today().isoformat()

    # Customer Hana owes 800
    post_event(
        client,
        {
            "business_id": "ignored",
            "language": "en",
            "event_type": "customer_debt",
            "data": {
                "customer": "Hana",
                "amount": 800.0,
                "currency": "ETB",
                "direction": "owed_to_business",
                "date": today_str,
            },
        },
        sub=sub,
    )
    # Hana repays 300 (owed_by_business reduces debt)
    post_event(
        client,
        {
            "business_id": "ignored",
            "language": "en",
            "event_type": "customer_debt",
            "data": {
                "customer": "Hana",
                "amount": 300.0,
                "currency": "ETB",
                "direction": "owed_by_business",
                "date": today_str,
            },
        },
        sub=sub,
    )
    # Customer Abebe owes 1200
    post_event(
        client,
        {
            "business_id": "ignored",
            "language": "en",
            "event_type": "customer_debt",
            "data": {
                "customer": "Abebe",
                "amount": 1200.0,
                "currency": "ETB",
                "direction": "owed_to_business",
                "date": today_str,
            },
        },
        sub=sub,
    )
    # Customer Chala settled balance to 0
    post_event(
        client,
        {
            "business_id": "ignored",
            "language": "en",
            "event_type": "customer_debt",
            "data": {
                "customer": "Chala",
                "amount": 500.0,
                "currency": "ETB",
                "direction": "owed_to_business",
                "date": today_str,
            },
        },
        sub=sub,
    )
    post_event(
        client,
        {
            "business_id": "ignored",
            "language": "en",
            "event_type": "customer_debt",
            "data": {
                "customer": "Chala",
                "amount": 500.0,
                "currency": "ETB",
                "direction": "owed_by_business",
                "date": today_str,
            },
        },
        sub=sub,
    )

    response = get_dashboard(client, sub=sub)
    assert response.status_code == 200
    debt = response.json()["customer_debt"]

    # Total = 1200 (Abebe) + 500 (Hana: 800 - 300) = 1700
    assert debt["total"] == 1700.0
    assert debt["currency"] == "ETB"

    # Top debtors breakdown sorted descending
    customers = debt["customers"]
    assert len(customers) == 2
    assert customers[0]["customer"] == "Abebe"
    assert customers[0]["amount"] == 1200.0
    assert customers[0]["currency"] == "ETB"

    assert customers[1]["customer"] == "Hana"
    assert customers[1]["amount"] == 500.0
    assert customers[1]["currency"] == "ETB"


def test_inventory_metrics_and_low_stock(client):
    sub = "inventory_test_merchant"
    today_str = business_today().isoformat()

    # Item 1: Shirts - Purchase 20, Sale 3, Adjustment -2 -> 15 units (normal stock > 10)
    post_event(
        client,
        {
            "business_id": "ignored",
            "language": "en",
            "event_type": "purchase",
            "data": {"item": "shirts", "quantity": 20, "amount": 4000, "currency": "ETB", "date": today_str},
        },
        sub=sub,
    )
    post_event(
        client,
        {
            "business_id": "ignored",
            "language": "en",
            "event_type": "sale",
            "data": {"item": "shirt", "quantity": 3, "amount": 900, "currency": "ETB", "date": today_str},
        },
        sub=sub,
    )
    post_event(
        client,
        {
            "business_id": "ignored",
            "language": "en",
            "event_type": "inventory_adjustment",
            "data": {"item": "shirt", "quantity": -2, "reason": "damaged", "date": today_str},
        },
        sub=sub,
    )

    # Item 2: Shoes - Purchase 5, Sale 2 -> 3 units (low stock <= 10)
    post_event(
        client,
        {
            "business_id": "ignored",
            "language": "en",
            "event_type": "purchase",
            "data": {"item": "shoes", "quantity": 5, "amount": 2500, "currency": "ETB", "date": today_str},
        },
        sub=sub,
    )
    post_event(
        client,
        {
            "business_id": "ignored",
            "language": "en",
            "event_type": "sale",
            "data": {"item": "shoes", "quantity": 2, "amount": 1600, "currency": "ETB", "date": today_str},
        },
        sub=sub,
    )

    # Item 3: Hat - Sale 2 without purchase -> -2 units (low stock <= 10)
    post_event(
        client,
        {
            "business_id": "ignored",
            "language": "en",
            "event_type": "sale",
            "data": {"item": "hat", "quantity": 2, "amount": 500, "currency": "ETB", "date": today_str},
        },
        sub=sub,
    )

    response = get_dashboard(client, sub=sub)
    assert response.status_code == 200
    inv = response.json()["inventory"]

    assert inv["total_items"] == 3
    assert inv["low_stock_count"] == 2

    # Low-stock items ordered ascending by quantity
    items = inv["items"]
    assert len(items) == 2
    assert items[0]["item"] == "hat"
    assert items[0]["quantity"] == -2.0
    assert items[0]["unit"] == "units"

    assert items[1]["item"] == "shoes"
    assert items[1]["quantity"] == 3.0
    assert items[1]["unit"] == "units"


def test_recent_activity_chronology_and_descriptions(client):
    sub = "activity_test_merchant"
    today_str = business_today().isoformat()

    # Create several events of different types
    post_event(
        client,
        {
            "business_id": "ignored",
            "language": "en",
            "event_type": "sale",
            "data": {"item": "dress", "quantity": 1, "amount": 1200, "currency": "ETB", "customer": "Sara", "date": today_str},
        },
        sub=sub,
    )
    post_event(
        client,
        {
            "business_id": "ignored",
            "language": "en",
            "event_type": "expense",
            "data": {"description": "electricity bill", "amount": 450, "currency": "ETB", "date": today_str},
        },
        sub=sub,
    )
    post_event(
        client,
        {
            "business_id": "ignored",
            "language": "en",
            "event_type": "purchase",
            "data": {"item": "fabric", "quantity": 10, "amount": 3000, "currency": "ETB", "supplier": "Textiles Co", "date": today_str},
        },
        sub=sub,
    )
    post_event(
        client,
        {
            "business_id": "ignored",
            "language": "en",
            "event_type": "customer_debt",
            "data": {"customer": "Dawit", "amount": 700, "currency": "ETB", "direction": "owed_to_business", "date": today_str},
        },
        sub=sub,
    )
    post_event(
        client,
        {
            "business_id": "ignored",
            "language": "en",
            "event_type": "inventory_adjustment",
            "data": {"item": "fabric", "quantity": -1, "reason": "damaged", "date": today_str},
        },
        sub=sub,
    )

    response = get_dashboard(client, sub=sub)
    assert response.status_code == 200
    activities = response.json()["recent_activity"]

    assert len(activities) == 5

    # Most recent first
    assert activities[0]["type"] == "inventory_adjustment"
    assert "damaged" in activities[0]["description"]
    assert activities[0]["amount"] is None
    assert activities[0]["timestamp"] != ""

    assert activities[1]["type"] == "customer_debt"
    assert activities[1]["amount"] == 700.0
    assert activities[1]["currency"] == "ETB"
    assert "Dawit" in activities[1]["description"]

    assert activities[2]["type"] == "purchase"
    assert activities[2]["amount"] == 3000.0
    assert activities[2]["currency"] == "ETB"
    assert "fabric" in activities[2]["description"]

    assert activities[3]["type"] == "expense"
    assert activities[3]["amount"] == 450.0
    assert activities[3]["currency"] == "ETB"
    assert "electricity bill" in activities[3]["description"]

    assert activities[4]["type"] == "sale"
    assert activities[4]["amount"] == 1200.0
    assert activities[4]["currency"] == "ETB"
    assert "dress" in activities[4]["description"]


def test_strict_tenant_isolation(client):
    tenant_a = "user_alpha"
    tenant_b = "user_beta"
    today_str = business_today().isoformat()

    # Tenant A logs a sale
    post_event(
        client,
        {
            "business_id": "ignored",
            "language": "en",
            "event_type": "sale",
            "data": {"item": "watch", "quantity": 1, "amount": 5000, "currency": "ETB", "date": today_str},
        },
        sub=tenant_a,
    )

    # Tenant B logs a different sale
    post_event(
        client,
        {
            "business_id": "ignored",
            "language": "en",
            "event_type": "sale",
            "data": {"item": "ring", "quantity": 2, "amount": 300, "currency": "ETB", "date": today_str},
        },
        sub=tenant_b,
    )

    # Check Tenant A
    resp_a = get_dashboard(client, sub=tenant_a)
    assert resp_a.status_code == 200
    data_a = resp_a.json()
    assert data_a["sales_today"]["amount"] == 5000.0
    assert data_a["sales_today"]["count"] == 1
    assert data_a["recent_activity"][0]["description"] == "Sale: 1 watch"

    # Check Tenant B
    resp_b = get_dashboard(client, sub=tenant_b)
    assert resp_b.status_code == 200
    data_b = resp_b.json()
    assert data_b["sales_today"]["amount"] == 300.0
    assert data_b["sales_today"]["count"] == 1
    assert data_b["recent_activity"][0]["description"] == "Sale: 2 ring"

    # Trying to supply business_id in query parameter has no effect
    resp_spoof = client.get(
        f"/api/v1/dashboard?business_id=biz_{tenant_a}",
        headers=auth_headers(tenant_b),
    )
    assert resp_spoof.status_code == 200
    spoof_data = resp_spoof.json()
    # Still sees tenant B's data!
    assert spoof_data["sales_today"]["amount"] == 300.0


def test_mixed_currencies_in_sales_today_triggers_clarification(client):
    sub = "mixed_sales_merchant"
    today_str = business_today().isoformat()

    post_event(
        client,
        {
            "business_id": "ignored",
            "language": "en",
            "event_type": "sale",
            "data": {"item": "shoes", "quantity": 1, "amount": 1200.0, "currency": "ETB", "date": today_str},
        },
        sub=sub,
    )
    post_event(
        client,
        {
            "business_id": "ignored",
            "language": "en",
            "event_type": "sale",
            "data": {"item": "watch", "quantity": 1, "amount": 50.0, "currency": "USD", "date": today_str},
        },
        sub=sub,
    )

    response = get_dashboard(client, sub=sub)
    assert response.status_code == 400
    body = response.json()
    assert body["success"] is False
    assert body["status"] == "needs_clarification"
    assert body["error"]["code"] == "NEEDS_CLARIFICATION"
    assert "currency" in body["missing_fields"]


def test_sales_on_different_days_with_different_currencies_do_not_conflict(client):
    sub = "multi_day_sales_merchant"
    today = business_today()
    today_str = today.isoformat()
    yesterday_str = (today - timedelta(days=1)).isoformat()

    # Yesterday was in USD
    post_event(
        client,
        {
            "business_id": "ignored",
            "language": "en",
            "event_type": "sale",
            "data": {"item": "bag", "quantity": 1, "amount": 30.0, "currency": "USD", "date": yesterday_str},
        },
        sub=sub,
    )
    # Today is in ETB
    post_event(
        client,
        {
            "business_id": "ignored",
            "language": "en",
            "event_type": "sale",
            "data": {"item": "shoes", "quantity": 1, "amount": 1200.0, "currency": "ETB", "date": today_str},
        },
        sub=sub,
    )

    response = get_dashboard(client, sub=sub)
    assert response.status_code == 200
    body = response.json()
    assert body["sales_today"]["amount"] == 1200.0
    assert body["sales_today"]["currency"] == "ETB"
    assert body["sales_today"]["count"] == 1


def test_mixed_currencies_in_expenses_today_triggers_clarification(client):
    sub = "mixed_expenses_merchant"
    today_str = business_today().isoformat()

    post_event(
        client,
        {
            "business_id": "ignored",
            "language": "en",
            "event_type": "expense",
            "data": {"description": "electricity", "amount": 500.0, "currency": "ETB", "date": today_str},
        },
        sub=sub,
    )
    post_event(
        client,
        {
            "business_id": "ignored",
            "language": "en",
            "event_type": "expense",
            "data": {"description": "cloud server", "amount": 20.0, "currency": "USD", "date": today_str},
        },
        sub=sub,
    )

    response = get_dashboard(client, sub=sub)
    assert response.status_code == 400
    body = response.json()
    assert body["success"] is False
    assert body["status"] == "needs_clarification"
    assert body["error"]["code"] == "NEEDS_CLARIFICATION"
    assert "currency" in body["missing_fields"]


def test_mixed_currencies_in_customer_debt_triggers_clarification_for_single_customer(client):
    sub = "mixed_debt_single_cust_merchant"
    today_str = business_today().isoformat()

    post_event(
        client,
        {
            "business_id": "ignored",
            "language": "en",
            "event_type": "customer_debt",
            "data": {
                "customer": "Hana",
                "amount": 800.0,
                "currency": "ETB",
                "direction": "owed_to_business",
                "date": today_str,
            },
        },
        sub=sub,
    )
    post_event(
        client,
        {
            "business_id": "ignored",
            "language": "en",
            "event_type": "customer_debt",
            "data": {
                "customer": "Hana",
                "amount": 50.0,
                "currency": "USD",
                "direction": "owed_to_business",
                "date": today_str,
            },
        },
        sub=sub,
    )

    response = get_dashboard(client, sub=sub)
    assert response.status_code == 400
    body = response.json()
    assert body["success"] is False
    assert body["status"] == "needs_clarification"
    assert body["error"]["code"] == "NEEDS_CLARIFICATION"
    assert "currency" in body["missing_fields"]


def test_mixed_currencies_in_customer_debt_triggers_clarification_for_multiple_customers(client):
    sub = "mixed_debt_multi_cust_merchant"
    today_str = business_today().isoformat()

    post_event(
        client,
        {
            "business_id": "ignored",
            "language": "en",
            "event_type": "customer_debt",
            "data": {
                "customer": "Abebe",
                "amount": 1000.0,
                "currency": "ETB",
                "direction": "owed_to_business",
                "date": today_str,
            },
        },
        sub=sub,
    )
    post_event(
        client,
        {
            "business_id": "ignored",
            "language": "en",
            "event_type": "customer_debt",
            "data": {
                "customer": "Sara",
                "amount": 80.0,
                "currency": "USD",
                "direction": "owed_to_business",
                "date": today_str,
            },
        },
        sub=sub,
    )

    response = get_dashboard(client, sub=sub)
    assert response.status_code == 400
    body = response.json()
    assert body["success"] is False
    assert body["status"] == "needs_clarification"
    assert body["error"]["code"] == "NEEDS_CLARIFICATION"
    assert "currency" in body["missing_fields"]


def test_dashboard_aggregates_consistent_non_default_currency(client):
    sub = "usd_merchant"
    today_str = business_today().isoformat()

    # Sales in USD
    post_event(
        client,
        {
            "business_id": "ignored",
            "language": "en",
            "event_type": "sale",
            "data": {"item": "software license", "quantity": 1, "amount": 100.0, "currency": "USD", "date": today_str},
        },
        sub=sub,
    )
    post_event(
        client,
        {
            "business_id": "ignored",
            "language": "en",
            "event_type": "sale",
            "data": {"item": "consulting", "quantity": 1, "amount": 50.0, "currency": "USD", "date": today_str},
        },
        sub=sub,
    )

    # Expenses in USD
    post_event(
        client,
        {
            "business_id": "ignored",
            "language": "en",
            "event_type": "expense",
            "data": {"description": "domain renewal", "amount": 15.0, "currency": "USD", "date": today_str},
        },
        sub=sub,
    )

    # Debt in USD
    post_event(
        client,
        {
            "business_id": "ignored",
            "language": "en",
            "event_type": "customer_debt",
            "data": {
                "customer": "John",
                "amount": 200.0,
                "currency": "USD",
                "direction": "owed_to_business",
                "date": today_str,
            },
        },
        sub=sub,
    )

    response = get_dashboard(client, sub=sub)
    assert response.status_code == 200
    body = response.json()

    assert body["sales_today"]["amount"] == 150.0
    assert body["sales_today"]["currency"] == "USD"
    assert body["sales_today"]["count"] == 2

    assert body["expenses_today"]["amount"] == 15.0
    assert body["expenses_today"]["currency"] == "USD"
    assert body["expenses_today"]["count"] == 1

    assert body["customer_debt"]["total"] == 200.0
    assert body["customer_debt"]["currency"] == "USD"
    assert len(body["customer_debt"]["customers"]) == 1
    assert body["customer_debt"]["customers"][0]["customer"] == "John"
    assert body["customer_debt"]["customers"][0]["amount"] == 200.0
    assert body["customer_debt"]["customers"][0]["currency"] == "USD"
