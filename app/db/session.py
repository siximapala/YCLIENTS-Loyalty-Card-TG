# app/db/session.py
from sqlmodel import SQLModel
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.config import settings

# Параметры пула для asyncpg
# pool_size           - размер пула постоянных соединений
# max_overflow        - сколько «лишних» соединений может создаваться сверх pool_size
# pool_pre_ping       - проверять соединение на «живость» перед выдачей из пула
# pool_recycle        - время (в секундах), после которого соединение будет пересоздано
# pool_timeout        - время ожидания свободного соединения из пула

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=True,
    future=True,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
    pool_recycle=1800,     # пересоздавать соединения раз в полчаса
    pool_timeout=30        # ждать до 30 секунд за соединением
)

async_session = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
