from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


class CoverLetter(Base):
    __tablename__ = "cover_letters"

    id: Mapped[int] = mapped_column(primary_key=True)
    vacancy_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("vacancies.id"), index=True
    )
    resume_id: Mapped[str] = mapped_column(String(50))

    # AI generation
    generated_text: Mapped[str] = mapped_column(Text)
    generation_prompt: Mapped[str | None] = mapped_column(Text)
    model_used: Mapped[str | None] = mapped_column(String(100))
    generation_cost_cents: Mapped[float | None] = mapped_column(Float)

    # Approval workflow: pending / approved / edited / rejected / sent / failed
    status: Mapped[str] = mapped_column(String(50), default="pending", index=True)
    edited_text: Mapped[str | None] = mapped_column(Text)
    rejection_reason: Mapped[str | None] = mapped_column(Text)

    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    vacancy: Mapped["Vacancy"] = relationship(back_populates="cover_letters")
