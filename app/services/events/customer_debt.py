from typing import Any

from app.services.events.base import reject_if, require_fields
from app.services.normalization import (
    as_number,
    as_non_empty_string,
    format_number,
    normalize_currency,
    normalize_date,
)

DEBT_DIRECTIONS = {"owed_to_business", "owed_by_business"}


class CustomerDebtHandler:
    event_type = "customer_debt"

    def validate(self, data: dict[str, Any]) -> dict[str, Any]:
        require_fields(
            data,
            ["customer", "amount", "direction"],
            {
                "customer": "Which customer is this debt for?",
                "amount": "What amount is owed?",
                "direction": "Does the customer owe the business, or does the business owe the customer?",
            },
        )
        customer = as_non_empty_string(data.get("customer"), "customer")
        amount = as_number(data.get("amount"), "amount")
        reject_if(amount <= 0, "Amount must be greater than zero.")

        direction = data.get("direction")
        if not isinstance(direction, str) or direction.strip() not in DEBT_DIRECTIONS:
            raise ValueError(
                "direction must be 'owed_to_business' or 'owed_by_business'."
            )

        normalized = dict(data)
        normalized.update(
            {
                "customer": customer,
                "amount": amount,
                "currency": normalize_currency(data.get("currency")),
                "direction": direction.strip(),
                "date": normalize_date(data.get("date")),
            }
        )
        return normalized

    def success_message(self, data: dict[str, Any]) -> str:
        amount = f"{format_number(data['amount'])} {data['currency']}"
        if data["direction"] == "owed_to_business":
            return f"Customer debt recorded: {data['customer']} owes {amount}."
        return f"Customer debt recorded: business owes {data['customer']} {amount}."
