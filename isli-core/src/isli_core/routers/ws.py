import asyncio
import json
import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, status
from isli_core.redis_client import get_redis
from isli_core.auth import verify_internal_token, _check_token_revocation

logger = structlog.get_logger()
router = APIRouter(prefix="/ws", tags=["websocket"])

# Lazy import to avoid circular dependency at module load time
_notification_engine = None

def _get_notification_engine():
    global _notification_engine
    if _notification_engine is None:
        from isli_core.notification.notification_engine import NotificationEngine
        _notification_engine = NotificationEngine
    return _notification_engine

class ConnectionManager:
    def __init__(self):
        self.board_connections: list[WebSocket] = []
        self.agent_connections: dict[str, list[WebSocket]] = {}

    async def connect_board(self, websocket: WebSocket):
        await websocket.accept()
        self.board_connections.append(websocket)
        logger.info("ws.board_connected", count=len(self.board_connections))

    def disconnect_board(self, websocket: WebSocket):
        if websocket in self.board_connections:
            self.board_connections.remove(websocket)
            logger.info("ws.board_disconnected", count=len(self.board_connections))

    async def connect_agent(self, websocket: WebSocket, agent_id: str):
        await websocket.accept()
        if agent_id not in self.agent_connections:
            self.agent_connections[agent_id] = []
        self.agent_connections[agent_id].append(websocket)
        logger.info("ws.agent_connected", agent_id=agent_id, count=len(self.agent_connections[agent_id]))
        await self._drain_queued_events(agent_id)

    async def _drain_queued_events(self, agent_id: str):
        try:
            redis = await get_redis()
            queue_key = f"agent:events:{agent_id}"
            while True:
                message = await redis.lpop(queue_key)
                if not message:
                    break
                if agent_id in self.agent_connections and self.agent_connections[agent_id]:
                    for connection in self.agent_connections[agent_id]:
                        try:
                            await connection.send_text(message)
                        except Exception as exc:
                            logger.warning("ws.agent_queued_send_failed", agent_id=agent_id, error=str(exc))
                    logger.info("ws.agent_queued_event_delivered", agent_id=agent_id)
                else:
                    await redis.lpush(queue_key, message)
                    break
        except Exception as exc:
            logger.warning("ws.agent_drain_failed", agent_id=agent_id, error=str(exc))

    def disconnect_agent(self, websocket: WebSocket, agent_id: str):
        if agent_id in self.agent_connections:
            if websocket in self.agent_connections[agent_id]:
                self.agent_connections[agent_id].remove(websocket)
            if not self.agent_connections[agent_id]:
                del self.agent_connections[agent_id]
        logger.info("ws.agent_disconnected", agent_id=agent_id)

    async def broadcast_to_board(self, message: str):
        for connection in self.board_connections:
            try:
                await connection.send_text(message)
            except Exception as exc:
                logger.warning("ws.board_send_failed", error=str(exc))

    async def send_to_agent(self, agent_id: str, message: str):
        if agent_id in self.agent_connections and self.agent_connections[agent_id]:
            for connection in self.agent_connections[agent_id]:
                try:
                    await connection.send_text(message)
                except Exception as exc:
                    logger.warning("ws.agent_send_failed", agent_id=agent_id, error=str(exc))
        else:
            try:
                redis = await get_redis()
                queue_key = f"agent:events:{agent_id}"
                await redis.rpush(queue_key, message)
                await redis.ltrim(queue_key, 0, 49)
                await redis.expire(queue_key, 3600)
                logger.info("ws.agent_event_queued", agent_id=agent_id, queue_key=queue_key)
            except Exception as exc:
                logger.warning("ws.agent_event_queue_failed", agent_id=agent_id, error=str(exc))

manager = ConnectionManager()

@router.websocket("/board")
async def board_ws(websocket: WebSocket):
    await manager.connect_board(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            logger.debug("ws.board_received", data=data)
    except WebSocketDisconnect:
        manager.disconnect_board(websocket)
    except Exception as exc:
        logger.error("ws.board_error", error=str(exc))
        manager.disconnect_board(websocket)

@router.websocket("/agents/{agent_id}")
async def agent_ws(websocket: WebSocket, agent_id: str, token: str = Query(None)):
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    try:
        payload = verify_internal_token(token)
        await _check_token_revocation(payload)
        if payload["sub"] != agent_id:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
    except Exception:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await manager.connect_agent(websocket, agent_id)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                event = json.loads(data)
                if event.get("type") == "agent:stream_event":
                    payload = event.get("payload", {})
                    session_id = payload.get("session_id")
                    event_type = payload.get("event_type")
                    event_data = payload.get("data", {})

                    # Append token_delta to Redis draft
                    if event_type == "token_delta" and session_id:
                        delta = event_data.get("delta", "")
                        if delta:
                            redis = await get_redis()
                            await redis.append(f"session:{session_id}:draft", delta)
                            await redis.expire(f"session:{session_id}:draft", 300)

                    # Store debug events in Redis (never broadcast over WS)
                    if event_type in ("debug_prompt", "debug_response") and session_id:
                        redis = await get_redis()
                        trace_key = f"session:{session_id}:debug_trace"
                        await redis.lpush(trace_key, json.dumps({
                            "event_type": event_type,
                            "data": event_data,
                            "timestamp": payload.get("timestamp"),
                        }))
                        await redis.ltrim(trace_key, 0, 99)
                        await redis.expire(trace_key, 300)
                        continue  # skip broadcast

                    # Fan out to board
                    await manager.broadcast_to_board(json.dumps({
                        "type": "session:stream_event",
                        "payload": {
                            "session_id": session_id,
                            "agent_id": agent_id,
                            "event_type": event_type,
                            "data": event_data,
                            "timestamp": payload.get("timestamp"),
                        }
                    }))
            except Exception as exc:
                logger.warning("ws.agent_message_parse_failed", agent_id=agent_id, error=str(exc))
    except WebSocketDisconnect:
        manager.disconnect_agent(websocket, agent_id)
    except Exception as exc:
        logger.error("ws.agent_error", agent_id=agent_id, error=str(exc))
        manager.disconnect_agent(websocket, agent_id)

async def redis_listener():
    """Background task to listen to Redis Pub/Sub and broadcast to WebSockets with retry."""
    retry_delay = 1.0
    max_delay = 60.0

    while True:
        try:
            redis = await get_redis()
            pubsub = redis.pubsub()
            await pubsub.subscribe("isli:events")

            logger.info("ws.redis_listener_started")
            retry_delay = 1.0  # Reset delay on success

            async for message in pubsub.listen():
                if message["type"] == "message":
                    data = message["data"]
                    if isinstance(data, bytes):
                        data = data.decode("utf-8")

                    # Always broadcast to the board
                    await manager.broadcast_to_board(data)

                    # Targeted delivery to agents
                    try:
                        event = json.loads(data)
                        payload = event.get("payload", {})

                        target_agent_id = None
                        if event.get("type") in ("task:created", "task:updated", "task:moved"):
                            task = payload.get("task", {})
                            target_agent_id = task.get("agent_id")
                        elif event.get("type") == "agent:heartbeat":
                            target_agent_id = payload.get("agent_id")
                        elif event.get("type") == "session:message":
                            target_agent_id = payload.get("agent_id")
                        elif event.get("type") == "agent:config_updated":
                            target_agent_id = payload.get("agent_id")
                            logger.info("ws.config_update_detected", agent_id=target_agent_id)

                        if target_agent_id:
                            is_connected = target_agent_id in manager.agent_connections
                            logger.debug("ws.dispatch_to_agent", agent_id=target_agent_id, connected=is_connected)
                            await manager.send_to_agent(target_agent_id, data)
                    except Exception as e:
                        logger.debug("ws.dispatch_failed", error=str(e))

                    # Unified notification dispatch — return_exceptions=True ensures
                    # a notification engine failure never kills the WebSocket fan-out.
                    try:
                        event = json.loads(data)
                        engine = _get_notification_engine()
                        results = await asyncio.gather(
                            engine.on_event(event.get("type", ""), event.get("payload", {})),
                            return_exceptions=True,
                        )
                        for r in results:
                            if isinstance(r, Exception):
                                logger.error("ws.notification_dispatch_failed", error=str(r))
                    except Exception as e:
                        logger.error("ws.notification_dispatch_failed", error=str(e))

        except asyncio.CancelledError:
            logger.info("ws.redis_listener_cancelled")
            break
        except Exception as exc:
            logger.error("ws.redis_listener_error", error=str(exc), next_retry=retry_delay)
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, max_delay)
        finally:
            try:
                await pubsub.unsubscribe("isli:events")
            except:
                pass


def emit_event(redis, event_type: str, payload: dict):
    """Utility to push an event to Redis for broadcasting."""
    event = {"type": event_type, "payload": payload}
    # In a real app, this would be an async call, but for utility we might want a sync wrapper if needed
    # For now, let's assume caller handles the redis.publish(..., json.dumps(event))
    pass
