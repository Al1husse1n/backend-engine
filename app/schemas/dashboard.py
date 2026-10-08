from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas import (
    CustomerDebtBreakdown,
    CustomerDebtMetric,
    DashboardResponse,
    ExpensesTodayMetric,
    InventoryMetric,
    LowStockItem,
    RecentActivityItem,
    SalesTodayMetric,
)

__all__ = [
    "SalesTodayMetric",
    "ExpensesTodayMetric",
    "CustomerDebtBreakdown",
    "CustomerDebtMetric",
    "LowStockItem",
    "InventoryMetric",
    "RecentActivityItem",
    "DashboardResponse",
]
