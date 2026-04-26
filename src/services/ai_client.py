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

    text = response.choices[0].message.content or ""
    usage = response.usage
    input_tokens = usage.prompt_tokens if usage else 0
    output_tokens = usage.completion_tokens if usage else 0

    logger.debug(f"AI call: model={model}, in={input_tokens}, out={output_tokens}")

    return AIResponse(
        text=text.strip(),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        model=model,
    )
