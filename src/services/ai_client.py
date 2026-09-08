"""AI client wrapper — supports Google Gemini (direct) and OpenRouter."""

import logging
from dataclasses import dataclass

import httpx
from openai import AsyncOpenAI

from src.config import settings

logger = logging.getLogger("hh-auto.ai")

_client: AsyncOpenAI | None = None

# Gemini API blocked from Russian IPs — route through ssh-proxy SOCKS5
_GEMINI_PROXY = "socks5://ssh-proxy:10808"


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

    response = await client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        messages=messages,
    )

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
