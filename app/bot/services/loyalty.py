from datetime import datetime, timezone
from app.db.models import BonusLog, Clients

async def award_points(session, client: Clients, record_id: int, points: int):
    """
    Начисление баллов клиенту и логирование операции, выделено в отдельный метод
    """
    # Обновляем баланс
    client.points += points
    session.add(client)

    # Явно используем наивное время для вставки в TIMESTAMP WITHOUT TIME ZONE
    naive_now = datetime.now(timezone.utc).replace(tzinfo=None)
    session.add(BonusLog(
        record_id=record_id,
        client_id=client.id,
        points=points,
        awarded_at=naive_now
    ))
