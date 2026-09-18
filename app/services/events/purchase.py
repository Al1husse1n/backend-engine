from typing import Any

from app.services.events.base import reject_if, require_fields
from app.services.normalization import (
    as_number,
    as_non_empty_string,
    format_number,
    normalize_currency,
    normalize_date,
    optional_string,
)


class PurchaseHandler:
    event_type = "purchase"

    def validate(self, data: dict[str, Any]) -> dict[str, Any]:
        require_fields(
            data,
            ["item", "quantity", "amount"],
            {
                "item": "Which item was purchased?",
                "quantity": "How many were purchased?",
                "amount": "What amount was the purchase?",
            },
        )
        item = as_non_empty_string(data.get("item"), "item")
        quantity = as_number(data.get("quantity"), "quantity")
        amount = as_number(data.get("amount"), "amount")
        reject_if(quantity <= 0, "Quantity must be greater than zero.")
        reject_if(amount <= 0, "Amount must be greater than zero.")

        normalized = dict(data)
        normalized.update(
            {
                "item": item,
                "quantity": quantity,
                "amount": amount,
                "currency": normalize_currency(data.get("currency")),
                "supplier": optional_string(data.get("supplier"), "supplier"),
                "date": normalize_date(data.get("date")),
            }
        )
        return normalized

    def success_message(self, data: dict[str, Any]) -> str:
        return (
            f"Purchase recorded successfully: {format_number(data['quantity'])} {data['item']} "
            f"for {format_number(data['amount'])} {data['currency']}."
        )
