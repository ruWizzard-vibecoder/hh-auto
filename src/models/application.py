from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (
        UniqueConstraint("vacancy_id", "resume_id", name="uq_application_vacancy_resume"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    vacancy_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("vacancies.id"), index=True
    )
    cover_letter_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("cover_letters.id")
    )
    resume_id: Mapped[str] = mapped_column(String(50))
    hh_negotiation_id: Mapped[str | None] = mapped_column(String(50))

    # Status: sent / viewed / invited / declined / offer
    status: Mapped[str] = mapped_column(String(50), default="sent", index=True)
    hh_status: Mapped[str | None] = mapped_column(String(100))

    applied_via: Mapped[str] = mapped_column(String(20), default="api")
    employer_message: Mapped[str | None] = mapped_column(Text)
    last_status_check: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    applied_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    vacancy: Mapped["Vacancy"] = relationship(back_populates="applications")
    cover_letter: Mapped["CoverLetter"] = relationship()
