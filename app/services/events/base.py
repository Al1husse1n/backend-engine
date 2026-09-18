from typing import Any, Protocol

from app.errors import NeedsClarification, ValidationFailed
from app.services.normalization import is_blank


class EventHandler(Protocol):
    event_type: str

    def validate(self, data: dict[str, Any]) -> dict[str, Any]:
        """Return normalized event data or raise NeedsClarification / ValidationFailed."""

    def success_message(self, data: dict[str, Any]) -> str:
        ...


def require_fields(
    data: dict[str, Any],
    fields: list[str],
    messages: dict[str, str],
) -> None:
    missing = [field for field in fields if is_blank(data.get(field))]
    if missing:
        message = messages.get(missing[0], f"Missing required field: {missing[0]}")
        raise NeedsClarification(message, missing)


def reject_if(condition: bool, message: str) -> None:
    if condition:
        raise ValidationFailed(message)
