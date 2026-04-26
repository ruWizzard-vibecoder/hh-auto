"""Keyword-based resume matching: pick the best resume for a vacancy."""

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.resume import Resume

logger = logging.getLogger("hh-auto.resume_matcher")


@dataclass
class ResumeMatch:
    resume_hh_id: str
    resume_title: str
    resume_short_name: str
    match_score: float
    matched_keywords: list[str]


def _score_resume(
    resume: Resume,
    vacancy_title: str,
    vacancy_skills: list[str] | None,
    vacancy_description: str | None,
) -> tuple[float, list[str]]:
    """Score a single resume against a vacancy."""
    if not resume.focus_keywords:
        return 0.0, []

    fk = resume.focus_keywords
    title_kws = fk.get("title_keywords", [])
    skill_kws = fk.get("skill_keywords", [])
    desc_kws = fk.get("description_keywords", [])

    score = 0.0
    matched = []
    title_lower = vacancy_title.lower()

    # Title keyword matching (weight: 0.4)
    title_hits = [kw for kw in title_kws if kw.lower() in title_lower]
    if title_hits:
        score += min(len(title_hits) * 0.15, 0.4)
        matched.extend(title_hits)

    # Skill keyword matching (weight: 0.35)
    if vacancy_skills:
        skills_lower = {s.lower() for s in vacancy_skills}
        skill_hits = [kw for kw in skill_kws if kw.lower() in skills_lower]
        if skill_hits:
            score += min(len(skill_hits) * 0.1, 0.35)
            matched.extend(skill_hits)

    # Description keyword matching (weight: 0.25)
    if vacancy_description:
        desc_lower = vacancy_description.lower()
        desc_hits = [kw for kw in desc_kws if kw.lower() in desc_lower]
        if desc_hits:
            score += min(len(desc_hits) * 0.05, 0.25)
            matched.extend(desc_hits)

    return min(score, 1.0), matched


async def match_resume(
    db: AsyncSession,
    vacancy_title: str,
    vacancy_skills: list[str] | None = None,
    vacancy_description: str | None = None,
) -> ResumeMatch:
    """Pick the best resume for a vacancy. Falls back to primary resume."""
    result = await db.execute(
        select(Resume).where(Resume.focus_keywords.isnot(None))
    )
    resumes = list(result.scalars().all())

    if not resumes:
        primary_result = await db.execute(
            select(Resume).where(Resume.is_primary == True).limit(1)
        )
        r = primary_result.scalar_one_or_none()
        if r:
            return ResumeMatch(r.hh_id, r.title, r.short_name or "", 0.0, [])
        return ResumeMatch("", "Unknown", "", 0.0, [])

    best_match = None
    best_score = -1.0

    for resume in resumes:
        score, matched = _score_resume(
            resume, vacancy_title, vacancy_skills, vacancy_description,
        )
        if score > best_score:
            best_score = score
            best_match = ResumeMatch(
                resume_hh_id=resume.hh_id,
                resume_title=resume.title,
                resume_short_name=resume.short_name or "",
                match_score=score,
                matched_keywords=matched,
            )

    # Fall back to primary if no strong signal
    if best_score < 0.1:
        for resume in resumes:
            if resume.is_primary:
                return ResumeMatch(
                    resume.hh_id, resume.title, resume.short_name or "", 0.0, []
                )

    return best_match
