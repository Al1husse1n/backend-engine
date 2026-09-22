import uuid
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.ledger import EventLog
from app.models.inventory import InventoryItem
from app.core.errors import BusinessRuleValidationError, NeedsClarificationError

async def process_sale_event(db: AsyncSession, business_id: str, language: str, data: dict) -> dict:
    item_name = data.get("item")
    amount = data.get("amount")
    quantity = data.get("quantity") or 1.0

    missing = []
    if not amount:
        missing.append("amount")
    if missing:
        raise NeedsClarificationError("What amount was the sale?", missing_fields=missing)

    if amount <= 0:
        raise BusinessRuleValidationError("Amount must be greater than zero.")

    # Deduct stock if item is specified
    if item_name:
        stmt = select(InventoryItem).where(
            InventoryItem.business_id == business_id,
            InventoryItem.item_name == item_name
        )
        res = await db.execute(stmt)
        inv = res.scalar_one_or_none()
        if inv:
            inv.quantity -= quantity

    event_id = f"evt_{uuid.uuid4().hex[:8]}"
    event_log = EventLog(
        id=event_id,
        business_id=business_id,
        event_type="sale",
        language=language,
        item=item_name,
        quantity=quantity,
        amount=amount,
        currency=data.get("currency", "ETB"),
        customer=data.get("customer"),
        event_date=datetime.strptime(data.get("date"), "%Y-%m-%d") if data.get("date") else datetime.utcnow()
    )
    db.add(event_log)
    await db.flush()

    return {
        "id": event_id,
        "event_type": "sale",
        "data": {
            "item": item_name,
            "quantity": quantity,
            "amount": amount,
            "currency": data.get("currency", "ETB"),
            "date": data.get("date") or datetime.utcnow().strftime("%Y-%m-%d")
        }
    }