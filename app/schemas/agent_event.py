from pydantic import BaseModel, Field
from typing import Optional, Any, Dict, List

class EventDataBase(BaseModel):
    item: Optional[str] = None
    quantity: Optional[float] = None
    amount: Optional[float] = None
    currency: Optional[str] = "ETB"
    customer: Optional[str] = None
    supplier: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    reason: Optional[str] = None
    direction: Optional[str] = None
    date: Optional[str] = None

class EventRecordRequest(BaseModel):
    business_id: str = Field(..., example="business_123")
    language: str = Field("en", example="en")
    event_type: str = Field(..., example="sale")
    data: EventDataBase

class EventRecordSuccessResponse(BaseModel):
    success: bool = True
    event: Dict[str, Any]
    message: str

class QueryRequest(BaseModel):
    business_id: str = Field(..., example="business_123")
    language: str = Field("en", example="en")
    query: str = Field(..., example="How much did I sell today?")

class QueryResponse(BaseModel):
    success: bool = True
    query_type: str
    result: Dict[str, Any]
    message: str