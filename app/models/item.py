from sqlalchemy import String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from ..db import Base

class Item(Base):
    __tablename__ = "items"
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(String(500), default=None)

