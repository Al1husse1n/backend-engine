from typing import Any

from app.services.events.base import reject_if, require_fields
from app.services.normalization import (
    as_number,
    as_non_empty_string,
    format_number,
    normalize_date,
)


class InventoryAdjustmentHandler:
    event_type = "inventory_adjustment"

    def validate(self, data: dict[str, Any]) -> dict[str, Any]:
        require_fields(
            data,
            ["item", "quantity", "reason"],
            {
                "item": "Which item should be adjusted?",
                "quantity": "By how much should inventory change?",
                "reason": "Why is inventory being adjusted?",
            },
        )
        item = as_non_empty_string(data.get("item"), "item")
        quantity = as_number(data.get("quantity"), "quantity")
        reason = as_non_empty_string(data.get("reason"), "reason")
        reject_if(quantity == 0, "Quantity must not be zero.")

        normalized = dict(data)
        normalized.update(
            {
                "item": item,
                "quantity": quantity,
                "reason": reason,
                "date": normalize_date(data.get("date")),
            }
        )
        return normalized

    def success_message(self, data: dict[str, Any]) -> str:
        quantity = data["quantity"]
        direction = "increased" if quantity > 0 else "decreased"
        return (
            f"Inventory adjustment recorded: {data['item']} {direction} by "
            f"{format_number(abs(quantity))}."
        )
