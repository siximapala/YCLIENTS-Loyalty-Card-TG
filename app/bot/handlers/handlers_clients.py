# app/bot/handlers/handlers_client.py

import re
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
    Contact,
    FSInputFile,
    ReplyKeyboardRemove
)
from aiogram.filters.state import StateFilter
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

from sqlmodel import select
from app.config import settings
from app.db.models import Clients
from app.db.session import async_session
from app.api.yclients import YClientsAPI

clients_router = Router()

# Регекс для валидации номера (мы теперь ждем его из Contact)
PHONE_RE = re.compile(r"""
    ^\s*
    (?:\+7|8)?      # +7 или 8 в начале (опционально)
    (\d{10})        # 10 цифр
    \s*$
""", re.VERBOSE)

class AuthStates(StatesGroup):
    waiting_for_phone = State()


# 1) /start спрашиваем контакт через кнопку
@clients_router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    async with async_session() as session:
        client = None
        if message.from_user:
            telegram_user_id = message.from_user.id
            result = await session.execute(
                select(Clients).where(Clients.telegram_user_id == telegram_user_id)
            )
            client = result.scalar_one_or_none()
        if client:
            # Уже зарегистрирован - показываем доступные команды
            await message.answer(
                f" <b>{client.name}</b>, рады видеть Вас в числе наших постоянных гостей!\n"
                f"Ваш номер <b>{client.phone_number}</b> успешно сохранён.\n\n"
                "Вы стали участником программы лояльности <b>DOG STYLE</b> — теперь за каждое посещение вы будете получать бонусы и приятные привилегии.\n\n"
                "Доступные команды:\n"
                "/balance - Посмотреть баланс баллов\n"
                "/reserve - Записаться на услугу\n"
                "/contact - Связаться с нами\n\n"
                "Если что-то понадобится — мы всегда рядом! ❤️🪄",
                parse_mode="HTML",
            )
            await state.clear()
        else:
            await state.clear()
            kb = ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="📱 Поделиться контактом", request_contact=True)]],
                resize_keyboard=True,
                one_time_keyboard=True,
            )
            await message.answer_photo(
                photo=FSInputFile("/app/app/media/welcome.png"),
                caption="<b>Добро пожаловать в программу лояльности DOG STYLE! 💞</b>"
                        "Участвуйте и накапливайте бонусные баллы за каждое посещение.\n"
                        "Для регистрации и начала участия, пожалуйста, нажмите кнопку ниже, чтобы указать свой номер телефона.📲",
                parse_mode="HTML",
                reply_markup=kb,
            )
            await state.set_state(AuthStates.waiting_for_phone)


# 2) Получили Contact от Telegram

@clients_router.message(F.contact, StateFilter(AuthStates.waiting_for_phone))
async def process_contact(message: Message, state: FSMContext):
    contact: Contact = message.contact
    phone = contact.phone_number
    telegram_user_id = message.from_user.id  # сохраняем user_id

    # Нормализация
    if phone.startswith("8") and len(phone) == 11:
        phone = "+7" + phone[1:]
    elif phone.startswith("7") and len(phone) == 11:
        phone = "+" + phone
    elif phone.startswith("+7") and len(phone) == 12:
        pass
    else:
        return await message.reply(
            "❗️ Похоже, ваш номер в нестандартном формате. "
            "Попробуйте ещё раз или обратитесь к администратору."
        )

    await _register_or_find_client(phone, telegram_user_id, message, state)


async def _register_or_find_client(phone: str, telegram_user_id: int, message: Message, state: FSMContext):
    # 1) Ищем в локальной БД
    async with async_session() as session:
        result = await session.execute(
            select(Clients).where(Clients.phone_number == phone)
        )
        client = result.scalar_one_or_none()

        if client:
            # Обновляем статус и сохраняем user_id
            client.is_in_loyalty = True
            client.telegram_user_id = telegram_user_id
            session.add(client)
            await session.commit()
        else:
            # 2) Ищем по всем клиентам YClients постранично
            api = YClientsAPI()  # должен использовать правильные заголовки
            found = None
            page = 1
            page_size = 200

            try:
                while True:
                    resp = await api.client.post(
                        f"/company/{settings.COMPANY_ID}/clients/search",  # ✅ Правильный эндпоинт
                        json={
                            "page": page,
                            "page_size": page_size,
                            "fields": ["id", "phone", "name"],  # ✅ Обязательные поля
                            "filters": [],  # ✅ Даже если фильтры не нужны
                            "operation": "AND",  # ✅ Обязательный параметр
                            "order_by": "name",
                            "order_by_direction": "ASC"
                        }
                    )
                    resp.raise_for_status()
                    data = resp.json().get("data", [])
                    for yc in data:
                        if yc.get("phone") == phone:
                            found = yc
                            break
                    if found or len(data) < page_size:
                        break
                    page += 1
            finally:
                await api.close()

            if not found:
                # ничего не нашли
                await message.reply(
                    "⚠️ Клиент с таким номером не найден в системе.\n"
                    "Пожалуйста, обратитесь к администратору."
                )
                return

            # 3) Создаём нового клиента в БД и сохраняем user_id
            client = Clients(
                yclients_id=found["id"],
                phone_number=phone,
                name=found.get("name", ""),
                points=0,
                is_in_loyalty=True,
                telegram_user_id=telegram_user_id
            )
            client.id = None  
            session.add(client)
            await session.commit()

    # 4) Сбрасываем FSM и показываем доступные команды
    await state.clear()

    await message.answer(
        f" <b>{client.name}</b>, рады видеть Вас в числе наших постоянных гостей!\n"
        f"Ваш номер <b>{client.phone_number}</b> успешно сохранён.\n"
        f"Вы стали участником программы лояльности <b>DOG STYLE</b> — теперь за каждое посещение вы будете получать бонусы и приятные привилегии.\n\n"
        f"Используйте доступные команды при помощи кнопки \"Меню\" слева снизу.\n"
        "Если что-то понадобится — мы всегда рядом! ❤️🪄",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove()
    )

# 5) Баланс через команду
@clients_router.message(Command("balance"))
async def cmd_balance(message: Message):
    async with async_session() as session:
        telegram_user_id = message.from_user.id if message.from_user else None
        if not telegram_user_id:
            return await message.reply("❗️ Ошибка: не удалось определить пользователя. Если ошибка повторяется, рекомендуем написать /start, либо удалить историю чата бота и зарегистрироваться в нем снова. В случае дополнительных вопросов, обращайтесь к администратору.")
        result = await session.execute(
            select(Clients).where(Clients.telegram_user_id == telegram_user_id)
        )
        client = result.scalar_one_or_none()

    if not client:
        return await message.reply("❗️ Ошибка: клиент не найден. Скорее всего, Вы не поделились контактом. Нажмите на кнопку \"Поделиться контактом\" внизу. Если ошибка повторяется, рекомендуем написать /start, либо удалить историю чата бота и зарегистрироваться в нем снова. В случае дополнительных вопросов, обращайтесь к администратору.")

    await message.reply(
        f"💳 Ваш баланс: <b>{client.points}</b> баллов",
        parse_mode="HTML",
    )

# 6) Записаться через команду
@clients_router.message(Command("reserve"))
async def cmd_reserve(message: Message):
    # Отправляем картинку и текст с ссылкой
    await message.answer_photo(
        photo=FSInputFile("/app/app/media/welcome.png/"),
        caption=f"📍Перейдите по ссылке, чтобы записаться:\n\n{settings.YCLIENTS_BOOK_URL}"
    )

# 7) Контакты салона через команду
@clients_router.message(Command("contact"))
async def cmd_contact(message: Message):
    await message.reply(
        f"Мы всегда рады нашим клиентам! Если нужно записаться по телефону или задать вопрос, звоните.\n"
        f"📞 <b>Телефон: {settings.SUPPORT_PHONE}\n</b>"
        "Мы работаем каждый день с 10:00 до 21:00.",
        reply_markup=InlineKeyboardMarkup(
                        inline_keyboard=[
                            [InlineKeyboardButton(text="📍 Мы на Яндекс.Картах", url=settings.COMPANY_YMAPS_LINK)]
                        ]
                    )
    )