from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class DailySummary(Base):
    __tablename__ = "daily_summaries"

    id: Mapped[int] = mapped_column(primary_key=True)
    summary_date: Mapped[date] = mapped_column(Date, unique=True, index=True)

    # Counts
    vacancies_discovered: Mapped[int] = mapped_column(Integer, default=0)
    vacancies_scored: Mapped[int] = mapped_column(Integer, default=0)
    letters_generated: Mapped[int] = mapped_column(Integer, default=0)
    letters_approved: Mapped[int] = mapped_column(Integer, default=0)
    applications_sent: Mapped[int] = mapped_column(Integer, default=0)
    responses_received: Mapped[int] = mapped_column(Integer, default=0)

    # AI-generated content
    summary_text: Mapped[str] = mapped_column(Text)  # Full markdown summary
    top_vacancies: Mapped[dict | None] = mapped_column(JSONB)  # Top 5 most promising
    interview_prep: Mapped[dict | None] = mapped_column(JSONB)  # Prep tips per vacancy
    insights: Mapped[str | None] = mapped_column(Text)  # Market trends, observations

    # Cost tracking
    avg_relevance_score: Mapped[float | None] = mapped_column(Float)
    model_used: Mapped[str | None] = mapped_column(String(100))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
