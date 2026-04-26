from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://hh_auto:changeme@localhost:5432/hh_auto"

    # hh.ru credentials (browser login)
    hh_email: str = ""
    hh_password: str = ""

    # hh.ru API OAuth (client_credentials flow)
    hh_client_id: str = ""
    hh_client_secret: str = ""

    # AI provider: "gemini" for direct Google API, "openrouter" for OpenRouter
    ai_provider: str = "gemini"

    # Google Gemini direct API
    gemini_api_key: str = ""
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"

    # OpenRouter (fallback)
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # Model names (auto-adjusted per provider)
    ai_model: str = "gemini-2.5-flash"
    scoring_model: str = "gemini-2.5-flash"

    # Telegram
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # Scheduler
    search_interval_hours: int = 4
    apply_interval_minutes: int = 30
    status_check_interval_hours: int = 6
    max_applications_per_day: int = 50

    # Auto-generate cover letters only for vacancies scoring above this threshold
    # Vacancies scoring between min_relevance_score and this value are saved as "scored"
    # and can have letters generated manually via UI button
    auto_generate_score: float = 0.7

    # Server
    host: str = "0.0.0.0"
    port: int = 8100

    model_config = {"env_prefix": "HH_AUTO_", "env_file": ".env"}


settings = Settings()
