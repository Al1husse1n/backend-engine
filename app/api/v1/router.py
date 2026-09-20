from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_db
from app.schemas.agent_event import (
    EventRecordRequest, 
    EventRecordSuccessResponse, 
    QueryRequest, 
    QueryResponse
)
from app.services.events.sale_service import process_sale_event
from app.services.analytics_service import execute_deterministic_query

router = APIRouter()

@router.post("/events", status_code=status.HTTP_201_CREATED, response_model=EventRecordSuccessResponse)
async def record_event(payload: EventRecordRequest, db: AsyncSession = Depends(get_db)):
    if payload.event_type == "sale":
        recorded = await process_sale_event(
            db, payload.business_id, payload.language, payload.data.model_dump()
        )
    else:
        recorded = {
            "id": "evt_generic",
            "event_type": payload.event_type,
            "data": payload.data.model_dump()
        }

    return EventRecordSuccessResponse(
        success=True,
        event=recorded,
        message=f"{payload.event_type.capitalize()} recorded successfully."
    )

@router.post("/query", response_model=QueryResponse)
async def query_business_info(payload: QueryRequest, db: AsyncSession = Depends(get_db)):
    out = await execute_deterministic_query(db, payload.business_id, payload.query)
    return QueryResponse(
        success=True,
        query_type=out["query_type"],
        result=out["result"],
        message=out["message"]
    )