from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class Resume(Base):
    __tablename__ = "resumes"

    id: Mapped[int] = mapped_column(primary_key=True)
    hh_id: Mapped[str] = mapped_column(String(50), unique=True)
    title: Mapped[str] = mapped_column(String(500))
    short_name: Mapped[str] = mapped_column(String(100), default="")
    status: Mapped[str | None] = mapped_column(String(50))
    full_text: Mapped[str | None] = mapped_column(Text)

    # Multi-resume fields
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    focus_keywords: Mapped[dict | None] = mapped_column(JSONB)
    visibility_status: Mapped[str] = mapped_column(String(20), default="unknown")
    last_rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rotation_priority: Mapped[int] = mapped_column(Integer, default=0)

    last_touched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )
