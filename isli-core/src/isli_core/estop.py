import asyncio
import structlog

from redis.asyncio import Redis

logger = structlog.get_logger()

ESTOP_CHANNEL = "isli:estop"
ESTOP_KEY = "isli:estop:active"


class EStopManager:
    """Global emergency stop via Redis pub/sub."""

    def __init__(self, redis: Redis):
        self.redis = redis
        self._active = False
        self._pubsub = None
        self._listener_task: asyncio.Task | None = None

    async def start(self) -> None:
        self._pubsub = self.redis.pubsub()
        await self._pubsub.subscribe(ESTOP_CHANNEL)
        self._listener_task = asyncio.create_task(self._listen())
        # Check if already active from previous session
        active = await self.redis.get(ESTOP_KEY)
        self._active = bool(active)
        logger.info("estop.started", active=self._active)

    async def stop(self) -> None:
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
        if self._pubsub:
            await self._pubsub.unsubscribe(ESTOP_CHANNEL)
            await self._pubsub.close()
        logger.info("estop.stopped")

    async def trigger(self, reason: str = "manual") -> None:
        self._active = True
        await self.redis.set(ESTOP_KEY, "1")
        await self.redis.publish(ESTOP_CHANNEL, f"TRIGGER:{reason}")
        logger.warning("estop.triggered", reason=reason)

    async def reset(self) -> None:
        self._active = False
        await self.redis.delete(ESTOP_KEY)
        await self.redis.publish(ESTOP_CHANNEL, "RESET")
        logger.info("estop.reset")

    @property
    def active(self) -> bool:
        return self._active

    async def _listen(self) -> None:
        while True:
            try:
                message = await self._pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message is None:
                    continue
                data = message["data"]
                if isinstance(data, bytes):
                    data = data.decode("utf-8")
                if data.startswith("TRIGGER"):
                    self._active = True
                    logger.warning("estop.received_trigger", data=data)
                elif data == "RESET":
                    self._active = False
                    logger.info("estop.received_reset")
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("estop.listen_error")
                await asyncio.sleep(1)
