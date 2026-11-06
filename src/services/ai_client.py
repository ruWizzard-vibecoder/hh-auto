"""AI client wrapper — supports Google Gemini (direct) and OpenRouter."""

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx
from openai import AsyncOpenAI

from src.config import settings

logger = logging.getLogger("hh-auto.ai")

_client: AsyncOpenAI | None = None

# Gemini API blocked from Russian IPs — route through ssh-proxy SOCKS5
_GEMINI_PROXY = "socks5://ssh-proxy:10808"


class AIQuotaExhausted(Exception):
    """The provider refused the call for lack of credits or quota.

    Kept distinct from every other failure because the right response differs:
    retrying costs money and changes nothing, and *every* LLM step is down until
    someone tops the account up. Callers should stop the cycle, not mark one item.
    """


class AIResponseInvalid(Exception):
    """The model answered, but the answer is not the JSON that was asked for."""


_QUOTA_MARKERS = (
    "resource_exhausted",
    "prepayment credits are depleted",
    "insufficient credits",
    "exceeded your current quota",
)

# One alert per hour: a depleted account fails every call, and 72 identical
# messages would be as easy to ignore as the log lines they replace.
_QUOTA_ALERT_INTERVAL = timedelta(hours=1)
_last_quota_alert: datetime | None = None


def _looks_like_quota_exhausted(exc: Exception) -> bool:
    if getattr(exc, "status_code", None) == 402:
        return True
    text = str(exc).lower()
    return any(marker in text for marker in _QUOTA_MARKERS)


async def _alert_quota_exhausted(detail: str) -> None:
    """Tell the operator the pipeline has stopped, not that one call failed.

    In Nov 2026 a depleted Gemini balance went unnoticed for two days: the only
    trace was an ERROR line per vacancy, the scorer answered each one with a
    hardcoded 0.5, and the cycle reported success. The review queue stayed empty
    and nothing said why.
    """
    global _last_quota_alert
    now = datetime.now(timezone.utc)
    if _last_quota_alert and now - _last_quota_alert < _QUOTA_ALERT_INTERVAL:
        return
    _last_quota_alert = now
    try:
        from src.services.telegram_bot import notifier

        if not notifier.is_configured:
            return
        await notifier.send_message(
            "🔴 <b>Конвейер остановлен: у модели закончились деньги</b>\n\n"
            f"Провайдер: <code>{settings.ai_provider}</code>\n"
            f"Ответ провайдера: <code>{detail[:300]}</code>\n\n"
            "Оценка вакансий, генерация писем и ежедневный разбор не работают, "
            "пока счёт не пополнен. Вакансии продолжают находиться и ждут оценки."
        )
    except Exception as e:  # noqa: BLE001 — an alert must never break the caller
        logger.error(f"Failed to send quota alert: {e}")


def _strip_code_fence(text: str) -> str:
    """Drop a ```json fence the model wrapped its answer in."""
    text = text.strip()
    if not text.startswith("```"):
        return text
    parts = text.split("```")
    if len(parts) < 2:
        return text
    body = parts[1]
    if body.startswith("json"):
        body = body[4:]
    return body.strip()


def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        if settings.ai_provider == "gemini":
            proxy_client = httpx.AsyncClient(
                proxy=_GEMINI_PROXY,
                timeout=60.0,
            )
            _client = AsyncOpenAI(
                base_url=settings.gemini_base_url,
                api_key=settings.gemini_api_key,
                http_client=proxy_client,
            )
            logger.info(f"AI client: Google Gemini via proxy {_GEMINI_PROXY}")
        else:
            _client = AsyncOpenAI(
                base_url=settings.openrouter_base_url,
                api_key=settings.openrouter_api_key,
                default_headers={
                    "HTTP-Referer": "https://hh-auto.local",
                    "X-Title": "hh-auto",
                },
            )
            logger.info("AI client: OpenRouter")
    return _client


@dataclass
class AIResponse:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""
    finish_reason: str = ""
    thinking_tokens: int = 0


async def ai_complete(
    prompt: str,
    system: str | None = None,
    model: str | None = None,
    max_tokens: int = 1000,
) -> AIResponse:
    """Send a completion request.

    Args:
        prompt: User message content.
        system: Optional system prompt.
        model: Model ID. For Gemini direct: 'gemini-2.5-flash'.
               For OpenRouter: 'google/gemini-2.5-flash'.
               Defaults to settings.ai_model.
        max_tokens: Max response tokens.

    Returns:
        AIResponse with text and token usage.
    """
    client = get_client()
    model = model or settings.ai_model

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    try:
        response = await client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=messages,
        )
    except Exception as e:
        if _looks_like_quota_exhausted(e):
            logger.error(
                f"AI quota exhausted (provider={settings.ai_provider}, model={model}): "
                f"{str(e)[:300]}"
            )
            await _alert_quota_exhausted(str(e))
            raise AIQuotaExhausted(str(e)) from e
        raise

    choice = response.choices[0]
    text = choice.message.content or ""
    finish_reason = choice.finish_reason or ""
    usage = response.usage
    input_tokens = usage.prompt_tokens if usage else 0
    output_tokens = usage.completion_tokens if usage else 0
    # Thinking models (gemini-2.5-*) bill reasoning against max_tokens without
    # reporting it as completion_tokens — total minus the two is what was spent
    # on thinking, and it is the part that silently starves the visible answer.
    total_tokens = usage.total_tokens if usage else 0
    thinking_tokens = max(0, total_tokens - input_tokens - output_tokens)

    logger.debug(
        f"AI call: model={model}, in={input_tokens}, out={output_tokens}, "
        f"thinking={thinking_tokens}, finish={finish_reason}"
    )
    if finish_reason == "length":
        # A truncated answer is indistinguishable from a complete one downstream:
        # json.loads() blames the malformed JSON and the token budget goes unnoticed.
        logger.warning(
            f"AI response truncated by max_tokens={max_tokens} "
            f"(model={model}, visible={output_tokens}, thinking={thinking_tokens}). "
            f"Raise the budget — the answer is incomplete."
        )

    return AIResponse(
        text=text.strip(),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        model=model,
        finish_reason=finish_reason,
        thinking_tokens=thinking_tokens,
    )


async def ai_complete_json(
    prompt: str,
    system: str | None = None,
    model: str | None = None,
    max_tokens: int = 1000,
    attempts: int = 3,
) -> tuple[dict, AIResponse]:
    """Ask for JSON and insist on getting it.

    Models occasionally emit a reply that is *nearly* JSON — an unescaped quote or
    a raw newline inside a string value. Measured on gemini-2.5-flash during the
    Nov 2026 re-score: 7 malformed replies in 211 calls, about 3%. Without a retry
    each bad roll became a permanent verdict (scorer) or a stats-only stub that
    looked like a report (daily summary), and the caller could not tell the
    difference. Asking again is the only fix that holds, because the next reply
    is usually well-formed: both back-dated summaries regenerated on attempt 1.

    Quota failures are *not* retried — the next call fails identically and bills
    for the attempt, so AIQuotaExhausted propagates immediately.

    Returns:
        (parsed JSON object, the AIResponse it came from).

    Raises:
        AIQuotaExhausted: the account is out of credits.
        AIResponseInvalid: every attempt produced unparseable JSON.
    """
    last_error: Exception | None = None
    effective_model = model or settings.ai_model

    for attempt in range(1, attempts + 1):
        response = await ai_complete(
            prompt=prompt,
            system=system,
            model=model,
            max_tokens=max_tokens,
        )
        try:
            parsed = json.loads(_strip_code_fence(response.text))
        except (json.JSONDecodeError, ValueError) as e:
            last_error = e
            logger.warning(
                f"AI returned invalid JSON (attempt {attempt}/{attempts}, "
                f"model={effective_model}, finish={response.finish_reason}, "
                f"chars={len(response.text)}): {e}"
            )
            continue
        if not isinstance(parsed, dict):
            last_error = ValueError(f"expected a JSON object, got {type(parsed).__name__}")
            logger.warning(
                f"AI returned {type(parsed).__name__}, not an object "
                f"(attempt {attempt}/{attempts}, model={effective_model})"
            )
            continue
        if attempt > 1:
            logger.info(f"AI returned valid JSON on attempt {attempt}/{attempts}")
        return parsed, response

    raise AIResponseInvalid(
        f"invalid JSON after {attempts} attempts (model={effective_model}): {last_error}"
    )
