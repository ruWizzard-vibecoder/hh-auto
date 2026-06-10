import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.config import settings
from src.database import engine, Base

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("/app/logs/hh-auto.log", mode="a"),
    ]
    if Path("/app/logs").exists()
    else [logging.StreamHandler()],
)
logger = logging.getLogger("hh-auto")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting hh-auto service")

    # Create tables
    async with engine.begin() as conn:
        from src.models import (  # noqa: F401
            Vacancy,
            Application,
            CoverLetter,
            Resume,
            SearchProfile,
            CompanyRule,
            EventLog,
            Setting,
            DailySummary,
        )
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables ready")

    # Auto-seed resumes if empty
    from src.api.resumes_api import auto_seed_resumes
    await auto_seed_resumes()

    # Start scheduler
    from src.services.scheduler import scheduler, setup_scheduler
    setup_scheduler()
    scheduler.start()
    logger.info("Scheduler started")

    # Start Telegram bot polling (if configured)
    from src.services.telegram_bot import notifier
    if notifier.is_configured:
        asyncio.create_task(notifier.start_polling())
        logger.info("Telegram bot polling started")

    # Start seed expansion worker (drains hh_ids enqueued from letter approvals)
    from src.services import seed_expansion_queue
    seed_expansion_queue.start_worker()
    logger.info("Seed expansion worker started")

    yield

    # Shutdown
    scheduler.shutdown(wait=False)
    logger.info("Scheduler stopped")

    await seed_expansion_queue.stop_worker()
    logger.info("Seed expansion worker stopped")

    from src.services.telegram_bot import notifier
    await notifier.close()

    await engine.dispose()
    logger.info("hh-auto service stopped")


app = FastAPI(title="hh-auto", version="0.1.0", lifespan=lifespan)

# Static files & templates
static_dir = Path(__file__).parent / "static"
templates_dir = Path(__file__).parent / "templates"

if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

templates = Jinja2Templates(directory=str(templates_dir))

# Register routers
from src.api.dashboard import router as dashboard_router
from src.api.auth import router as auth_router
from src.api.cover_letters import router as cover_letters_router
from src.api.settings_api import router as settings_api_router
from src.api.pipeline_api import router as pipeline_api_router
from src.api.resumes_api import router as resumes_api_router
from src.api.dashboard_json import router as dashboard_json_router
from src.api.letters_json import router as letters_json_router
from src.api.vacancies_json import router as vacancies_json_router
from src.api.extra_json import router as extra_json_router

app.include_router(dashboard_router)
app.include_router(auth_router)
app.include_router(cover_letters_router)
app.include_router(settings_api_router)
app.include_router(pipeline_api_router)
app.include_router(resumes_api_router)
app.include_router(dashboard_json_router)
app.include_router(letters_json_router)
app.include_router(vacancies_json_router)
app.include_router(extra_json_router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "hh-auto"}
