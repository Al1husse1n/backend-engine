from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime
from app.models.ledger import EventLog

async def execute_deterministic_query(db: AsyncSession, business_id: str, query_str: str) -> dict:
    q = query_str.lower()
    today_str = datetime.utcnow().strftime("%Y-%m-%d")

    if "sell" in q or "sold" in q or "sale" in q:
        stmt = select(func.sum(EventLog.amount)).where(
            EventLog.business_id == business_id,
            EventLog.event_type == "sale"
        )
        res = await db.execute(stmt)
        total = res.scalar() or 0.0

        return {
            "query_type": "sales_total",
            "result": {
                "amount": total,
                "currency": "ETB",
                "period": {"start": today_str, "end": today_str}
            },
            "message": f"You sold {total:,.2f} ETB today."
        }
    
    return {
        "query_type": "general_summary",
        "result": {"amount": 0.0, "currency": "ETB"},
        "message": "No query matches identified."
    }