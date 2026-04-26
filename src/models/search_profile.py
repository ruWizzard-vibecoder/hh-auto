from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class SearchProfile(Base):
    __tablename__ = "search_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    search_text: Mapped[str | None] = mapped_column(String(1000))
    area_id: Mapped[int | None] = mapped_column(Integer)  # 2 = SPb
    experience: Mapped[str | None] = mapped_column(String(50))
    employment: Mapped[str | None] = mapped_column(String(50))
    schedule: Mapped[str | None] = mapped_column(String(50))
    salary_from: Mapped[int | None] = mapped_column(Integer)
    salary_to: Mapped[int | None] = mapped_column(Integer)
    salary_currency: Mapped[str] = mapped_column(String(10), default="RUR")
    only_with_salary: Mapped[bool] = mapped_column(Boolean, default=False)
    professional_role_ids: Mapped[dict | None] = mapped_column(JSONB)
    search_field: Mapped[str] = mapped_column(String(50), default="name")
    order_by: Mapped[str] = mapped_column(String(50), default="publication_time")
    min_relevance_score: Mapped[float] = mapped_column(Float, default=0.5)
    resume_id: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )
