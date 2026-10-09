from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SUPPORTED_EVENT_TYPES = (
    "sale",
    "expense",
    "purchase",
    "inventory_adjustment",
    "customer_debt",
)

Language = str
EventType = Literal[
    "sale",
    "expense",
    "purchase",
    "inventory_adjustment",
    "customer_debt",
]


class EventRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    business_id: str = Field(min_length=1)
    language: str = Field(min_length=1)
    event_type: str = Field(min_length=1)
    data: dict[str, Any] = Field(default_factory=dict)


class EventPayload(BaseModel):
    id: str
    event_type: str
    data: dict[str, Any]


class EventSuccessResponse(BaseModel):
    success: Literal[True] = True
    event: EventPayload
    message: str


class QueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    business_id: str = Field(min_length=1)
    language: str = Field(min_length=1)
    query: str = Field(min_length=1)


class QuerySuccessResponse(BaseModel):
    success: Literal[True] = True
    query_type: str
    result: dict[str, Any]
    message: str


class SalesTodayMetric(BaseModel):
    amount: float = 0.0
    currency: str = "ETB"
    count: int = 0


class ExpensesTodayMetric(BaseModel):
    amount: float = 0.0
    currency: str = "ETB"
    count: int = 0


class CustomerDebtBreakdown(BaseModel):
    customer: str
    amount: float
    currency: str = "ETB"


class CustomerDebtMetric(BaseModel):
    total: float = 0.0
    currency: str = "ETB"
    customers: list[CustomerDebtBreakdown] = Field(default_factory=list)


class LowStockItem(BaseModel):
    item: str
    quantity: float
    unit: str = "units"


class InventoryMetric(BaseModel):
    total_items: int = 0
    low_stock_count: int = 0
    items: list[LowStockItem] = Field(default_factory=list)


class RecentActivityItem(BaseModel):
    id: str
    type: str
    description: str
    amount: float | None = None
    currency: str | None = None
    timestamp: str


class DashboardResponse(BaseModel):
    sales_today: SalesTodayMetric
    expenses_today: ExpensesTodayMetric
    customer_debt: CustomerDebtMetric
    inventory: InventoryMetric
    recent_activity: list[RecentActivityItem] = Field(default_factory=list)
