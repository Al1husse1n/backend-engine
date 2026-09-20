from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base
from app.models.base import AuditMixin

class Business(Base, AuditMixin):
    __tablename__ = "businesses"

    id: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    default_currency: Mapped[str] = mapped_column(String, default="ETB")