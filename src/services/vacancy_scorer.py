"""Two-tier vacancy scoring: fast rule-based + AI-powered deep scoring."""

import json
import logging
import re
from dataclasses import dataclass, field
from html import unescape

from src.config import settings
from src.services.ai_client import ai_complete

logger = logging.getLogger("hh-auto.scorer")

# Skills from Alexey's resume, grouped by relevance weight
AI_SKILLS = {
    "claude", "gpt", "llm", "openai", "anthropic", "rag", "vector",
    "prompt engineering", "ai", "ml", "machine learning", "nlp",
    "langchain", "dify", "flowise", "ollama", "weaviate",
}
DEV_SKILLS = {
    "python", "fastapi", "flask", "django", "node.js", "nodejs",
    "typescript", "javascript", "react", "next.js", "nextjs",
    "express", "nestjs", "nest.js", "docker", "postgresql", "postgres",
    "redis", "sql", "sqlalchemy", "prisma", "streamlit", "supabase",
    "trpc", "vite", "tailwind", "playwright", "electron",
}
DEVOPS_SKILLS = {
    "docker", "docker compose", "nginx", "linux", "devops",
    "ci/cd", "kubernetes", "k8s", "terraform", "ansible",
    "ssl", "certbot", "ssh", "vpn", "tailscale",
}
AUTOMATION_SKILLS = {
    "n8n", "automation", "etl", "rpa", "telegram bot",
    "api integration", "webhook", "cron", "scheduler",
    "no-code", "low-code", "zapier",
    "автоматизация", "нейросет", "нейронн",
}

ALL_SKILLS = AI_SKILLS | DEV_SKILLS | DEVOPS_SKILLS | AUTOMATION_SKILLS

# Keywords by target role tiers — different bonus levels
TIER1_TITLE_KEYWORDS = {
    # Прямое попадание: AI-инженер, автоматизация, no-code, vibe coder
    "ai engineer", "ml engineer", "automation engineer", "ai developer",
    "ai specialist", "ai/automation", "no-code", "low-code", "nocode", "lowcode",
    "n8n", "ai solutions", "автоматизация процессов", "vibe cod",
    "вайб-кодер", "вайб кодер", "ai интегратор", "ai архитектор",
    "ai-архитектор", "ai-интегратор",
    # Русские аналоги
    "ии-инженер", "ии-разработчик", "ии-автоматизатор", "ии-специалист",
    "инженер по ии", "специалист по ии", "разработчик ии", "автоматизатор",
    "автоматизация бизнеса",
}
TIER2_TITLE_KEYWORDS = {
    # Сильная позиция: AI-продукт, консультант, LLM, growth
    "ai product", "ai consultant", "technical consultant",
    "llm engineer", "llm developer", "prompt engineer",
    "data engineer", "ml ops", "mlops",
    "product engineer", "growth manager", "martech",
    "email автоматизация", "ai growth",
    # Русские аналоги
    "машинное обучение", "нейросет", "ии-консультант", "ии-аналитик",
}
TIER3_TITLE_KEYWORDS = {
    # Общие — только если есть AI/automation контекст в описании
    "python developer", "python разработчик", "разработчик python",
    "backend developer", "fullstack", "full-stack", "devops",
    "разработчик",
}
# Very short keywords that match too broadly — only match in title with word boundaries
EXACT_TITLE_KEYWORDS = {"ai", "ml", "llm", "ии"}

# Part-time / freelance keywords for bonus scoring
PARTTIME_KEYWORDS = {
    "частичная занятость", "подработка", "проектная работа",
    "разовое задание", "фриланс", "freelance", "part-time", "part time",
    "контракт", "contract", "временная", "совместительство",
}

# Region scoring by timezone proximity to Moscow (UTC+3)
PREFERRED_REGIONS = {
    # MSK (UTC+3) — Москва, СПб и ближайшие
    "москва", "санкт-петербург", "нижний новгород", "казань",
    "ростов-на-дону", "воронеж", "краснодар", "волгоград",
    "ярославль", "тула", "калуга", "рязань", "тверь",
    "архангельск", "мурманск", "калининград", "петрозаводск",
    "сочи", "ставрополь", "симферополь", "севастополь",
    # Ближнее зарубежье (MSK)
    "минск", "тбилиси", "ереван", "баку", "кишинёв",
}
NEARBY_REGIONS = {
    # MSK+1..+2 (UTC+4-5) — допустимая разница
    "самара", "ижевск", "саратов", "ульяновск", "оренбург",
    "екатеринбург", "челябинск", "уфа", "пермь", "тюмень",
    "курган", "магнитогорск", "сургут",
    # Ближнее зарубежье (UTC+5-6)
    "астана", "алматы", "ташкент", "бишкек",
}
MEDIUM_REGIONS = {
    # MSK+3..+4 (UTC+6-7) — ощутимая разница
    "омск", "новосибирск", "красноярск", "томск", "барнаул",
    "кемерово", "новокузнецк",
}
FAR_REGIONS = {
    # MSK+5+ (UTC+8-12) — большая разница во времени
    "иркутск", "чита", "улан-удэ",
    "якутск", "благовещенск",
    "хабаровск", "владивосток",
    "магадан", "южно-сахалинск",
    "петропавловск-камчатский", "анадырь",
}

# Red flags that indicate irrelevance
NEGATIVE_KEYWORDS = {
    "senior java", "c++", "c#", ".net", "ios", "android",
    "swift", "kotlin", "go developer", "golang", "scala",
    "php developer", "ruby", "salesforce", "1c", "1с",
    "бухгалтер", "юрист", "менеджер по продажам",
}


@dataclass
class ScoringResult:
    score: float  # 0.0 - 1.0
    reasoning: str
    matched_skills: list[str] = field(default_factory=list)
    missing_skills: list[str] = field(default_factory=list)
    recommended_emphasis: str = ""


def _clean_html(text: str) -> str:
    """Strip HTML tags from vacancy description."""
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_text_skills(text: str) -> set[str]:
    """Extract known skills mentioned in text."""
    text_lower = text.lower()
    found = set()
    for skill in ALL_SKILLS:
        if skill in text_lower:
            found.add(skill)
    return found


def _region_score(area_name: str | None) -> tuple[float, str]:
    """Score region by timezone proximity to Moscow/SPb."""
    if not area_name:
        return 0.0, ""
    area_lower = area_name.lower()
    # Moscow and SPb get higher bonus (preferred cities)
    if area_lower in ("москва", "санкт-петербург"):
        return 0.1, f"top city: {area_name}"
    if area_lower in PREFERRED_REGIONS:
        return 0.05, f"preferred region: {area_name}"
    if area_lower in NEARBY_REGIONS:
        return 0.0, ""  # neutral, no bonus no penalty
    if area_lower in MEDIUM_REGIONS:
        return -0.05, f"medium timezone diff: {area_name}"
    if area_lower in FAR_REGIONS:
        return -0.15, f"far timezone: {area_name}"
    # Unknown region — neutral (could be "Другое", "Сербия", "Кипр", etc.)
    return 0.0, ""


def fast_score(
    title: str,
    company_name: str | None,
    description_snippet: str | None,
    key_skills: list[str] | None,
    experience: str | None,
    schedule: str | None,
    area_name: str | None = None,
) -> tuple[float, str]:
    """
    Quick rule-based scoring. No API calls.
    Returns (score 0.0-1.0, reasoning).
    """
    score = 0.0
    reasons = []

    title_lower = title.lower()

    # Negative keywords in title — check first
    for neg in NEGATIVE_KEYWORDS:
        if neg in title_lower:
            return 0.0, f"negative keyword in title: '{neg}'"

    # Tiered title matching
    title_matched = False
    for kw in TIER1_TITLE_KEYWORDS:
        if kw in title_lower:
            score += 0.35
            reasons.append(f"tier1 title: '{kw}'")
            title_matched = True
            break
    if not title_matched:
        for kw in TIER2_TITLE_KEYWORDS:
            if kw in title_lower:
                score += 0.25
                reasons.append(f"tier2 title: '{kw}'")
                title_matched = True
                break
    if not title_matched:
        # Exact short keywords (ai, ml, llm) — word boundary check
        for kw in EXACT_TITLE_KEYWORDS:
            pattern = rf'\b{kw}\b'
            if re.search(pattern, title_lower):
                score += 0.2
                reasons.append(f"exact title: '{kw}'")
                title_matched = True
                break
    if not title_matched:
        for kw in TIER3_TITLE_KEYWORDS:
            if kw in title_lower:
                # Tier 3 generic devs — only small bonus, AI scoring will decide
                score += 0.1
                reasons.append(f"tier3 title: '{kw}'")
                title_matched = True
                break

    # Key skills matching
    if key_skills:
        skills_lower = {s.lower() for s in key_skills}
        matched = skills_lower & ALL_SKILLS
        if matched:
            skill_score = min(len(matched) * 0.1, 0.4)
            score += skill_score
            reasons.append(f"matched {len(matched)} skills: {', '.join(list(matched)[:5])}")

    # Snippet matching
    if description_snippet:
        snippet_skills = _extract_text_skills(description_snippet)
        if snippet_skills:
            snippet_score = min(len(snippet_skills) * 0.05, 0.2)
            score += snippet_score

    # Schedule bonus (remote preferred)
    if schedule == "remote":
        score += 0.1
        reasons.append("remote work")

    # Part-time / freelance bonus (small — we search full-time too)
    search_text = f"{title_lower} {(description_snippet or '').lower()}"
    for kw in PARTTIME_KEYWORDS:
        if kw in search_text:
            score += 0.05
            reasons.append(f"part-time keyword: '{kw}'")
            break

    # Region / timezone scoring
    region_delta, region_reason = _region_score(area_name)
    if region_delta != 0:
        score += region_delta
        reasons.append(region_reason)

    # Cap at 1.0, floor at 0.0
    score = max(min(score, 1.0), 0.0)
    reasoning = "; ".join(reasons) if reasons else "no strong matches"

    return score, reasoning


async def ai_score(
    title: str,
    company_name: str | None,
    description: str | None,
    key_skills: list[str] | None,
    resume_text: str,
) -> ScoringResult:
    """
    AI-powered deep scoring using Claude Haiku for cost efficiency.
    Analyzes full vacancy description against resume.
    """
    clean_desc = _clean_html(description) if description else "No description"
    skills_str = ", ".join(key_skills) if key_skills else "Not specified"

    prompt = f"""Score this vacancy's relevance to the candidate on a 0.0-1.0 scale.

CANDIDATE PROFILE:
{resume_text[:3000]}

VACANCY:
Title: {title}
Company: {company_name or 'Unknown'}
Key Skills: {skills_str}
Description: {clean_desc[:2000]}

Return ONLY valid JSON (no markdown):
{{
    "score": 0.0-1.0,
    "reasoning": "brief explanation in Russian",
    "matched_skills": ["skill1", "skill2"],
    "missing_skills": ["skill3"],
    "recommended_emphasis": "what to highlight in cover letter (in Russian)"
}}

IMPORTANT CONTEXT:
- Candidate is open to BOTH full-time and part-time/project work
- Prefers remote work or hybrid in Moscow/Saint Petersburg, but considers other formats
- Has enterprise experience (major international clients, B2B platforms) AND personal projects (18+ total)
- Target roles by priority:
  Tier 1 (best fit): AI/Automation Engineer, AI Integrator, Vibe Coder, AI Solutions Engineer
  Tier 2 (strong): AI Product Engineer, LLM Engineer, Full-Stack AI Developer, No-code/Low-code Developer
  Tier 3 (possible): AI Consultant, Growth Manager (AI), DevOps Engineer, MarTech Engineer

Scoring guidelines:
- 0.8-1.0: Perfect match (target role from Tier 1-2, most skills match)
- 0.6-0.8: Good match (related tech role, many skills overlap)
- 0.4-0.6: Partial match (some relevant skills, different focus)
- 0.2-0.4: Weak match (few overlapping skills)
- 0.0-0.2: No match"""

    try:
        response = await ai_complete(
            prompt=prompt,
            model=settings.scoring_model,
            max_tokens=16000,
        )

        text = response.text
        # Try to extract JSON from response
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        # Fix truncated JSON: close open strings and braces
        text = text.strip()
        if not text.endswith("}"):
            # Try to salvage truncated JSON
            if '"score"' in text:
                score_match = re.search(r'"score"\s*:\s*([\d.]+)', text)
                if score_match:
                    return ScoringResult(
                        score=float(score_match.group(1)),
                        reasoning="(truncated AI response)",
                    )
        data = json.loads(text)

        return ScoringResult(
            score=float(data.get("score", 0.0)),
            reasoning=data.get("reasoning", ""),
            matched_skills=data.get("matched_skills", []),
            missing_skills=data.get("missing_skills", []),
            recommended_emphasis=data.get("recommended_emphasis", ""),
        )

    except Exception as e:
        logger.error(f"AI scoring failed: {e}")
        return ScoringResult(
            score=0.5,
            reasoning=f"AI scoring failed: {str(e)[:100]}",
        )
