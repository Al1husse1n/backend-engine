from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.dependencies import get_authenticated_business_id
from app.db import get_db
from app.schemas import DashboardResponse
from app.services.dashboard import compute_dashboard_metrics

router = APIRouter()


@router.get("/dashboard", response_model=DashboardResponse)
@router.get("/dashboard/", response_model=DashboardResponse, include_in_schema=False)
def get_dashboard(
    db: Session = Depends(get_db),
    business_id: str = Depends(get_authenticated_business_id),
) -> DashboardResponse:
    """Fetch aggregated business metrics and recent activity for the authenticated tenant."""
    return compute_dashboard_metrics(db=db, business_id=business_id)
