"""Daily summary generation — AI analysis of the day's activity."""

import json
import logging
from datetime import date, datetime

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.config import settings
from src.services.ai_client import ai_complete
from src.models.vacancy import Vacancy
from src.models.application import Application
from src.models.cover_letter import CoverLetter
from src.models.daily_summary import DailySummary

logger = logging.getLogger("hh-auto.daily_summary")

SUMMARY_SYSTEM_PROMPT = """Ты — AI-ассистент по поиску работы. Твоя задача — составить ежедневный отчёт по активности на hh.ru.

Формат отчёта (на русском, Markdown):

## Итоги дня [дата]

### Обзор
- Краткая сводка по цифрам (отклики, просмотры, приглашения)
- Общая оценка продуктивности дня

### Топ-5 перспективных вакансий
Для каждой:
- Название и компания
- Почему эта вакансия перспективна
- Ключевые требования
- Твой скор совпадения

### Подготовка к собеседованиям
Для самых перспективных вакансий (score >= 0.7 или получены отклики):
- На какие вопросы готовиться
- Какие проекты из портфолио подчеркнуть
- Технические темы для повторения
- Что узнать о компании

### Наблюдения и рекомендации
- Какие навыки чаще всего требуют (тренды)
- Рекомендации по улучшению профиля/резюме
- Какие направления поиска стоит скорректировать

Будь конкретен. Не используй шаблонные фразы. Ссылайся на реальные данные из предоставленной статистики."""


async def generate_daily_summary(
    db: AsyncSession,
    target_date: date | None = None,
) -> DailySummary | None:
    """Generate comprehensive daily summary using Claude API."""

    if target_date is None:
        target_date = date.today()

    # Check if summary already exists
    existing = await db.execute(
        select(DailySummary).where(DailySummary.summary_date == target_date)
    )
    if existing.scalar_one_or_none():
        logger.info(f"Summary for {target_date} already exists, skipping")
        return None

    # --- Gather day's data ---

    # Vacancies discovered today
    vacancies_result = await db.execute(
        select(Vacancy).where(
            func.date(Vacancy.discovered_at) == target_date
        ).order_by(Vacancy.relevance_score.desc().nullslast())
    )
    vacancies = list(vacancies_result.scalars().all())

    # Applications sent today
    apps_result = await db.execute(
        select(Application)
        .options(selectinload(Application.vacancy))
        .where(func.date(Application.applied_at) == target_date)
    )
    applications = list(apps_result.scalars().all())

    # Cover letters generated today
    letters_result = await db.execute(
        select(CoverLetter)
        .options(selectinload(CoverLetter.vacancy))
        .where(func.date(CoverLetter.generated_at) == target_date)
    )
    letters = list(letters_result.scalars().all())

    # Status changes today (responses received)
    responses_result = await db.execute(
        select(Application)
        .options(selectinload(Application.vacancy))
        .where(
            and_(
                func.date(Application.updated_at) == target_date,
                Application.status.in_(["viewed", "invited", "offer"]),
            )
        )
    )
    responses = list(responses_result.scalars().all())

    # Counts
    vacancies_discovered = len(vacancies)
    vacancies_scored = len([v for v in vacancies if v.relevance_score is not None])
    letters_generated = len(letters)
    letters_approved = len([l for l in letters if l.status in ("approved", "edited", "sent")])
    applications_sent = len(applications)
    responses_received = len(responses)

    # If absolutely nothing happened, skip
    if vacancies_discovered == 0 and applications_sent == 0 and responses_received == 0:
        logger.info(f"No activity on {target_date}, skipping summary")
        return None

    # Average relevance score
    scores = [v.relevance_score for v in vacancies if v.relevance_score]
    avg_score = sum(scores) / len(scores) if scores else 0.0

    # --- Build context for AI ---

    # Top vacancies (by score)
    top_vacancies_data = []
    for v in vacancies[:10]:
        top_vacancies_data.append({
            "title": v.title,
            "company": v.company_name,
            "score": v.relevance_score,
            "salary": f"{v.salary_from or '?'}-{v.salary_to or '?'} {v.salary_currency or ''}".strip(),
            "schedule": v.schedule,
            "experience": v.experience,
            "key_skills": v.key_skills[:10] if v.key_skills else [],
            "matched_skills": v.matched_skills[:8] if v.matched_skills else [],
            "missing_skills": v.missing_skills[:5] if v.missing_skills else [],
            "score_reasoning": v.score_reasoning,
            "url": v.url,
            "status": v.status,
        })

    # Applications details
    apps_data = []
    for app in applications:
        v = app.vacancy
        apps_data.append({
            "title": v.title if v else "Unknown",
            "company": v.company_name if v else "Unknown",
            "status": app.status,
            "score": v.relevance_score if v else None,
        })

    # Responses details
    responses_data = []
    for r in responses:
        v = r.vacancy
        responses_data.append({
            "title": v.title if v else "Unknown",
            "company": v.company_name if v else "Unknown",
            "status": r.status,
            "employer_message": r.employer_message,
        })

    # All skills seen today (frequency)
    skills_counter: dict[str, int] = {}
    for v in vacancies:
        if v.key_skills:
            for skill in v.key_skills:
                skills_counter[skill] = skills_counter.get(skill, 0) + 1
    top_skills = sorted(skills_counter.items(), key=lambda x: x[1], reverse=True)[:20]

    # --- Call Claude API ---

    user_prompt = f"""Составь ежедневный отчёт за {target_date.strftime('%d.%m.%Y')}.

СТАТИСТИКА ДНЯ:
- Обнаружено вакансий: {vacancies_discovered}
- Оценено: {vacancies_scored}
- Сгенерировано писем: {letters_generated}
- Одобрено/отправлено: {letters_approved}
- Откликов отправлено: {applications_sent}
- Получено ответов: {responses_received}
- Средний скор релевантности: {avg_score:.0%}

ТОП-10 ВАКАНСИЙ ДНЯ (отсортированы по скору):
{json.dumps(top_vacancies_data, ensure_ascii=False, indent=2)}

ОТКЛИКИ ЗА ДЕНЬ:
{json.dumps(apps_data, ensure_ascii=False, indent=2)}

ПОЛУЧЕННЫЕ ОТВЕТЫ:
{json.dumps(responses_data, ensure_ascii=False, indent=2) if responses_data else 'Нет ответов за сегодня'}

САМЫЕ ВОСТРЕБОВАННЫЕ НАВЫКИ (по вакансиям дня):
{json.dumps(dict(top_skills), ensure_ascii=False)}

ПРОФИЛЬ КАНДИДАТА:
Алексей Аванов, AI/Automation Engineer. Ключевые навыки: Python, FastAPI, Claude API, GPT-4, LLM, RAG, Docker, PostgreSQL, n8n, React, TypeScript, Next.js.
7 проектов (5 в проде): AI-поиск авто, cosmodoc, калькулятор лазерной резки, SMS-аналитика, автоматизация маркетинга.

Ответь в формате JSON:
{{
    "summary_text": "Полный Markdown-отчёт по формату из системного промпта",
    "top_vacancies": [
        {{
            "title": "...",
            "company": "...",
            "score": 0.85,
            "why_promising": "почему перспективна",
            "url": "..."
        }}
    ],
    "interview_prep": [
        {{
            "vacancy_title": "...",
            "company": "...",
            "questions_to_prepare": ["вопрос 1", "вопрос 2"],
            "projects_to_highlight": ["проект 1"],
            "tech_topics_to_review": ["тема 1"],
            "company_research": "что узнать о компании"
        }}
    ],
    "insights": "Наблюдения по рынку и рекомендации"
}}"""

    try:
        response = await ai_complete(
            prompt=user_prompt,
            system=SUMMARY_SYSTEM_PROMPT,
            model=settings.ai_model,
            max_tokens=4000,
        )

        text = response.text
        # Parse JSON from response
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
        data = json.loads(text)

        summary = DailySummary(
            summary_date=target_date,
            vacancies_discovered=vacancies_discovered,
            vacancies_scored=vacancies_scored,
            letters_generated=letters_generated,
            letters_approved=letters_approved,
            applications_sent=applications_sent,
            responses_received=responses_received,
            summary_text=data.get("summary_text", ""),
            top_vacancies=data.get("top_vacancies"),
            interview_prep=data.get("interview_prep"),
            insights=data.get("insights"),
            avg_relevance_score=avg_score,
            model_used=response.model,
        )
        db.add(summary)
        await db.commit()

        logger.info(f"Daily summary generated for {target_date}")
        return summary

    except Exception as e:
        logger.error(f"Daily summary generation failed: {e}")
        # Save a fallback summary with just stats
        summary = DailySummary(
            summary_date=target_date,
            vacancies_discovered=vacancies_discovered,
            vacancies_scored=vacancies_scored,
            letters_generated=letters_generated,
            letters_approved=letters_approved,
            applications_sent=applications_sent,
            responses_received=responses_received,
            summary_text=_fallback_summary(
                target_date, vacancies_discovered, applications_sent,
                responses_received, avg_score, top_vacancies_data,
            ),
            top_vacancies=[
                {"title": v["title"], "company": v["company"], "score": v["score"], "url": v["url"]}
                for v in top_vacancies_data[:5]
            ],
            avg_relevance_score=avg_score,
        )
        db.add(summary)
        await db.commit()
        return summary


def _fallback_summary(
    target_date: date,
    discovered: int,
    sent: int,
    responses: int,
    avg_score: float,
    top_vacancies: list[dict],
) -> str:
    """Simple text summary when AI generation fails."""
    top_list = "\n".join(
        f"- **{v['title']}** @ {v['company']} (score: {v['score']:.0%})"
        for v in top_vacancies[:5]
    )
    return f"""## Итоги дня {target_date.strftime('%d.%m.%Y')}

### Обзор
- Обнаружено вакансий: {discovered}
- Отправлено откликов: {sent}
- Получено ответов: {responses}
- Средний скор: {avg_score:.0%}

### Топ вакансий
{top_list}

_AI-анализ недоступен, показана базовая статистика._
"""


def format_summary_for_telegram(summary: DailySummary) -> str:
    """Format summary for Telegram message (shorter, HTML)."""
    d = summary.summary_date.strftime("%d.%m.%Y")

    # Stats line
    stats = (
        f"<b>Daily Summary {d}</b>\n\n"
        f"Vacancies: {summary.vacancies_discovered} | "
        f"Applications: {summary.applications_sent} | "
        f"Responses: {summary.responses_received}\n"
        f"Avg score: {summary.avg_relevance_score:.0%}\n\n"
    )

    # Top vacancies
    top = ""
    if summary.top_vacancies:
        top = "<b>Top vacancies:</b>\n"
        for v in summary.top_vacancies[:5]:
            score = v.get("score", 0)
            score_str = f"{score:.0%}" if isinstance(score, (int, float)) else str(score)
            top += f"  {v.get('title', '?')} @ {v.get('company', '?')} ({score_str})\n"
        top += "\n"

    # Interview prep summary
    prep = ""
    if summary.interview_prep:
        prep = "<b>Prepare for interviews:</b>\n"
        for item in summary.interview_prep[:3]:
            prep += f"  {item.get('vacancy_title', '?')} — {item.get('company', '?')}\n"
            topics = item.get("tech_topics_to_review", [])
            if topics:
                prep += f"    Topics: {', '.join(topics[:3])}\n"
        prep += "\n"

    # Insights snippet
    insights = ""
    if summary.insights:
        # Truncate for Telegram
        ins = summary.insights[:300]
        if len(summary.insights) > 300:
            ins += "..."
        insights = f"<b>Insights:</b>\n{ins}\n"

    full = stats + top + prep + insights
    full += "\nFull report on dashboard: /summaries"
    return full
