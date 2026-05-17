import asyncio
import json
import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, status
from isli_core.redis_client import get_redis
from isli_core.auth import verify_internal_token

logger = structlog.get_logger()
router = APIRouter(prefix="/ws", tags=["websocket"])

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
        if agent_id in self.agent_connections:
            for connection in self.agent_connections[agent_id]:
                try:
                    await connection.send_text(message)
                except Exception as exc:
                    logger.warning("ws.agent_send_failed", agent_id=agent_id, error=str(exc))

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
            logger.debug("ws.agent_received", agent_id=agent_id, data=data)
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
                        
                        if target_agent_id:
                            await manager.send_to_agent(target_agent_id, data)
                    except Exception as e:
                        logger.debug("ws.dispatch_failed", error=str(e))
                        
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
