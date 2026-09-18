from __future__ import annotations

from uuid import uuid4

from sqlalchemy.orm import Session

from app.errors import NeedsClarification, ValidationFailed
from app.models import Event
from app.schemas import EventRequest, SUPPORTED_EVENT_TYPES
from app.services.events.base import EventHandler
from app.services.events.customer_debt import CustomerDebtHandler
from app.services.events.expense import ExpenseHandler
from app.services.events.inventory_adjustment import InventoryAdjustmentHandler
from app.services.events.purchase import PurchaseHandler
from app.services.events.sale import SaleHandler

_HANDLERS: dict[str, EventHandler] = {
    handler.event_type: handler
    for handler in (
        SaleHandler(),
        ExpenseHandler(),
        PurchaseHandler(),
        InventoryAdjustmentHandler(),
        CustomerDebtHandler(),
    )
}


def get_handler(event_type: str) -> EventHandler:
    handler = _HANDLERS.get(event_type)
    if handler is None:
        supported = ", ".join(SUPPORTED_EVENT_TYPES)
        raise ValidationFailed(
            f"Unsupported event_type '{event_type}'. Supported types: {supported}."
        )
    return handler


def process_event(db: Session, payload: EventRequest) -> tuple[Event, str]:
    if not payload.business_id.strip():
        raise ValidationFailed("business_id is required.")
    if not payload.language.strip():
        raise ValidationFailed("language is required.")
    if not isinstance(payload.data, dict):
        raise ValidationFailed("data must be an object.")

    handler = get_handler(payload.event_type.strip())
    try:
        normalized = handler.validate(payload.data)
    except ValueError as exc:
        raise ValidationFailed(str(exc)) from exc
    except NeedsClarification:
        raise

    event = Event(
        id=f"event_{uuid4()}",
        business_id=payload.business_id.strip(),
        event_type=handler.event_type,
        language=payload.language.strip(),
        data=normalized,
    )
    db.add(event)
    db.flush()
    return event, handler.success_message(normalized)
