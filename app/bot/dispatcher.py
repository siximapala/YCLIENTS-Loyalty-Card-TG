import logging
from fastapi import APIRouter, Request
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Update, Message, ErrorEvent
from aiogram.filters import Command

from app.config import settings
# Используем относительные импорты для внутренних роутеров
from .handlers.handlers_admin import admin_router
from .handlers.handlers_clients import clients_router

# Настройка логирования: вывод в консоль и файл bot.log
log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
logging.basicConfig(
    level=logging.INFO,
    format=log_format,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("bot.log", encoding="utf-8")
    ]
)
logger = logging.getLogger(__name__)

# Инициализация Bot и Dispatcher
bot = Bot(
    token=settings.FATHERBOT_TOKEN,
    default=DefaultBotProperties(parse_mode="HTML")
)
dp = Dispatcher(storage=MemoryStorage())

# Подключение роутеров с хендлерами
dp.include_router(admin_router)
dp.include_router(clients_router)

# Глобальный обработчик ошибок aiogram
@dp.error()
async def global_error_handler(event: ErrorEvent):
    """
    Ловит все необработанные исключения в хендлерах aiogram.
    """
    # Логирование исключения с полным стектрейсом
    logger.exception("Unhandled exception in aiogram: %s", event.exception)

    # Если есть сообщение в update - уведомляем пользователя
    update = event.update
    if isinstance(update, Update) and update.message:
        try:
            await update.message.reply(
                "❗️ Упс… что-то пошло не так на сервере. Попробуйте чуть позже."
            )
        except Exception as notify_exc:
            logger.error("Failed to notify user about error: %s", notify_exc)


# FastAPI APIRouter для вебхуков Telegram
router = APIRouter()

@router.post(f"/bot/{settings.FATHERBOT_TOKEN}")
async def bot_webhook(request: Request):
    update_data = await request.json()
    update = Update(**update_data)
    await dp.feed_webhook_update(bot, update)
    return {"status": "ok"}
