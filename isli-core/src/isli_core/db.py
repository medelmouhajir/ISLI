from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from isli_core.models import Base

engine = None
async_session = None


async def init_db(database_url: str):
    global engine, async_session
    engine = create_async_engine(database_url, echo=False, future=True)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    if async_session is None:
        raise RuntimeError("Database not initialized")
    async with async_session() as session:
        yield session


async def close_db():
    global engine
    if engine:
        await engine.dispose()
