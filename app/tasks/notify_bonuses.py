# app/tasks/notify_bonuses.py

from app.db.session import async_session
from app.db.models import BonusLog, Clients
from app.bot.dispatcher import bot
from app.config import settings
from sqlmodel import select

async def notify_new_bonuses():
    async with async_session() as session:
        # выбираем все не­уведомлённые записи
        result = await session.execute(
            select(BonusLog, Clients)
            .join(Clients, BonusLog.client_id == Clients.id)
            .where(BonusLog.is_telegram_notified == False)
        )
        for bonuslog, client in result.fetchall():
            # если у клиента есть telegram_user_id - шлём ему сообщение
            if client.telegram_user_id:
                try:
                    # Кнопка Яндекс.Карты
                    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
                    maps_kb = InlineKeyboardMarkup(
                        inline_keyboard=[
                            [InlineKeyboardButton(text="📍 Мы на Яндекс.Картах", url=settings.COMPANY_YMAPS_LINK)]
                        ]
                    )
                    await bot.send_message(
                        client.telegram_user_id,
                        f"🎉 За ваш последний визит начислено <b>{bonuslog.points}</b> бонусов!\n"
                        "Пожалуйста, оцените нас на Яндекс.Картах, если Вам понравились наши услуги!",
                        parse_mode="HTML",
                        reply_markup=maps_kb
                    )
                    # помечаем, что уведомление отправлено
                    bonuslog.is_telegram_notified = True
                    session.add(bonuslog)
                    await session.commit()
                except Exception as e:
                    # логируем ошибку
                    print(f"[ERROR] Не удалось отправить уведомление: {e}")
