from datetime import datetime, timezone
from typing import Optional
import sqlalchemy
from sqlalchemy import Column, DateTime, UniqueConstraint

from sqlmodel import SQLModel, Field


class Clients(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    yclients_id: int  = Field(nullable=False, index=True, description="ID клиента в YCLIENTS")
    phone_number: str = Field(nullable=False, index=True, description="Телефон +7XXXXXXXXXX")
    points: int       = Field(default=0, nullable=False, description="Накопленные баллы")
    is_in_loyalty: bool = Field(default=True, nullable=False, description="Участвует в программе лояльности")
    name: str = Field(nullable=False, index=True, description="Имя клиента")
    telegram_user_id: Optional[int] = Field(default=None, sa_column=sqlalchemy.Column(sqlalchemy.BigInteger))


class SyncState(SQLModel, table=True):
    company_id: int = Field(primary_key=True, description="ID филиала")
    last_checked: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False),
        default_factory=lambda: datetime.now(timezone.utc),
        description="Время последнего опроса API"
    )

class BonusLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    record_id: int = Field(index=True, nullable=False, description="ID записи в YClients")
    client_id: int = Field(foreign_key="clients.id", index=True, nullable=False)
    points: int = Field(nullable=False)
    awarded_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False),
        default_factory=lambda: datetime.now(timezone.utc),
        description="Время начисления"
    )
    is_telegram_notified: bool = Field(
        default=False,
        nullable=False,
        sa_column_kwargs={"server_default": sqlalchemy.text("FALSE")}
    )
    __table_args__ = (UniqueConstraint('record_id', name='uix_record_id'),)