"""Regression tests: a failed AI call must never be stored as a verdict.

The trigger case (Nov 2026): the Gemini balance ran out on 04.11 at 06:52 UTC.
`ai_score` answered every exception with `ScoringResult(score=0.5, ...)`, which is
indistinguishable from a real middling score. The vacancy was written to the
database as `scored`, the cycle reported success, and because auto-generation
needs 0.7 nothing reached the review queue. 63 vacancies were buried that way in
two days, 341 since March, and the only trace was one ERROR line per vacancy.

A second, independent defect surfaced while repairing the first: about 3% of
gemini-2.5-flash replies are *nearly* JSON (7 of 211 calls), and with no retry
each bad roll became a permanent 0.5 too.

These tests pin both fixes, in both directions:
  * a failure raises instead of returning a number;
  * a malformed reply is retried, and a quota failure is not;
  * the quota guard fires on real quota errors and stays quiet on ordinary ones.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.services import ai_client
from src.services.ai_client import (
    AIQuotaExhausted,
    AIResponse,
    AIResponseInvalid,
    _looks_like_quota_exhausted,
    _strip_code_fence,
    ai_complete_json,
)
from src.services.daily_summary import (
    _as_json_list,
    _as_text,
    format_summary_for_telegram,
)
from src.services.vacancy_scorer import ScoringFailed, ai_score

GOOD_SCORE_JSON = json.dumps(
    {
        "score": 0.85,
        "reasoning": "Сильное совпадение по стеку",
        "matched_skills": ["Python", "LLM"],
        "missing_skills": ["Kubernetes"],
        "recommended_emphasis": "Подчеркнуть RAG",
    },
    ensure_ascii=False,
)

# The exact shape that broke 7 calls in 211: an unescaped quote inside a value.
MALFORMED_JSON = '{"score": 0.9, "reasoning": "он сказал "да" и ушёл", "matched_skills": []}'


def _response(text: str, finish_reason: str = "stop") -> AIResponse:
    return AIResponse(
        text=text,
        input_tokens=100,
        output_tokens=50,
        model="gemini-2.5-flash",
        finish_reason=finish_reason,
        thinking_tokens=200,
    )


def _quota_error() -> Exception:
    exc = Exception(
        "Error code: 402 - {'error': {'code': 402, 'message': 'Your prepayment "
        "credits are depleted. Please go to AI Studio at https://ai.studio/projects', "
        "'status': 'RESOURCE_EXHAUSTED'}}"
    )
    exc.status_code = 402
    return exc


@pytest.fixture(autouse=True)
def _reset_quota_alert_throttle():
    """Each test starts with the alert throttle cleared."""
    ai_client._last_quota_alert = None
    yield
    ai_client._last_quota_alert = None


# ─── Quota detection: both directions ──────────────────────────────────────

@pytest.mark.parametrize(
    "exc",
    [
        _quota_error(),
        Exception("RESOURCE_EXHAUSTED"),
        Exception("Your prepayment credits are depleted."),
        Exception("402 insufficient credits for this request"),
        Exception("You exceeded your current quota, please check your plan"),
    ],
)
def test_quota_guard_recognises_real_quota_failures(exc):
    assert _looks_like_quota_exhausted(exc) is True


@pytest.mark.parametrize(
    "exc",
    [
        Exception("Connection reset by peer"),
        Exception("Error code: 500 - internal server error"),
        Exception("Expecting ',' delimiter: line 2 column 6852 (char 6853)"),
        Exception("Error code: 403 - Access denied by security policy"),
        Exception("Read timed out"),
    ],
)
def test_quota_guard_stays_quiet_on_ordinary_failures(exc):
    """The mutation in the other direction.

    A guard wide enough to match any error would alert on every network blip and
    stop the cycle for nothing — exactly as damaging as missing the real case.
    """
    assert _looks_like_quota_exhausted(exc) is False


# ─── ai_complete_json: retry on malformed, never on quota ──────────────────

@pytest.mark.asyncio
async def test_malformed_json_is_retried_and_the_second_reply_wins():
    replies = [_response(MALFORMED_JSON), _response(GOOD_SCORE_JSON)]
    with patch.object(ai_client, "ai_complete", AsyncMock(side_effect=replies)) as mock:
        data, response = await ai_complete_json(prompt="x", attempts=3)
    assert mock.await_count == 2
    assert data["score"] == 0.9 or data["score"] == 0.85
    assert response.model == "gemini-2.5-flash"


@pytest.mark.asyncio
async def test_json_invalid_on_every_attempt_raises_and_does_not_return_a_value():
    with patch.object(
        ai_client, "ai_complete", AsyncMock(return_value=_response(MALFORMED_JSON))
    ) as mock:
        with pytest.raises(AIResponseInvalid):
            await ai_complete_json(prompt="x", attempts=3)
    assert mock.await_count == 3


@pytest.mark.asyncio
async def test_quota_failure_is_not_retried():
    """Retrying a depleted account bills for each attempt and changes nothing."""
    with patch.object(
        ai_client, "ai_complete", AsyncMock(side_effect=AIQuotaExhausted("402"))
    ) as mock:
        with pytest.raises(AIQuotaExhausted):
            await ai_complete_json(prompt="x", attempts=3)
    assert mock.await_count == 1


@pytest.mark.asyncio
async def test_a_json_array_is_not_accepted_as_an_object():
    with patch.object(
        ai_client, "ai_complete", AsyncMock(return_value=_response("[1, 2, 3]"))
    ):
        with pytest.raises(AIResponseInvalid):
            await ai_complete_json(prompt="x", attempts=2)


def test_code_fence_is_stripped():
    assert _strip_code_fence('```json\n{"a": 1}\n```') == '{"a": 1}'
    assert _strip_code_fence('```\n{"a": 1}\n```') == '{"a": 1}'
    assert _strip_code_fence('{"a": 1}') == '{"a": 1}'


# ─── The quota alert ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_quota_failure_alerts_once_per_hour_not_once_per_vacancy():
    """72 identical messages are as easy to ignore as the log lines they replace."""
    sent: list[str] = []
    fake_notifier = SimpleNamespace(
        is_configured=True,
        send_message=AsyncMock(side_effect=lambda text, **kw: sent.append(text)),
    )
    with patch("src.services.telegram_bot.notifier", fake_notifier):
        await ai_client._alert_quota_exhausted("credits are depleted")
        await ai_client._alert_quota_exhausted("credits are depleted")
        await ai_client._alert_quota_exhausted("credits are depleted")
    assert len(sent) == 1
    assert "остановлен" in sent[0]


@pytest.mark.asyncio
async def test_quota_alert_fires_again_after_the_interval():
    sent: list[str] = []
    fake_notifier = SimpleNamespace(
        is_configured=True,
        send_message=AsyncMock(side_effect=lambda text, **kw: sent.append(text)),
    )
    with patch("src.services.telegram_bot.notifier", fake_notifier):
        await ai_client._alert_quota_exhausted("depleted")
        ai_client._last_quota_alert = datetime.now(timezone.utc) - timedelta(hours=2)
        await ai_client._alert_quota_exhausted("depleted")
    assert len(sent) == 2


@pytest.mark.asyncio
async def test_a_failing_alert_does_not_break_the_caller():
    """An alert that cannot be delivered must not turn into a second failure."""
    fake_notifier = SimpleNamespace(
        is_configured=True,
        send_message=AsyncMock(side_effect=RuntimeError("telegram unreachable")),
    )
    with patch("src.services.telegram_bot.notifier", fake_notifier):
        await ai_client._alert_quota_exhausted("depleted")  # must not raise


# ─── ai_score: the actual regression ───────────────────────────────────────

SCORE_ARGS = dict(
    title="AI Engineer",
    company_name="ООО Пример",
    description="Нужен Python и LLM",
    key_skills=["Python", "LLM"],
    resume_text="Алексей Аванов, AI/Automation Engineer",
)


@pytest.mark.asyncio
async def test_scoring_returns_the_model_verdict_when_the_reply_is_good():
    with patch(
        "src.services.vacancy_scorer.ai_complete_json",
        AsyncMock(return_value=(json.loads(GOOD_SCORE_JSON), _response(GOOD_SCORE_JSON))),
    ):
        result = await ai_score(**SCORE_ARGS)
    assert result.score == 0.85
    assert result.matched_skills == ["Python", "LLM"]


@pytest.mark.asyncio
async def test_scoring_failure_raises_instead_of_returning_half():
    """THE regression. 0.5 as a return value is what hid a two-day outage."""
    with patch(
        "src.services.vacancy_scorer.ai_complete_json",
        AsyncMock(side_effect=AIResponseInvalid("invalid JSON after 3 attempts")),
    ):
        with pytest.raises(ScoringFailed):
            await ai_score(**SCORE_ARGS)


@pytest.mark.asyncio
async def test_any_unexpected_error_also_raises_rather_than_scoring():
    with patch(
        "src.services.vacancy_scorer.ai_complete_json",
        AsyncMock(side_effect=RuntimeError("socket closed")),
    ):
        with pytest.raises(ScoringFailed):
            await ai_score(**SCORE_ARGS)


@pytest.mark.asyncio
async def test_quota_exhaustion_propagates_and_is_not_downgraded():
    """The cycle must be able to tell "no money" from "this vacancy is odd"."""
    with patch(
        "src.services.vacancy_scorer.ai_complete_json",
        AsyncMock(side_effect=AIQuotaExhausted("402 credits depleted")),
    ):
        with pytest.raises(AIQuotaExhausted):
            await ai_score(**SCORE_ARGS)


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [
    {"reasoning": "без балла"},
    {"score": None, "reasoning": "пусто"},
    {"score": "высокий", "reasoning": "словом, а не числом"},
])
async def test_a_reply_without_a_usable_score_is_a_failure_not_a_zero(payload):
    with patch(
        "src.services.vacancy_scorer.ai_complete_json",
        AsyncMock(return_value=(payload, _response("{}"))),
    ):
        with pytest.raises(ScoringFailed):
            await ai_score(**SCORE_ARGS)


@pytest.mark.asyncio
@pytest.mark.parametrize("raw,expected", [(1.7, 1.0), (-0.3, 0.0), (0.42, 0.42)])
async def test_scores_outside_the_scale_are_clamped(raw, expected):
    with patch(
        "src.services.vacancy_scorer.ai_complete_json",
        AsyncMock(return_value=({"score": raw, "reasoning": "r"}, _response("{}"))),
    ):
        result = await ai_score(**SCORE_ARGS)
    assert result.score == expected


# ─── The daily summary must not pass a stub off as a report ────────────────

def _summary(model_used: str | None) -> SimpleNamespace:
    return SimpleNamespace(
        summary_date=date(2026, 11, 6),
        vacancies_discovered=97,
        applications_sent=0,
        responses_received=0,
        avg_relevance_score=0.27,
        top_vacancies=[{"title": "AI Engineer", "company": "X", "score": 0.9}],
        interview_prep=None,
        insights=None,
        model_used=model_used,
    )


def test_a_stub_summary_says_so_on_the_first_line():
    text = format_summary_for_telegram(_summary(model_used=None))
    assert "Разбора нет" in text


def test_a_real_summary_carries_no_warning():
    """The other direction: don't cry failure over a summary that worked."""
    text = format_summary_for_telegram(_summary(model_used="gemini-2.5-flash"))
    assert "Разбора нет" not in text


# ─── The shape of a reply must not cost the day's analysis ─────────────────
#
# Found by running the new code against the real database: the model answered
# `insights` with an object of named sections instead of a string. asyncpg
# rejected the Text column ("expected str, got dict"), the whole insert failed,
# and the fallback insert failed too on the poisoned session — one day in the
# last 30 has no summary row at all because of this.

def test_insights_as_an_object_is_rendered_not_dropped():
    rendered = _as_text({
        "trends": "Рост спроса на LLM",
        "recommendation_for_candidate": "Подчёркивать RAG",
    })
    assert "Рост спроса на LLM" in rendered
    assert "Подчёркивать RAG" in rendered
    assert isinstance(rendered, str)


@pytest.mark.parametrize("value,expected", [
    ("просто текст", "просто текст"),
    (None, ""),
    (["первое", "второе"], "первое\n\nвторое"),
    (42, "42"),
])
def test_as_text_passes_plain_values_through(value, expected):
    assert _as_text(value) == expected


def test_nested_objects_are_flattened_to_text():
    rendered = _as_text({"outer": {"inner": "значение"}})
    assert "значение" in rendered
    assert isinstance(rendered, str)


@pytest.mark.parametrize("value,expected", [
    (None, None),
    ([{"title": "a"}], [{"title": "a"}]),
    ({"items": [{"title": "a"}]}, [{"title": "a"}]),
    ({"title": "одна вакансия"}, [{"title": "одна вакансия"}]),
])
def test_a_jsonb_list_column_always_gets_a_list(value, expected):
    assert _as_json_list(value) == expected


# ─── No money means stop, not grind ───────────────────────────────────────

@pytest.mark.asyncio
async def test_a_quota_failure_stops_the_cycle_instead_of_walking_every_profile():
    """Every remaining vacancy would hit the same wall and be billed for the try."""
    from src.services.pipeline import Pipeline

    pipeline = Pipeline(db=AsyncMock(), hh_client=AsyncMock(), hh_browser=AsyncMock())
    profiles = [
        SimpleNamespace(id=1, name="первый", resume_id="r1"),
        SimpleNamespace(id=2, name="второй", resume_id="r2"),
    ]
    visited: list[str] = []

    async def fake_process(profile):
        visited.append(profile.name)
        raise AIQuotaExhausted("402 prepayment credits are depleted")

    pipeline._get_active_profiles = AsyncMock(return_value=profiles)
    pipeline._retry_failed_scores = AsyncMock(return_value=0)
    pipeline._process_profile = fake_process
    pipeline._log_event = AsyncMock()

    await pipeline.run_search_cycle()

    assert visited == ["первый"]
    logged = [call.args[0] for call in pipeline._log_event.await_args_list]
    assert "search_cycle_aborted" in logged


@pytest.mark.asyncio
async def test_an_ordinary_profile_error_does_not_stop_the_other_profiles():
    """The other direction: one bad profile must not cancel the rest of the run."""
    from src.services.pipeline import Pipeline

    pipeline = Pipeline(db=AsyncMock(), hh_client=AsyncMock(), hh_browser=AsyncMock())
    profiles = [
        SimpleNamespace(id=1, name="первый", resume_id="r1"),
        SimpleNamespace(id=2, name="второй", resume_id="r2"),
    ]
    visited: list[str] = []

    async def fake_process(profile):
        visited.append(profile.name)
        if profile.name == "первый":
            raise RuntimeError("hh.ru вернул 500")
        return 1, 1, 0

    pipeline._get_active_profiles = AsyncMock(return_value=profiles)
    pipeline._retry_failed_scores = AsyncMock(return_value=0)
    pipeline._process_profile = fake_process
    pipeline._log_event = AsyncMock()

    await pipeline.run_search_cycle()

    assert visited == ["первый", "второй"]
