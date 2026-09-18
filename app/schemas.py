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
