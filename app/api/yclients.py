import httpx
from typing import List
from datetime import datetime
from pydantic import BaseModel
from zoneinfo import ZoneInfo
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential
import logging
from app.config import settings

# Настройка логгера для YClientsAPI
logger = logging.getLogger(__name__)

# Общие настройки клиента
CLIENT_TIMEOUT = httpx.Timeout(10.0, connect=5.0)

class Service(BaseModel):
    id: int
    title: str
    cost: int

class ClientInfo(BaseModel):
    id: int
    phone: str

class Record(BaseModel):
    id: int
    paid_full: int
    last_change_date: datetime
    client: ClientInfo
    services: List[Service]

class YClientsAPI:
    BASE = "https://api.yclients.com/api/v1"

    def __init__(self):
        self.company_id = settings.COMPANY_ID
        self.client = httpx.AsyncClient(
            base_url=self.BASE,
            headers={
                "Accept": f"application/vnd.yclients.v2+json",
                "Authorization": f"Bearer {settings.YCLIENTS_PARTNER_TOKEN}, User {settings.YCLIENTS_USER_TOKEN}",
            },
            timeout=CLIENT_TIMEOUT
        )

    async def fetch_records(
        self,
        changed_after: datetime,
        page: int = 1,
        count: int = 100
    ) -> List[dict]:
        spb_tz = ZoneInfo("Europe/Moscow")
        changed_after_str = changed_after.astimezone(spb_tz).strftime("%Y-%m-%dT%H:%M:%S")

        try:
            async for attempt in AsyncRetrying(
                reraise=True,
                stop=stop_after_attempt(3),
                wait=wait_exponential(multiplier=1, min=1, max=10),
                retry=retry_if_exception_type((
                    httpx.ConnectError,
                    httpx.ReadTimeout,
                    httpx.HTTPStatusError
                ))
            ):
                with attempt:
                    resp = await self.client.get(
                        f"/records/{self.company_id}/",
                        params={
                            "changed_after": changed_after_str,
                            "page":          page,
                            "count":         count,
                        },
                    )
                    resp.raise_for_status()
                    return resp.json().get("data", [])
        except Exception as exc:
            # После трех неудачных попыток или других ошибок
            logger.exception(
                "Failed to fetch records from YClients after retries: %s", exc
            )
            # Пробрасываем дальше, чтобы вызывающий код мог обработать или пропустить
            raise

    async def close(self):
        await self.client.aclose()
