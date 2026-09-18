from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import NeedsClarification
from app.models import Event
from app.services.normalization import DEFAULT_CURRENCY, format_money, format_number, normalize_key

PeriodKind = Literal["today", "week", "month", "all"]

UNCLEAR_QUERY_MESSAGE = (
    "I could not tell what you want to know. Try asking about sales, expenses, "
    "inventory, or money a customer owes you."
)

# Item names that collide with parser keywords are ignored as item matches.
RESERVED_ITEM_WORDS = {
    "today",
    "tonight",
    "week",
    "month",
    "left",
    "cost",
    "costs",
    "owe",
    "owes",
    "owed",
    "debt",
    "sales",
    "sale",
    "sell",
    "sold",
    "expense",
    "expenses",
    "purchase",
    "purchases",
    "buy",
    "bought",
    "buying",
    "stock",
    "money",
    "amount",
    "how",
    "many",
    "much",
    "who",
    "what",
    "record",
    "business",
    "supplier",
    "suppliers",
    "vendor",
    "vendors",
    "me",
    "my",
    "i",
}

CUSTOMER_STOPWORDS = {
    "the",
    "a",
    "an",
    "my",
    "our",
    "this",
    "that",
    "business",
    "shop",
    "i",
    "we",
}


@dataclass(frozen=True)
class QueryIntent:
    query_type: str
    period_kind: PeriodKind = "all"
    item: str | None = None
    customer: str | None = None


def period_bounds(kind: PeriodKind, today: date | None = None) -> tuple[date | None, date | None]:
    today = today or date.today()
    if kind == "today":
        return today, today
    if kind == "week":
        return today - timedelta(days=today.weekday()), today
    if kind == "month":
        return today.replace(day=1), today
    return None, None


def _detect_period(text: str) -> PeriodKind:
    if re.search(r"\btoday\b|\btonight\b", text):
        return "today"
    if re.search(r"\bthis week\b|\bthe week\b", text):
        return "week"
    if re.search(r"\bthis month\b|\bthe month\b", text):
        return "month"
    return "all"


def _is_english(language: str) -> bool:
    code = language.strip().lower().replace("_", "-")
    primary = code.split("-")[0]
    return primary in {"en", "eng", "english"}


def _unclear(message: str = UNCLEAR_QUERY_MESSAGE) -> NeedsClarification:
    return NeedsClarification(message, ["query"])


def _detect_customer(original: str) -> str | None:
    match = re.search(
        r"(?:how much does|does)\s+([A-Za-z][A-Za-z'-]*)\s+owe",
        original,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    name = match.group(1).strip()
    if name.lower() in CUSTOMER_STOPWORDS:
        return None
    return name


def _detect_item(text: str, known_items: list[str]) -> str | None:
    """Match items case-insensitively after collapsing whitespace.

    Known item names that are parser keywords (today, left, cost, owe, ...)
    are ignored so they cannot steal the query type or filter totals.
    """
    for item in sorted(known_items, key=len, reverse=True):
        key = normalize_key(item)
        if not key or key in RESERVED_ITEM_WORDS:
            continue
        if re.search(rf"\b{re.escape(item)}\b", text, flags=re.IGNORECASE):
            return item
    match = re.search(
        r"how many\s+([a-z0-9][a-z0-9\s-]{0,40}?)(?:\s+did|\s+do|\s+have|\s+left|\s+in|\?|$)",
        text,
    )
    if match:
        item = match.group(1).strip()
        item = re.sub(r"\b(did|do|have|left|in|stock|i)\b", "", item).strip()
        if item and normalize_key(item) not in RESERVED_ITEM_WORDS:
            return item
    return None


def parse_query(
    query: str,
    known_items: list[str] | None = None,
    language: str = "en",
) -> QueryIntent:
    """Map English text to a single QueryIntent, or ask for clarification.

    This function must not compute business totals. Calculations happen only
    after a confident intent is returned.
    """
    original = query.strip()
    if not original:
        raise NeedsClarification("What would you like to know?", ["query"])
    if not _is_english(language):
        raise _unclear(
            "Query interpretation currently supports English only. Please ask in English."
        )

    text = original.lower()
    period = _detect_period(text)
    item = _detect_item(text, known_items or [])
    customer = _detect_customer(original)

    sales = bool(re.search(r"\b(sold|sell|selling|sales|revenue)\b", text))
    purchase = bool(re.search(r"\b(bought|buy|buying|purchase|purchases|purchased)\b", text))
    expense_core = bool(re.search(r"\b(spent|spend|spending|expense|expenses)\b", text))
    cost_word = bool(re.search(r"\bcosts?\b", text))
    # "cost of my purchases" is a purchase question, not an operating expense.
    expense = expense_core or (cost_word and not purchase)
    inventory = bool(
        re.search(r"\b(in stock|on hand|inventory)\b", text)
        or re.search(r"\bhave left\b", text)
        or re.search(r"\bhow many\b.*\bleft\b", text)
        or (re.search(r"\bhow many\b", text) and not sales and not purchase)
    )
    leftover_sales = bool(
        sales
        and re.search(r"\bleft\b", text)
        and not re.search(r"\b(have left|in stock|on hand|how many)\b", text)
    )
    i_owe = bool(re.search(r"\b((who )?do i owe|i owe)\b", text))
    they_owe_me = bool(
        re.search(r"\b(owe me|owes me|who owes)\b", text) or customer is not None
    )
    supplier_side = bool(re.search(r"\b(supplier|suppliers|vendor|vendors)\b", text))
    debt_word = bool(re.search(r"\b(owe|owes|owed|debt|receivable)\b", text))
    top = bool(re.search(r"\b(biggest|largest|top)\b", text))

    if leftover_sales:
        raise _unclear(
            "I could not tell whether you are asking about sales totals or remaining inventory."
        )
    if i_owe or (debt_word and supplier_side):
        raise _unclear(
            "I could not tell who owes whom. Try asking who owes you, or how much a named customer owes you."
        )
    if purchase and expense_core:
        raise _unclear(
            "I could not tell whether you are asking about expenses or purchases."
        )
    if debt_word and not they_owe_me:
        raise _unclear(
            "I could not tell who owes whom. Try asking who owes you, or how much a named customer owes you."
        )

    signals: list[str] = []
    if they_owe_me and debt_word:
        signals.append("customer_debt")
    if inventory and not leftover_sales:
        signals.append("inventory_quantity")
    if sales:
        signals.append("sales_total")
    if expense:
        signals.append("expenses_total")
    if purchase:
        signals.append("purchases_total")
    if top and (expense or expense_core or cost_word):
        signals.append("expenses_top")

    # "how many X did I sell" is a sales question, not on-hand inventory.
    if "inventory_quantity" in signals and "sales_total" in signals:
        signals = [name for name in signals if name != "inventory_quantity"]
    # "biggest expenses" is more specific than a plain expense total.
    if "expenses_top" in signals and "expenses_total" in signals:
        signals = [name for name in signals if name != "expenses_total"]

    unique = list(dict.fromkeys(signals))
    if len(unique) != 1:
        raise _unclear()

    query_type = unique[0]
    if query_type == "inventory_quantity" and not item:
        raise NeedsClarification("Which item do you want the quantity for?", ["item"])
    if query_type == "customer_debt":
        return QueryIntent(query_type=query_type, customer=customer)
    if query_type in {"sales_total", "purchases_total"}:
        return QueryIntent(query_type=query_type, period_kind=period, item=item)
    if query_type in {"expenses_total", "expenses_top"}:
        return QueryIntent(query_type=query_type, period_kind=period)
    return QueryIntent(query_type=query_type, period_kind=period, item=item)


def _event_date(event: Event) -> str | None:
    value = event.data.get("date") if isinstance(event.data, dict) else None
    return value if isinstance(value, str) else None


def _in_period(event: Event, start: date | None, end: date | None) -> bool:
    if start is None and end is None:
        return True
    event_day = _event_date(event)
    if not event_day:
        return False
    if start and event_day < start.isoformat():
        return False
    if end and event_day > end.isoformat():
        return False
    return True


def _as_amount(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _pick_currency(events: list[Event]) -> str:
    currencies = {
        str(event.data.get("currency")).upper()
        for event in events
        if isinstance(event.data, dict) and event.data.get("currency")
    }
    if len(currencies) == 1:
        return currencies.pop()
    return DEFAULT_CURRENCY


def _period_result(start: date | None, end: date | None) -> dict[str, str] | None:
    if start is None or end is None:
        return None
    return {"start": start.isoformat(), "end": end.isoformat()}


def _period_phrase(kind: PeriodKind) -> str:
    if kind == "today":
        return " today"
    if kind == "week":
        return " this week"
    if kind == "month":
        return " this month"
    return ""


def _load_events(db: Session, business_id: str) -> list[Event]:
    return list(
        db.scalars(select(Event).where(Event.business_id == business_id)).all()
    )


def _known_items(events: list[Event]) -> list[str]:
    items: list[str] = []
    seen: set[str] = set()
    for event in events:
        name = event.data.get("item") if isinstance(event.data, dict) else None
        if not isinstance(name, str) or not name.strip():
            continue
        key = normalize_key(name)
        if key not in seen:
            seen.add(key)
            items.append(name.strip())
    return items


def _sum_amounts(events: list[Event], event_type: str, start: date | None, end: date | None, item: str | None = None) -> tuple[float, list[Event]]:
    matched: list[Event] = []
    total = 0.0
    item_key = normalize_key(item) if item else None
    for event in events:
        if event.event_type != event_type or not _in_period(event, start, end):
            continue
        if item_key:
            event_item = event.data.get("item") if isinstance(event.data, dict) else None
            if not isinstance(event_item, str) or normalize_key(event_item) != item_key:
                continue
        matched.append(event)
        total += _as_amount(event.data.get("amount"))
    return total, matched


def _inventory_quantity(events: list[Event], item: str) -> float:
    """On-hand quantity for one item, matched case-insensitively.

    purchase +quantity, sale -quantity, inventory_adjustment +signed quantity.
    """
    item_key = normalize_key(item)
    quantity = 0.0
    for event in events:
        event_item = event.data.get("item") if isinstance(event.data, dict) else None
        if not isinstance(event_item, str) or normalize_key(event_item) != item_key:
            continue
        qty = _as_amount(event.data.get("quantity"))
        if event.event_type == "purchase":
            quantity += qty
        elif event.event_type == "sale":
            quantity -= qty
        elif event.event_type == "inventory_adjustment":
            quantity += qty
    return quantity


def _customer_balances(events: list[Event]) -> dict[str, dict[str, Any]]:
    balances: dict[str, dict[str, Any]] = {}
    for event in events:
        if event.event_type != "customer_debt":
            continue
        name = event.data.get("customer")
        if not isinstance(name, str) or not name.strip():
            continue
        key = normalize_key(name)
        row = balances.setdefault(
            key,
            {
                "customer": name.strip(),
                "amount": 0.0,
                "currency": event.data.get("currency") or DEFAULT_CURRENCY,
            },
        )
        amount = _as_amount(event.data.get("amount"))
        direction = event.data.get("direction")
        if direction == "owed_to_business":
            row["amount"] += amount
        elif direction == "owed_by_business":
            row["amount"] -= amount
        row["customer"] = name.strip()
        if event.data.get("currency"):
            row["currency"] = event.data["currency"]
    return balances


def answer_query(
    db: Session,
    business_id: str,
    query: str,
    language: str = "en",
) -> dict[str, Any]:
    events = _load_events(db, business_id.strip())
    intent = parse_query(query, known_items=_known_items(events), language=language)
    start, end = period_bounds(intent.period_kind)
    period = _period_result(start, end)

    if intent.query_type == "sales_total":
        total, matched = _sum_amounts(events, "sale", start, end, intent.item)
        currency = _pick_currency(matched)
        quantity = sum(_as_amount(event.data.get("quantity")) for event in matched)
        result: dict[str, Any] = {
            "amount": int(total) if float(total).is_integer() else total,
            "currency": currency,
            "count": len(matched),
        }
        if period:
            result["period"] = period
        if intent.item:
            result["item"] = intent.item
            result["quantity"] = int(quantity) if float(quantity).is_integer() else quantity
        item_bit = f" of {intent.item}" if intent.item else ""
        message = f"You sold {format_money(total, currency)}{item_bit}{_period_phrase(intent.period_kind)}."
        return {"query_type": "sales_total", "result": result, "message": message}

    if intent.query_type == "expenses_total":
        total, matched = _sum_amounts(events, "expense", start, end)
        currency = _pick_currency(matched)
        result = {
            "amount": int(total) if float(total).is_integer() else total,
            "currency": currency,
            "count": len(matched),
        }
        if period:
            result["period"] = period
        message = f"You spent {format_money(total, currency)}{_period_phrase(intent.period_kind)}."
        return {"query_type": "expenses_total", "result": result, "message": message}

    if intent.query_type == "purchases_total":
        total, matched = _sum_amounts(events, "purchase", start, end, intent.item)
        currency = _pick_currency(matched)
        result = {
            "amount": int(total) if float(total).is_integer() else total,
            "currency": currency,
            "count": len(matched),
        }
        if period:
            result["period"] = period
        if intent.item:
            result["item"] = intent.item
        item_bit = f" of {intent.item}" if intent.item else ""
        message = f"You spent {format_money(total, currency)} on purchases{item_bit}{_period_phrase(intent.period_kind)}."
        return {"query_type": "purchases_total", "result": result, "message": message}

    if intent.query_type == "expenses_top":
        matched = [
            event
            for event in events
            if event.event_type == "expense" and _in_period(event, start, end)
        ]
        ranked = sorted(matched, key=lambda event: _as_amount(event.data.get("amount")), reverse=True)
        expenses = [
            {
                "description": event.data.get("description"),
                "amount": event.data.get("amount"),
                "currency": event.data.get("currency") or DEFAULT_CURRENCY,
                "date": event.data.get("date"),
            }
            for event in ranked[:5]
        ]
        result = {"expenses": expenses}
        if period:
            result["period"] = period
        if expenses:
            top = expenses[0]
            message = (
                f"Your biggest expense{_period_phrase(intent.period_kind)} was "
                f"{top['description']} at {format_money(_as_amount(top['amount']), str(top['currency']))}."
            )
        else:
            message = f"No expenses were recorded{_period_phrase(intent.period_kind)}."
        return {"query_type": "expenses_top", "result": result, "message": message}

    if intent.query_type == "inventory_quantity":
        assert intent.item is not None
        quantity = _inventory_quantity(events, intent.item)
        qty = int(quantity) if float(quantity).is_integer() else quantity
        result = {"item": intent.item, "quantity": qty}
        message = f"You have {format_number(qty)} {intent.item} left."
        return {"query_type": "inventory_quantity", "result": result, "message": message}

    if intent.query_type == "customer_debt":
        balances = _customer_balances(events)
        if intent.customer:
            key = normalize_key(intent.customer)
            row = balances.get(key, {"customer": intent.customer, "amount": 0, "currency": DEFAULT_CURRENCY})
            amount = row["amount"]
            amount_out = int(amount) if float(amount).is_integer() else amount
            currency = str(row.get("currency") or DEFAULT_CURRENCY)
            result = {
                "customer": row["customer"],
                "amount": amount_out,
                "currency": currency,
                "direction": "owed_to_business" if amount >= 0 else "owed_by_business",
            }
            if amount > 0:
                message = f"{row['customer']} owes you {format_money(amount, currency)}."
            elif amount < 0:
                message = f"You owe {row['customer']} {format_money(abs(amount), currency)}."
            else:
                message = f"{row['customer']} does not currently owe you money."
            return {"query_type": "customer_debt", "result": result, "message": message}

        outstanding = [
            {
                "customer": row["customer"],
                "amount": int(row["amount"]) if float(row["amount"]).is_integer() else row["amount"],
                "currency": row["currency"],
            }
            for row in balances.values()
            if row["amount"] > 0
        ]
        outstanding.sort(key=lambda row: row["amount"], reverse=True)
        total = sum(_as_amount(row["amount"]) for row in outstanding)
        currency = outstanding[0]["currency"] if outstanding else DEFAULT_CURRENCY
        result = {
            "customers": outstanding,
            "total": int(total) if float(total).is_integer() else total,
            "currency": currency,
        }
        if outstanding:
            names = ", ".join(
                f"{row['customer']} ({format_money(row['amount'], str(row['currency']))})"
                for row in outstanding
            )
            message = f"These customers owe you money: {names}."
        else:
            message = "Nobody currently owes you money."
        return {"query_type": "customer_debt", "result": result, "message": message}

    raise NeedsClarification("I could not tell what you want to know.", ["query"])
