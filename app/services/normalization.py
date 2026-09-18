from datetime import date, datetime
from typing import Any

DEFAULT_CURRENCY = "ETB"


def normalize_key(value: str) -> str:
    return " ".join(value.strip().lower().split())


def is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def as_number(value: Any, field: str) -> int | float:
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{field} must be a number.")
    if isinstance(value, str):
        cleaned = value.replace(",", "").strip()
        if not cleaned:
            raise ValueError(f"{field} must be a number.")
        value = cleaned
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a number.") from exc
    if number != number:  # NaN
        raise ValueError(f"{field} must be a number.")
    if number.is_integer():
        return int(number)
    return number


def as_non_empty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required.")
    return value.strip()


def optional_string(value: Any, field: str) -> str | None:
    if is_blank(value):
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string or null.")
    return value.strip()


def normalize_date(value: Any) -> str:
    if is_blank(value):
        return date.today().isoformat()
    if isinstance(value, date) and not isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, str):
        text = value.strip()
        try:
            return date.fromisoformat(text).isoformat()
        except ValueError as exc:
            raise ValueError("date must be an ISO date (YYYY-MM-DD).") from exc
    raise ValueError("date must be an ISO date (YYYY-MM-DD).")


def normalize_currency(value: Any) -> str:
    if is_blank(value):
        return DEFAULT_CURRENCY
    if not isinstance(value, str):
        raise ValueError("currency must be a string.")
    currency = value.strip().upper()
    if not currency:
        return DEFAULT_CURRENCY
    return currency


def format_number(value: int | float) -> str:
    if isinstance(value, int) or float(value).is_integer():
        return str(int(value))
    return str(value)


def format_money(amount: int | float, currency: str) -> str:
    if isinstance(amount, float) and not amount.is_integer():
        return f"{amount:,.2f} {currency}"
    return f"{int(amount):,} {currency}"
