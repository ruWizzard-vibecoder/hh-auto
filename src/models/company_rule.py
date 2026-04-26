from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class CompanyRule(Base):
    __tablename__ = "company_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    # blacklist / whitelist
    rule_type: Mapped[str] = mapped_column(String(20))
    # company_name / company_id / keyword_in_title / keyword_in_description
    match_type: Mapped[str] = mapped_column(String(20))
    match_value: Mapped[str] = mapped_column(String(500))
    reason: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
