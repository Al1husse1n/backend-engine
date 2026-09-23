from sqlalchemy import String, Float, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import AuditMixin, RelationalBase

class InventoryItem(RelationalBase, AuditMixin):
    __tablename__ = "inventory_items"

    id: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    business_id: Mapped[str] = mapped_column(String, ForeignKey("businesses.id"), index=True, nullable=False)
    item_name: Mapped[str] = mapped_column(String, index=True, nullable=False)
    quantity: Mapped[float] = mapped_column(Float, default=0.0)
    unit_price: Mapped[float] = mapped_column(Float, default=0.0)

    __table_args__ = (
        UniqueConstraint("business_id", "item_name", name="uix_business_item"),
    )