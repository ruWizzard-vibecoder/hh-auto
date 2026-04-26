"""API endpoints for resume management."""

import asyncio
import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db, async_session
from src.models.resume import Resume

logger = logging.getLogger("hh-auto.resumes_api")

router = APIRouter(prefix="/api/resumes")

# Seed data for 4 resumes
RESUME_SEED = [
    {
        "hh_id": "7d535317ff0ec1b82e0039ed1f554767455935",
        "title": "AI/Automation Engineer",
        "short_name": "AI/Auto",
        "is_primary": True,
        "rotation_priority": 0,
        "focus_keywords": {
            "title_keywords": [
                "ai", "ml", "machine learning", "automation", "llm",
                "data engineer", "python developer", "backend",
                "искусственный интеллект", "автоматизация", "разработчик python",
            ],
            "skill_keywords": [
                "python", "fastapi", "pytorch", "tensorflow", "langchain",
                "docker", "postgresql", "redis", "celery", "asyncio",
                "ci/cd", "git", "linux", "aws", "gcp",
            ],
            "description_keywords": [
                "neural network", "deep learning", "nlp", "cv", "api",
                "microservices", "etl", "pipeline", "deployment",
                "нейросет", "обучение", "модел", "данн",
            ],
        },
    },
    {
        "hh_id": "e59a5601ff101870060039ed1f6d7a386f6e69",
        "title": "AI-автоматизатор (RPA, n8n, ETL)",
        "short_name": "RPA",
        "is_primary": False,
        "rotation_priority": 1,
        "focus_keywords": {
            "title_keywords": [
                "rpa", "автоматизация", "etl", "интеграция", "n8n",
                "бизнес-процесс", "системный аналитик", "аналитик",
                "process automation", "integration", "workflow",
            ],
            "skill_keywords": [
                "n8n", "zapier", "make", "power automate", "uipath",
                "sql", "api", "rest", "python", "javascript",
                "1c", "bitrix", "amocrm", "excel", "vba",
            ],
            "description_keywords": [
                "автоматиз", "процесс", "интеграц", "отчёт", "crm",
                "erp", "workflow", "бизнес", "оптимиз", "рутин",
                "automat", "process", "integrat", "report",
            ],
        },
    },
    {
        "hh_id": "fa234e6aff10186eb20039ed1f7131794a756c",
        "title": "Vibe Coder (prompt engineer, AI startups)",
        "short_name": "Vibe",
        "is_primary": False,
        "rotation_priority": 2,
        "focus_keywords": {
            "title_keywords": [
                "prompt engineer", "ai engineer", "startup", "product",
                "fullstack", "full-stack", "фулстек", "продукт",
                "r&d", "research", "исследовани",
            ],
            "skill_keywords": [
                "chatgpt", "claude", "openai", "anthropic", "langchain",
                "prompt", "rag", "vector", "embedding", "fine-tuning",
                "react", "next.js", "typescript", "node.js",
            ],
            "description_keywords": [
                "startup", "стартап", "product", "продукт", "mvp",
                "prompt", "генерат", "чат-бот", "chatbot", "agent",
                "агент", "ai-first", "rapid", "прототип",
            ],
        },
    },
    {
        "hh_id": "be67ae04ff10186d490039ed1f447a74516575",
        "title": "No-code + AI Solutions",
        "short_name": "NoCode",
        "is_primary": False,
        "rotation_priority": 3,
        "focus_keywords": {
            "title_keywords": [
                "no-code", "low-code", "nocode", "consultant", "консультант",
                "ai solutions", "digital", "цифров", "трансформац",
                "внедрение", "implementation",
            ],
            "skill_keywords": [
                "bubble", "webflow", "tilda", "notion", "airtable",
                "chatgpt", "midjourney", "ai", "figma", "canva",
                "google sheets", "zapier", "make", "telegram bot",
            ],
            "description_keywords": [
                "no-code", "low-code", "без кода", "консульт", "внедр",
                "обучени", "тренинг", "digital", "цифров", "чат-бот",
                "telegram", "бот", "автоматиз", "презентац",
            ],
        },
    },
]


@router.get("")
async def list_resumes(db: AsyncSession = Depends(get_db)):
    """List all resumes with their status."""
    result = await db.execute(select(Resume).order_by(Resume.rotation_priority))
    resumes = list(result.scalars().all())
    return [
        {
            "id": r.id,
            "hh_id": r.hh_id,
            "title": r.title,
            "short_name": r.short_name,
            "is_primary": r.is_primary,
            "visibility_status": r.visibility_status,
            "last_rotated_at": r.last_rotated_at.isoformat() if r.last_rotated_at else None,
            "rotation_priority": r.rotation_priority,
        }
        for r in resumes
    ]


@router.post("/seed")
async def seed_resumes(db: AsyncSession = Depends(get_db)):
    """Seed the 4 resumes with focus keywords. Safe to call multiple times."""
    created = 0
    updated = 0
    for data in RESUME_SEED:
        result = await db.execute(
            select(Resume).where(Resume.hh_id == data["hh_id"])
        )
        existing = result.scalar_one_or_none()
        if existing:
            existing.title = data["title"]
            existing.short_name = data["short_name"]
            existing.is_primary = data["is_primary"]
            existing.focus_keywords = data["focus_keywords"]
            existing.rotation_priority = data["rotation_priority"]
            updated += 1
        else:
            resume = Resume(
                hh_id=data["hh_id"],
                title=data["title"],
                short_name=data["short_name"],
                is_primary=data["is_primary"],
                focus_keywords=data["focus_keywords"],
                rotation_priority=data["rotation_priority"],
                visibility_status="unknown",
            )
            db.add(resume)
            created += 1

    await db.commit()
    return JSONResponse({"created": created, "updated": updated})


@router.post("/rotate")
async def trigger_rotation(db: AsyncSession = Depends(get_db)):
    """Manually trigger resume rotation."""
    from src.services.hh_auth import ensure_logged_in
    from src.services.hh_client import HHClient
    from src.services.hh_browser import get_browser
    from src.services.pipeline import Pipeline

    async def _run():
        if not await ensure_logged_in():
            logger.warning("Not logged in to hh.ru, cannot rotate")
            return
        async with async_session() as session:
            client = HHClient()
            try:
                pipeline = Pipeline(session, client, get_browser())
                await pipeline.run_resume_rotation()
            finally:
                await client.close()

    asyncio.create_task(_run())
    return JSONResponse({"status": "rotation_started"})


async def auto_seed_resumes():
    """Auto-seed resumes on startup if table is empty."""
    async with async_session() as db:
        count = (await db.execute(select(Resume))).scalars().all()
        if len(count) == 0:
            logger.info("No resumes found, auto-seeding 4 resumes")
            for data in RESUME_SEED:
                resume = Resume(
                    hh_id=data["hh_id"],
                    title=data["title"],
                    short_name=data["short_name"],
                    is_primary=data["is_primary"],
                    focus_keywords=data["focus_keywords"],
                    rotation_priority=data["rotation_priority"],
                    visibility_status="unknown",
                )
                db.add(resume)
            await db.commit()
            logger.info("Auto-seeded 4 resumes")
        else:
            logger.info(f"Found {len(count)} resumes, skipping auto-seed")
