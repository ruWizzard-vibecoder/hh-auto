"""AI-powered cover letter generation using Claude API."""

import logging
from dataclasses import dataclass
from html import unescape
import re

from src.config import settings
from src.services.ai_client import ai_complete
from src.services.vacancy_scorer import ScoringResult

logger = logging.getLogger("hh-auto.cover_letter")

SYSTEM_PROMPT_RU = """Ты пишешь сопроводительное письмо на русском языке для отклика на вакансию на hh.ru.
Кандидат — Алексей Аванов, AI/Automation Engineer.

Структура письма:
1. ПРИВЕТСТВИЕ — всегда начинай с приветствия. Варианты (чередуй!):
   - "Добрый день!"
   - "Здравствуйте!"
   - "Добрый день, коллеги!"
   - "Приветствую!"
2. ПРИЧИНА ИНТЕРЕСА — 1-2 предложения, почему именно эта вакансия привлекла. Будь конкретен: упомяни название компании, специфику задач или стека. НЕ пиши общие фразы типа "заинтересовала ваша вакансия".
3. РЕЛЕВАНТНЫЙ ОПЫТ — 2-3 конкретных проекта или навыка из резюме, которые напрямую отвечают требованиям. Упомяни конкретные технологии из вакансии.
4. ЗАВЕРШЕНИЕ — короткое, деловое: готовность обсудить детали, предложить созвон.

Правила тона:
- Пиши как живой человек: уверенно, конкретно, без канцелярита
- Длина: 150-250 слов
- РАЗНООБРАЗИЕ: каждое письмо должно отличаться структурой, формулировками, акцентами. Не начинай два письма одинаково. Меняй порядок аргументов, стиль подачи (где-то более деловой, где-то чуть свободнее)
- НЕ используй: "высокомотивированный", "командный игрок", "стрессоустойчивый", "быстрообучаемый", "нацелен на результат"
- НЕ пиши "меня зовут..." (имя будет в профиле)
- Если есть пробелы в навыках — НЕ упоминай их, фокус на сильных сторонах
- Кандидат открыт к full-time и part-time/проектной работе
- Если вакансия на подработку — подчеркни гибкость графика
- Если вакансия на full-time — пиши как обычно, не упоминай подработку

NDA-ограничения — СТРОГО СОБЛЮДАЙ:
- НИКОГДА не называй конкретных заказчиков по имени (a major international client, и т.д.)
- Вместо этого используй обобщённые описания:
  - a major international client → "крупный международный производитель электроники"
  - Другие enterprise-клиенты → "крупный B2B-заказчик", "международная компания", "enterprise-клиент"
- Проекты описывай по сути, без привязки к бренду: "AI-аналитика email-кампаний для международного производителя электроники", "AI-агенты для CRM enterprise-клиента"
- Это касается и резюме в контексте — если там упоминается a major international client, в письме замени на обобщение"""

SYSTEM_PROMPT_EN = """You write a cover letter in English for a job application on hh.ru.
Candidate: Alexey Avanov, AI/Automation Engineer.

Letter structure:
1. GREETING — always start with a greeting. Alternate between:
   - "Hello!"
   - "Hi there!"
   - "Good day!"
2. REASON FOR INTEREST — 1-2 sentences on why this specific role is appealing. Be specific: mention the company name, specific tasks or tech stack. NO generic phrases like "I'm interested in your vacancy".
3. RELEVANT EXPERIENCE — 2-3 specific projects or skills from the resume that directly match the requirements. Mention specific technologies from the job posting.
4. CLOSING — short, professional: readiness to discuss details, suggest a call.

Tone rules:
- Write like a real person: confident, specific, no corporate jargon
- Length: 150-250 words
- VARIETY: each letter should differ in structure, phrasing, and emphasis. Never start two letters the same way. Vary the order of arguments and presentation style
- DO NOT use: "highly motivated", "team player", "stress-resistant", "fast learner", "results-oriented"
- DO NOT write "my name is..." (name is in the profile)
- If there are skill gaps — DON'T mention them, focus on strengths
- Candidate is open to full-time and part-time/contract work
- For part-time roles — emphasize schedule flexibility
- For full-time roles — write normally, don't mention part-time

NDA restrictions — STRICTLY FOLLOW:
- NEVER name specific clients (a major international client, etc.)
- Use generalized descriptions instead:
  - a major international client → "a major international electronics manufacturer"
  - Other enterprise clients → "a large B2B client", "an international company", "an enterprise client"
- Describe projects by substance, not brand: "AI email analytics for a major electronics manufacturer", "AI agents for an enterprise CRM"
- This also applies to the resume context — if a major international client is mentioned there, replace with a generalization in the letter"""


def _detect_language(text: str) -> str:
    """Detect if vacancy text is primarily English or Russian."""
    if not text:
        return "ru"
    # Count Cyrillic vs Latin characters
    cyrillic = sum(1 for c in text if '\u0400' <= c <= '\u04ff')
    latin = sum(1 for c in text if ('a' <= c <= 'z') or ('A' <= c <= 'Z'))
    if latin > cyrillic:
        return "en"
    return "ru"


@dataclass
class CoverLetterDraft:
    text: str
    prompt_used: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0


def _clean_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


async def generate_cover_letter(
    title: str,
    company_name: str | None,
    description: str | None,
    key_skills: list[str] | None,
    resume_text: str,
    scoring: ScoringResult | None = None,
) -> CoverLetterDraft:
    """Generate a personalized cover letter using Claude API."""

    clean_desc = _clean_html(description) if description else "Описание не указано"
    skills_str = ", ".join(key_skills) if key_skills else "Не указаны"

    # Detect vacancy language from title + description
    lang = _detect_language(f"{title} {clean_desc}")
    system_prompt = SYSTEM_PROMPT_EN if lang == "en" else SYSTEM_PROMPT_RU
    logger.info(f"Detected vacancy language: {lang}")

    if lang == "en":
        scoring_context = ""
        if scoring:
            scoring_context = f"""
RELEVANCE ANALYSIS:
Matching skills: {', '.join(scoring.matched_skills) if scoring.matched_skills else 'n/a'}
Emphasis: {scoring.recommended_emphasis or 'n/a'}"""

        user_prompt = f"""Write a cover letter for this vacancy.

VACANCY:
Position: {title}
Company: {company_name or 'Not specified'}
Required skills: {skills_str}
Description: {clean_desc[:2000]}
{scoring_context}

CANDIDATE RESUME:
{resume_text[:3000]}

Return ONLY the letter text, no headers or explanations."""
    else:
        scoring_context = ""
        if scoring:
            scoring_context = f"""
АНАЛИЗ РЕЛЕВАНТНОСТИ:
Совпадающие навыки: {', '.join(scoring.matched_skills) if scoring.matched_skills else 'н/д'}
На что сделать акцент: {scoring.recommended_emphasis or 'н/д'}"""

        user_prompt = f"""Напиши сопроводительное письмо для этой вакансии.

ВАКАНСИЯ:
Должность: {title}
Компания: {company_name or 'Не указана'}
Требуемые навыки: {skills_str}
Описание: {clean_desc[:2000]}
{scoring_context}

РЕЗЮМЕ КАНДИДАТА:
{resume_text[:3000]}

Верни ТОЛЬКО текст письма, без заголовков и пояснений."""

    try:
        response = await ai_complete(
            prompt=user_prompt,
            system=system_prompt,
            model=settings.ai_model,
            max_tokens=4096,
        )

        logger.info(
            f"Cover letter generated for '{title}' at {company_name} "
            f"({response.input_tokens}+{response.output_tokens} tokens)"
        )

        return CoverLetterDraft(
            text=response.text,
            prompt_used=user_prompt,
            model=response.model,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
        )

    except Exception as e:
        logger.error(f"Cover letter generation failed: {e}")
        raise
