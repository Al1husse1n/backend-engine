from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import EventPayload, EventRequest, EventSuccessResponse
from app.services.events import process_event

router = APIRouter()


@router.post(
    "/events",
    status_code=status.HTTP_201_CREATED,
    response_model=EventSuccessResponse,
)
def create_event(
    payload: EventRequest,
    db: Session = Depends(get_db),
) -> EventSuccessResponse:
    event, message = process_event(db, payload)
    return EventSuccessResponse(
        event=EventPayload(
            id=event.id,
            event_type=event.event_type,
            data=event.data,
        ),
        message=message,
    )
