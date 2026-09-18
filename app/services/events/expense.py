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


class ExpenseHandler:
    event_type = "expense"

    def validate(self, data: dict[str, Any]) -> dict[str, Any]:
        require_fields(
            data,
            ["description", "amount"],
            {
                "description": "What was the expense for?",
                "amount": "What amount was the expense?",
            },
        )
        description = as_non_empty_string(data.get("description"), "description")
        amount = as_number(data.get("amount"), "amount")
        reject_if(amount <= 0, "Amount must be greater than zero.")

        normalized = dict(data)
        normalized.update(
            {
                "description": description,
                "amount": amount,
                "currency": normalize_currency(data.get("currency")),
                "category": optional_string(data.get("category"), "category"),
                "date": normalize_date(data.get("date")),
            }
        )
        return normalized

    def success_message(self, data: dict[str, Any]) -> str:
        return (
            f"Expense recorded successfully: {format_number(data['amount'])} {data['currency']} "
            f"for {data['description']}."
        )
