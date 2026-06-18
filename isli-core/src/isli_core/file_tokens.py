import uuid
import json
from typing import Any
from redis.asyncio import Redis

TOKEN_PREFIX = "file_token:"
TOKEN_TTL = 300  # 5 minutes

async def create_file_token(redis: Redis, scope: str, scope_id: str, path: str) -> str:
    """
    Generate a secure random token and store file metadata in Redis.
    """
    token = str(uuid.uuid4())
    key = f"{TOKEN_PREFIX}{token}"
    data = {
        "scope": scope,
        "scope_id": scope_id,
        "path": path
    }
    await redis.setex(key, TOKEN_TTL, json.dumps(data))
    return token

async def consume_file_token(redis: Redis, token: str) -> dict[str, Any] | None:
    """
    Atomically retrieve and delete file metadata associated with a token.
    Ensures single-use consumption.
    """
    key = f"{TOKEN_PREFIX}{token}"
    
    # Use Lua script for atomic GET and DEL to ensure single-use even on older Redis versions
    lua_script = """
    local val = redis.call('GET', KEYS[1])
    if val then
        redis.call('DEL', KEYS[1])
        return val
    else
        return nil
    end
    """
    val = await redis.eval(lua_script, 1, key)
    
    if val:
        return json.loads(val)
    return None
