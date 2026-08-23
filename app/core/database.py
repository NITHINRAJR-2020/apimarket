from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

settings = get_settings()


class Base(DeclarativeBase):
    pass


def _build_engine() -> AsyncEngine:
    url = settings.DATABASE_URL
    connect_args: dict = {}

    if url.startswith("postgresql+asyncpg://") and (
        "sslmode=require" in url or "ssl=require" in url or "neon.tech" in url
    ):
        connect_args["ssl"] = True

    clean_url = url.split("?")[0]

    kwargs = dict(echo=settings.DB_ECHO, connect_args=connect_args)
    if not clean_url.startswith("sqlite"):
        kwargs["pool_pre_ping"] = True

    return create_async_engine(clean_url, **kwargs)


engine: AsyncEngine = _build_engine()

AsyncSessionLocal = async_sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_models() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
