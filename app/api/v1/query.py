from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.dependencies import get_authenticated_business_id
from app.db import get_db
from app.errors import ValidationFailed
from app.schemas import QueryRequest, QuerySuccessResponse
from app.services.query import answer_query

router = APIRouter()


@router.post("/query", response_model=QuerySuccessResponse)
def query_business(
    payload: QueryRequest,
    db: Session = Depends(get_db),
    business_id: str = Depends(get_authenticated_business_id),
) -> QuerySuccessResponse:
    if not payload.query.strip():
        raise ValidationFailed("query is required.")

    answered = answer_query(
        db,
        business_id,
        payload.query,
        language=payload.language,
    )
    return QuerySuccessResponse(
        query_type=answered["query_type"],
        result=answered["result"],
        message=answered["message"],
    )
