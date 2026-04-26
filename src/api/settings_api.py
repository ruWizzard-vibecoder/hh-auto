"""REST API for settings management (search profiles, company rules)."""

from fastapi import APIRouter, Depends, Form
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.models.search_profile import SearchProfile
from src.models.company_rule import CompanyRule

router = APIRouter(prefix="/api/settings")


# --- Search Profiles ---

@router.post("/profiles")
async def create_profile(
    name: str = Form(...),
    search_text: str = Form(""),
    area_id: int | None = Form(None),
    min_relevance_score: float = Form(0.5),
    resume_id: str = Form(""),
    schedule: str = Form(""),
    experience: str = Form(""),
    employment: str = Form(""),
    salary_from: int | None = Form(None),
    salary_to: int | None = Form(None),
    only_with_salary: bool = Form(False),
    db: AsyncSession = Depends(get_db),
):
    profile = SearchProfile(
        name=name,
        search_text=search_text or None,
        area_id=area_id,
        min_relevance_score=min_relevance_score,
        resume_id=resume_id or None,
        schedule=schedule or None,
        experience=experience or None,
        employment=employment or None,
        salary_from=salary_from,
        salary_to=salary_to,
        only_with_salary=only_with_salary,
    )
    db.add(profile)
    await db.commit()
    return JSONResponse({"status": "created", "id": profile.id})


@router.put("/profiles/{profile_id}")
async def update_profile(
    profile_id: int,
    name: str = Form(...),
    search_text: str = Form(""),
    area_id: int | None = Form(None),
    min_relevance_score: float = Form(0.5),
    resume_id: str = Form(""),
    schedule: str = Form(""),
    experience: str = Form(""),
    employment: str = Form(""),
    salary_from: int | None = Form(None),
    salary_to: int | None = Form(None),
    only_with_salary: bool = Form(False),
    is_active: bool = Form(False),
    db: AsyncSession = Depends(get_db),
):
    profile = await db.get(SearchProfile, profile_id)
    if not profile:
        return JSONResponse({"error": "not found"}, status_code=404)

    profile.name = name
    profile.search_text = search_text or None
    profile.area_id = area_id
    profile.min_relevance_score = min_relevance_score
    profile.resume_id = resume_id or None
    profile.schedule = schedule or None
    profile.experience = experience or None
    profile.employment = employment or None
    profile.salary_from = salary_from
    profile.salary_to = salary_to
    profile.only_with_salary = only_with_salary
    profile.is_active = is_active
    await db.commit()
    return JSONResponse({"status": "updated"})


# --- Company Rules ---

@router.post("/rules")
async def create_rule(
    rule_type: str = Form(...),
    match_type: str = Form(...),
    match_value: str = Form(...),
    reason: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    rule = CompanyRule(
        rule_type=rule_type,
        match_type=match_type,
        match_value=match_value,
        reason=reason or None,
    )
    db.add(rule)
    await db.commit()
    return JSONResponse({"status": "created", "id": rule.id})


@router.delete("/rules/{rule_id}")
async def delete_rule(rule_id: int, db: AsyncSession = Depends(get_db)):
    rule = await db.get(CompanyRule, rule_id)
    if not rule:
        return JSONResponse({"error": "not found"}, status_code=404)
    rule.is_active = False
    await db.commit()
    return JSONResponse({"status": "deleted"})
