import logging
import sys
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from app.tasks.notify_bonuses import notify_new_bonuses
from app.tasks.sync_bonuses import sync_records
from app.db.session import init_db
from app.config import settings
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from contextlib import asynccontextmanager
from .bot.dispatcher import bot, router as bot_router

# Настройка логирования: консоль и файл
log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
logging.basicConfig(
    level=logging.INFO,
    format=log_format,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot.log", encoding="utf-8")
    ]
)
logger = logging.getLogger(__name__)

# Инициализация планировщика
scheduler = AsyncIOScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting application setup...")
    # Startup
    try:
        # Инициализация БД и схем
        await init_db()
        logger.info("Database initialized")

        # Плановые задания
        scheduler.add_job(
            func=sync_records,
            trigger="interval",
            seconds=60,
            args=[settings.COMPANY_ID],
            id="sync_records_job",
            replace_existing=True
        )
        scheduler.add_job(
            func=notify_new_bonuses,
            trigger="interval",
            seconds=60,
            id="notify_new_bonuses_job",
            replace_existing=True
        )
        scheduler.start()
        logger.info("Scheduler started with jobs: sync_records, notify_new_bonuses")

        # Установка webhook Telegram
        webhook_url = f"https://yourweebhookurl.com/bot/{settings.FATHERBOT_TOKEN}"
        await bot.set_webhook(
            url=webhook_url,
            drop_pending_updates=True
        )
        logger.info("Webhook set to %s", webhook_url)

    except Exception as exc:
        logger.exception("Error during startup: %s", exc)

    yield

    # --- Shutdown ---
    try:
        logger.info("Shutting down application...")
        await bot.delete_webhook()
        await bot.session.close()
        scheduler.shutdown(wait=False)
        logger.info("Scheduler shutdown and webhook deleted")
    except Exception as exc:
        logger.exception("Error during shutdown: %s", exc)

# Создаём FastAPI с нашим lifespan
app = FastAPI(lifespan=lifespan)

# Глобальный middleware для обработки HTTP ошибок
@app.middleware("http")
async def catch_exceptions_middleware(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception as exc:
        logger.exception("Unhandled exception in HTTP request: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"}
        )

# Монтируем роуты Telegram-бота
app.include_router(bot_router)

@app.get("/health")
async def health():
    return {"status": "ok"}
