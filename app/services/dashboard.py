from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.business_time import BUSINESS_ZONE, business_today
from app.models import Event
from app.schemas import (
    CustomerDebtBreakdown,
    CustomerDebtMetric,
    DashboardResponse,
    ExpensesTodayMetric,
    InventoryMetric,
    LowStockItem,
    RecentActivityItem,
    SalesTodayMetric,
)
from app.services.normalization import DEFAULT_CURRENCY
from app.services.query import (
    _as_amount,
    _customer_balances,
    _normalize_item_name,
    _pick_currency,
    _require_single_currency,
)

DEFAULT_LOW_STOCK_THRESHOLD = 10.0
DEFAULT_RECENT_ACTIVITY_LIMIT = 10
DEFAULT_TOP_DEBTOR_LIMIT = 5


def _is_event_today(event: Event, today_date: date) -> bool:
    """Determine whether an event occurred on today_date using server calendar."""
    today_iso = today_date.isoformat()
    if isinstance(event.data, dict) and event.data.get("date"):
        try:
            return str(event.data["date"]).strip() == today_iso
        except Exception:
            pass
    if event.created_at:
        try:
            return event.created_at.astimezone(BUSINESS_ZONE).date() == today_date
        except Exception:
            return event.created_at.date() == today_date
    return False


def _event_description(event: Event) -> str:
    """Generate a clean, human-readable description for an event record."""
    data = event.data if isinstance(event.data, dict) else {}
    if data.get("description") and isinstance(data["description"], str) and data["description"].strip():
        return data["description"].strip()

    event_type = event.event_type
    if event_type == "sale":
        qty = data.get("quantity", "")
        item = data.get("item", "item")
        cust = data.get("customer")
        if cust:
            return f"Sale: {qty} {item} to {cust}".strip()
        return f"Sale: {qty} {item}".strip()

    if event_type == "expense":
        return str(data.get("description") or "Expense")

    if event_type == "purchase":
        qty = data.get("quantity", "")
        item = data.get("item", "item")
        sup = data.get("supplier")
        if sup:
            return f"Purchase: {qty} {item} from {sup}".strip()
        return f"Purchase: {qty} {item}".strip()

    if event_type == "customer_debt":
        cust = data.get("customer", "Customer")
        direction = data.get("direction")
        if direction == "owed_to_business":
            return f"Debt: {cust} owes business"
        return f"Debt: business owes {cust}"

    if event_type == "inventory_adjustment":
        item = data.get("item", "item")
        reason = data.get("reason")
        if reason:
            return f"Inventory adjustment: {item} ({reason})"
        return f"Inventory adjustment: {item}"

    return f"{event_type.replace('_', ' ').capitalize()}"


def compute_dashboard_metrics(
    db: Session,
    business_id: str,
    *,
    low_stock_threshold: float = DEFAULT_LOW_STOCK_THRESHOLD,
    recent_activity_limit: int = DEFAULT_RECENT_ACTIVITY_LIMIT,
    top_debtor_limit: int = DEFAULT_TOP_DEBTOR_LIMIT,
) -> DashboardResponse:
    """Compute aggregate dashboard metrics strictly scoped to business_id."""
    clean_biz_id = business_id.strip()

    # Load all events for this business ordered chronologically descending
    events = list(
        db.scalars(
            select(Event)
            .where(Event.business_id == clean_biz_id)
            .order_by(Event.created_at.desc(), Event.id.desc())
        ).all()
    )

    today = business_today()

    # 1. Today's Sales
    sales_today_events = [
        e for e in events
        if e.event_type == "sale" and _is_event_today(e, today)
    ]
    sales_currency = _pick_currency(sales_today_events)
    sales_amount = sum(
        _as_amount(e.data.get("amount"))
        for e in sales_today_events
        if isinstance(e.data, dict)
    )
    sales_today = SalesTodayMetric(
        amount=round(sales_amount, 2),
        currency=sales_currency,
        count=len(sales_today_events),
    )

    # 2. Today's Expenses
    expenses_today_events = [
        e for e in events
        if e.event_type == "expense" and _is_event_today(e, today)
    ]
    expenses_currency = _pick_currency(expenses_today_events)
    expenses_amount = sum(
        _as_amount(e.data.get("amount"))
        for e in expenses_today_events
        if isinstance(e.data, dict)
    )
    expenses_today = ExpensesTodayMetric(
        amount=round(expenses_amount, 2),
        currency=expenses_currency,
        count=len(expenses_today_events),
    )

    # 3. Outstanding Customer Debt
    customer_balances = _customer_balances(events)
    for r in customer_balances.values():
        if len(r.get("currencies", set())) > 1:
            _require_single_currency(r["currencies"])

    positive_debtors = [r for r in customer_balances.values() if r["amount"] > 0]
    debt_currency = _require_single_currency(
        {
            _require_single_currency(set(r.get("currencies") or []))
            for r in positive_debtors
        }
    )
    total_debt = sum(_as_amount(r["amount"]) for r in positive_debtors)

    positive_debtors.sort(key=lambda r: r["amount"], reverse=True)
    top_debtors = [
        CustomerDebtBreakdown(
            customer=r["customer"],
            amount=round(r["amount"], 2),
            currency=debt_currency,
        )
        for r in positive_debtors[:top_debtor_limit]
    ]
    customer_debt = CustomerDebtMetric(
        total=round(total_debt, 2),
        currency=debt_currency,
        customers=top_debtors,
    )

    # 4. Inventory Metric
    tracked_items: dict[str, dict[str, Any]] = {}
    for e in events:
        if e.event_type not in {"purchase", "sale", "inventory_adjustment"}:
            continue
        if not isinstance(e.data, dict):
            continue
        raw_item = e.data.get("item")
        if not isinstance(raw_item, str) or not raw_item.strip():
            continue
        item_name = raw_item.strip()
        norm_key = _normalize_item_name(item_name)

        if norm_key not in tracked_items:
            tracked_items[norm_key] = {
                "item": item_name,
                "quantity": 0.0,
                "unit": e.data.get("unit") or "units",
                "threshold": e.data.get("low_stock_threshold") or e.data.get("threshold"),
            }

        qty = _as_amount(e.data.get("quantity"))
        if e.event_type == "purchase":
            tracked_items[norm_key]["quantity"] += qty
        elif e.event_type == "sale":
            tracked_items[norm_key]["quantity"] -= qty
        elif e.event_type == "inventory_adjustment":
            tracked_items[norm_key]["quantity"] += qty

        if e.data.get("unit") and tracked_items[norm_key]["unit"] == "units":
            tracked_items[norm_key]["unit"] = str(e.data["unit"])
        if (e.data.get("low_stock_threshold") or e.data.get("threshold")) and tracked_items[norm_key]["threshold"] is None:
            tracked_items[norm_key]["threshold"] = _as_amount(
                e.data.get("low_stock_threshold") or e.data.get("threshold")
            )

    low_stock_items: list[LowStockItem] = []
    for _key, item_info in tracked_items.items():
        qty = item_info["quantity"]
        thresh = (
            item_info["threshold"]
            if item_info["threshold"] is not None
            else low_stock_threshold
        )
        if qty <= thresh:
            low_stock_items.append(
                LowStockItem(
                    item=item_info["item"],
                    quantity=round(qty, 2),
                    unit=str(item_info["unit"]),
                )
            )

    low_stock_items.sort(key=lambda x: x.quantity)
    inventory = InventoryMetric(
        total_items=len(tracked_items),
        low_stock_count=len(low_stock_items),
        items=low_stock_items,
    )

    # 5. Recent Activity (chronologically descending, up to recent_activity_limit)
    recent_activity_events = events[:recent_activity_limit]
    recent_activity = [
        RecentActivityItem(
            id=e.id,
            type=e.event_type,
            description=_event_description(e),
            amount=float(e.data["amount"]) if isinstance(e.data, dict) and e.data.get("amount") is not None else None,
            currency=str(e.data.get("currency")) if isinstance(e.data, dict) and e.data.get("currency") else (DEFAULT_CURRENCY if isinstance(e.data, dict) and e.data.get("amount") is not None else None),
            timestamp=e.created_at.isoformat() if e.created_at else "",
        )
        for e in recent_activity_events
    ]

    return DashboardResponse(
        sales_today=sales_today,
        expenses_today=expenses_today,
        customer_debt=customer_debt,
        inventory=inventory,
        recent_activity=recent_activity,
    )
