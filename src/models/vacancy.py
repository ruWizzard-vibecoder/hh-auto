from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


class Vacancy(Base):
    __tablename__ = "vacancies"

    id: Mapped[int] = mapped_column(primary_key=True)
    hh_id: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(500))
    company_name: Mapped[str | None] = mapped_column(String(500))
    company_id: Mapped[str | None] = mapped_column(String(50), index=True)
    salary_from: Mapped[int | None] = mapped_column(Integer)
    salary_to: Mapped[int | None] = mapped_column(Integer)
    salary_currency: Mapped[str | None] = mapped_column(String(10))
    salary_gross: Mapped[bool | None] = mapped_column(Boolean)
    area_name: Mapped[str | None] = mapped_column(String(255))
    experience: Mapped[str | None] = mapped_column(String(100))
    employment: Mapped[str | None] = mapped_column(String(100))
    schedule: Mapped[str | None] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    key_skills: Mapped[dict | None] = mapped_column(JSONB)
    url: Mapped[str | None] = mapped_column(String(1000))
    response_letter_required: Mapped[bool] = mapped_column(Boolean, default=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    employer_logo_url: Mapped[str | None] = mapped_column(String(1000))

    # Scoring
    relevance_score: Mapped[float | None] = mapped_column(Float)
    score_reasoning: Mapped[str | None] = mapped_column(Text)
    matched_skills: Mapped[dict | None] = mapped_column(JSONB)
    missing_skills: Mapped[dict | None] = mapped_column(JSONB)

    # Resume matching
    recommended_resume_id: Mapped[str | None] = mapped_column(String(50))

    # Pipeline status: discovered / scored / queued / applied / skipped / blacklisted
    status: Mapped[str] = mapped_column(String(50), default="discovered", index=True)
    search_profile_id: Mapped[int | None] = mapped_column(Integer)

    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    cover_letters: Mapped[list["CoverLetter"]] = relationship(back_populates="vacancy")
    applications: Mapped[list["Application"]] = relationship(back_populates="vacancy")
