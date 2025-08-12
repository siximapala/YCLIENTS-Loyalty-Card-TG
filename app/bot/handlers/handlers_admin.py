import re
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)
from aiogram.filters.state import StateFilter
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from sqlmodel import select

from app.config import settings
from app.db.models import Clients
from app.db.session import async_session

admin_router = Router()


# ─── 1) /start и /help ────────────────────────────────────────────────────────

@admin_router.message(Command("start"), F.from_user.id.in_(settings.ADMIN_IDS))
async def cmd_start(message: Message):
    text = (
        "👋 <b>Админ-панель</b>\n\n"
        "Отправьте номер телефона клиента — получите его баланс.\n"
        "Можно сразу добавить сумму через пробел, например:\n"
        "  +79990001122 1500\n\n"
        "Форматы телефона:\n"
        " • +7XXXXXXXXXX\n"
        " • 8XXXXXXXXXX (заменю 8→+7)\n"
        " • XXXXXXXXXX  (добавлю +7)\n\n"
        "Команды:\n"
        " /help — подсказка\n"
    )
    await message.reply(text, parse_mode="HTML")


@admin_router.message(Command("help"), F.from_user.id.in_(settings.ADMIN_IDS))
async def cmd_help(message: Message):
    # просто дублируем стартовое сообщение
    await cmd_start(message)


# ─── 2) FSM для списания и начисления баллов ────────────────────────────────

class WriteoffStates(StatesGroup):
    waiting_for_amount = State()

class AddPointsStates(StatesGroup):
    waiting_for_amount = State()


# ─── Обработчики списания баллов ────────────────────────────────────────────

@admin_router.callback_query(
    F.data.startswith("writeoff:"),
    F.from_user.id.in_(settings.ADMIN_IDS),
)
async def callback_writeoff(query: CallbackQuery, state: FSMContext):
    """
    Обрабатывает обе кнопки:
      writeoff:<phone>:all
      writeoff:<phone>:custom:<total>
    """
    _, phone, mode, total_str = query.data.split(":")
    total = int(total_str)

    # получаем клиента
    async with async_session() as session:
        result = await session.execute(
            select(Clients).where(Clients.phone_number == phone)
        )
        client = result.scalar_one_or_none()

    if not client:
        return await query.answer("❗️ Клиент не найден", show_alert=True)

    if mode == "all":
        # Если у нас есть order total>0, списываем не больше min(points, total), иначе всё
        remove = min(client.points, total) if total > 0 else client.points
        client.points -= remove
        session.add(client)
        await session.commit()

        to_pay = max(0, total - remove)
        await query.message.edit_text(
            f"✅ Списано {remove} баллов у <b>{client.name}</b> ({phone}).\n" +
            f"📊 Осталось баллов: <b>{client.points}</b>\n" +
            (f"💰 Осталось к оплате: <b>{to_pay}</b>" if total > 0 else ""),
            parse_mode="HTML"
        )
        await query.answer()
    else:
        # custom: спрашиваем, сколько списать, и сохраняем в FSM: телефон + исходную сумму
        await query.message.answer(
            f"Сколько баллов списать у <b>{client.name}</b> ({phone})? Введите число:",
            parse_mode="HTML"
        )
        await state.set_state(WriteoffStates.waiting_for_amount)
        await state.update_data(phone=phone, total=total or 0)
        await query.answer()


@admin_router.message(
    StateFilter(WriteoffStates.waiting_for_amount),
    F.from_user.id.in_(settings.ADMIN_IDS),
)
async def process_writeoff_amount(message: Message, state: FSMContext):
    """
    После custom-сценария: админ вводит число.
    Нужно:
      - проверить корректность
      - убедиться, что у клиента достаточно баллов
      - списать
      - в ответе указать:
            - сколько списано
            - сколько осталось баллов
            - сколько осталось доплатить (total - списано)
    """
    data = await state.get_data()
    phone = data["phone"]
    total = data.get("total", 0)

    # проверяем ввод
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="cancel_action")]])
    try:
        amount = int(message.text.strip())
        if amount <= 0:
            raise ValueError
    except ValueError:
        return await message.reply("❗️ Введите корректное положительное число", reply_markup=kb)

    # получаем клиента ещё раз
    async with async_session() as session:
        result = await session.execute(
            select(Clients).where(Clients.phone_number == phone)
        )
        client = result.scalar_one_or_none()

        if not client:
            await message.reply("❗️ Клиент не найден")
            await state.clear()
            return

        # проверяем, чтобы не списать больше, чем у клиента и не больше заказа
        if amount > client.points:
            return await message.reply(f"❗️ У клиента всего {client.points} баллов", reply_markup=kb)
        if total > 0 and amount > total:
            return await message.reply(f"❗️ Нельзя списать больше, чем сумма заказа ({total})", reply_markup=kb)

        # списываем
        client.points -= amount
        session.add(client)
        await session.commit()

    # расчёт оставшейся к оплате суммы
    to_pay = max(0, total - amount)

    await message.reply(
        (
            f"✅ Списано {amount} баллов у <b>{client.name}</b> ({phone}).\n"
            f"📊 Осталось баллов: <b>{client.points}</b>\n"
            f"💰 Осталось к оплате: <b>{to_pay}</b>"
        ),
        parse_mode="HTML"
    )
    await state.clear()


# ─── Обработчики начисления баллов ──────────────────────────────────────────

@admin_router.callback_query(
    F.data.startswith("add_points:"),
    F.from_user.id.in_(settings.ADMIN_IDS),
)
async def callback_add_points(query: CallbackQuery, state: FSMContext):
    phone = query.data.split(":")[1]
    
    async with async_session() as session:
        result = await session.execute(
            select(Clients).where(Clients.phone_number == phone)
        )
        client = result.scalar_one_or_none()

    if not client:
        return await query.answer("❗️ Клиент не найден", show_alert=True)

    await query.message.answer(
        f"Сколько баллов начислить клиенту <b>{client.name}</b> ({phone})?\n"
        "Введите положительное число:",
        parse_mode="HTML"
    )
    await state.set_state(AddPointsStates.waiting_for_amount)
    await state.update_data(phone=phone)
    await query.answer()


@admin_router.message(
    StateFilter(AddPointsStates.waiting_for_amount),
    F.from_user.id.in_(settings.ADMIN_IDS),
)
async def process_add_amount(message: Message, state: FSMContext):
    data = await state.get_data()
    phone = data["phone"]
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="◀️ Назад", callback_data="cancel_action")
    ]])
    
    try:
        amount = int(message.text.strip())
        if amount <= 0:
            raise ValueError
    except ValueError:
        return await message.reply("❗️ Введите положительное целое число", reply_markup=kb)

    MAX_INT32 = 2_147_483_647
    async with async_session() as session:
        result = await session.execute(
            select(Clients).where(Clients.phone_number == phone)
        )
        client = result.scalar_one_or_none()

        if not client:
            await message.reply("❗️ Клиент не найден")
            await state.clear()
            return

        new_points = client.points + amount
        if new_points > MAX_INT32:
            await message.reply(f"❗️ Сумма баллов превышает максимально допустимое значение ({MAX_INT32}). Попробуйте начислить меньше.", reply_markup=kb)
            return

        client.points = new_points
        session.add(client)
        await session.commit()

        await message.reply(
            f"✅ Начислено <b>{amount}</b> баллов клиенту <b>{client.name}</b> ({phone})\n"
            f"📊 Новый баланс: <b>{client.points}</b>",
            parse_mode="HTML"
        )
        await state.clear()


# ─── Обработчик кнопки "Назад" ──────────────────────────────────────────────

@admin_router.callback_query(F.data == "cancel_action", F.from_user.id.in_(settings.ADMIN_IDS))
async def cancel_action(query: CallbackQuery, state: FSMContext):
    await state.clear()
    text = (
        "👋 <b>Админ-панель</b>\n\n"
        "Отправьте номер телефона клиента — получите его баланс.\n"
        "Можно сразу добавить сумму через пробел, например:\n"
        "  +79990001122 1500\n\n"
        "Форматы телефона:\n"
        " • +7XXXXXXXXXX\n"
        " • 8XXXXXXXXXX (заменю 8→+7)\n"
        " • XXXXXXXXXX  (добавлю +7)\n\n"
        "Команды:\n"
        " /help — подсказка\n"
    )
    await query.message.edit_text(text, parse_mode="HTML")
    await query.answer()


# ─── 3) Общий хэндлер «телефон [+ сумма]» ────────────────────────────────────

PHONE_RE = re.compile(r"""
    ^\s*
    (?:\+7|8)?          # +7 или 8 в начале, опционально
    (\d{10})            # 10 цифр
    (?:\s+(\d+))?       # опционально - пробел и сумма
    \s*$
""", re.VERBOSE)


# Основной хендлер для номера телефона и суммы
@admin_router.message(
    ~F.state,  # только если FSM НЕ ожидает число
    F.from_user.id.in_(settings.ADMIN_IDS),
)
async def handle_phone_and_amount(message: Message):
    m = PHONE_RE.match(message.text)
    if not m:
        # Не удалось разобрать сообщение - выводим подсказку
        return await message.reply(
            "❗️ Не удалось разобрать сообщение. Пожалуйста, используйте формат из /help.",
            parse_mode="HTML"
        )

    raw, amount_str = m.group(1), m.group(2)
    phone = f"+7{raw}"

    # получаем клиента
    async with async_session() as session:
        result = await session.execute(
            select(Clients).where(Clients.phone_number == phone)
        )
        client = result.scalar_one_or_none()

    if not client:
        return await message.reply(
            f"⚠️ Клиент <b>{phone}</b> не найден.", parse_mode="HTML"
        )
    if not client.is_in_loyalty:
        return await message.reply(
            f"⚠️ Клиент <b>{phone}</b> не в программе лояльности.", parse_mode="HTML"
        )

    name = client.name
    pts = client.points

    # Кнопки «списать всё», «списать custom» и «начислить»
    total_str = amount_str or "0"
    kb = InlineKeyboardMarkup(inline_keyboard=[[
         InlineKeyboardButton(
             text="🗑 Списать все баллы",
             callback_data=f"writeoff:{phone}:all:{total_str}"
         ),
         InlineKeyboardButton(
             text="✏️ Списать другое количество",
             callback_data=f"writeoff:{phone}:custom:{total_str}"
         ),
     ], [
         InlineKeyboardButton(
             text="➕ Начислить баллы",
             callback_data=f"add_points:{phone}"
         )
     ]])

    # Тело сообщения
    if not amount_str:
        text = f"📊 Баллы <b>{name}</b> ({phone}): <b>{pts}</b>\n\nВыберите действие:"
    else:
        total = int(amount_str)
        to_pay = max(0, total - pts)
        text = (
            f"📊 Баллы <b>{name}</b> ({phone}): <b>{pts}</b>\n"
            f"💰 Если списать все баллы – к оплате: <b>{to_pay}</b>\n"
            f"После операции останется <b>{max(0, pts - total)}</b> баллов\n\n"
            "Выберите вариант списания или начислите баллы:"
        )

    await message.reply(text, reply_markup=kb, parse_mode="HTML")