from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from isli_core.models import Base

engine = None
async_session = None


async def init_db(database_url: str):
    global engine, async_session
    
    engine_kwargs = {
        "echo": False,
        "future": True,
        "pool_pre_ping": True
    }
    
    if "sqlite" not in database_url.lower():
        engine_kwargs.update({
            "pool_size": 20,
            "max_overflow": 10,
        })

    engine = create_async_engine(database_url, **engine_kwargs)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    if async_session is None:
        raise RuntimeError("Database not initialized")
    async with async_session() as session:
        yield session


@asynccontextmanager
async def get_db_session_manual():
    if async_session is None:
        raise RuntimeError("Database not initialized")
    async with async_session() as session:
        yield session


async def close_db():
    global engine
    if engine:
        await engine.dispose()
