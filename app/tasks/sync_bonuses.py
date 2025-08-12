import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select

from app.db.models import BonusLog, SyncState, Clients
from app.db.session import async_session
from app.api.yclients import YClientsAPI

from app.bot.services.loyalty import award_points

# Настройка логирования для задач синхронизации
logger = logging.getLogger(__name__)

async def sync_records(company_id: int):
    """Основная функция синхронизации бонусов для конкретного филиала"""
    api = YClientsAPI()
    try:
        async with async_session() as session:
            start_time = datetime.now(timezone.utc)

            # Получаем или создаём состояние
            state = await _get_or_create_state(session, company_id)
            last_checked_aware = state.last_checked.replace(tzinfo=timezone.utc)
            safe_since = last_checked_aware + timedelta(milliseconds=1)

            # Получаем все новые записи
            pages = await _fetch_all_records(api, safe_since)

            for rec in pages:
                rec_id = rec.get("id")
                if rec_id is None:
                    continue

                # Пропускаем уже обработанные
                if await _is_record_processed(session, rec_id):
                    logger.debug(f"record {rec_id} already processed, skipping")
                    continue

                # Фильтруем неполные или не оплаченные
                if rec.get("paid_full") != 1 or not rec.get("services"):
                    continue

                client_data = rec.get("client")
                if not client_data:
                    continue

                # Обрабатываем каждую запись в отдельной транзакции
                try:
                    async with async_session() as inner_sess:
                        # Проверяем ещё раз внутри транзакции
                        if await _is_record_processed(inner_sess, rec_id):
                            continue

                        client = await _get_client(inner_sess, client_data.get("id"))
                        if not client or not client.is_in_loyalty:
                            continue

                        total_amount = sum(s.get("cost", 0) for s in rec.get("services", []))
                        points = int(total_amount * 0.01)

                        # Начисляем баллы и логируем в БД
                        await award_points(inner_sess, client, rec_id, points)
                        await inner_sess.commit()

                        logger.info(f"Awarded {points} pts to client {client.yclients_id} for record {rec_id}")
                except Exception as e:
                    logger.exception(f"Failed to process record {rec_id}: {e}")

            # После обработки всех - обновляем метку времени
            try:
                state.last_checked = start_time
                session.add(state)
                await session.commit()
                logger.debug(f"SyncState.last_checked updated to {state.last_checked}")
            except Exception as e:
                logger.exception("Failed to update SyncState.last_checked: %s", e)

    except Exception as e:
        # Глобальный обработчик ошибок
        logger.exception(f"Sync failed entirely: {e}")
        try:
            await session.rollback()
        except Exception:
            pass
    finally:
        await api.close()

async def _is_record_processed(session: AsyncSession, record_id: int) -> bool:
    """
    Проверяет, была ли запись уже обработана (начислены бонусы).
    """
    result = await session.execute(
        select(BonusLog).where(BonusLog.record_id == record_id)
    )
    return result.scalar_one_or_none() is not None

async def _get_client(session: AsyncSession, yclients_id: int) -> Optional[Clients]:
    """
    Поиск клиента в базе по ID из YClients.
    """
    result = await session.execute(
        select(Clients).where(Clients.yclients_id == yclients_id)
    )
    return result.scalar_one_or_none()

async def _get_or_create_state(
    session: AsyncSession,
    company_id: int
) -> SyncState:
    state: Optional[SyncState] = await session.get(SyncState, company_id)
    if not state:
        initial = datetime.now(timezone.utc) - timedelta(days=1)
        state = SyncState(company_id=company_id, last_checked=initial)
        session.add(state)
        await session.commit()
        logger.debug(f"Created SyncState company_id={company_id}, initial={initial.isoformat()}")
    return state

async def _fetch_all_records(
    api: YClientsAPI,
    changed_after: datetime,
    page_size: int = 100
) -> List[dict]:
    """
    Загружает все записи из API, изменённые после `changed_after`.
    """
    all_records: List[dict] = []
    page = 1

    while True:
        try:
            batch = await api.fetch_records(
                changed_after=changed_after,
                page=page,
                count=page_size
            )
        except Exception:
            # Ошибка уже залогирована внутри fetch_records
            break

        logger.debug(f"page {page} → {len(batch)} records from API")
        if not batch:
            break

        all_records.extend(batch)
        if len(batch) < page_size:
            break
        page += 1

    logger.info(f"total records fetched from API: {len(all_records)}")
    return all_records
