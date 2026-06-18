"""Local model management router — manages local Ollama + Audio model states."""

from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from isli_core.auth import create_internal_token, require_admin_auth
from isli_core.config import get_settings
from isli_core.db import get_db_session_manual
from isli_core.db_utils import get_active_sessions_count
from isli_core.dynamic_config import get_setting, invalidate_cache
from isli_core.models import SystemSetting

router = APIRouter(prefix="/model-management", tags=["model-management"])

# Default permitted local models (fallback when DB setting is absent)
DEFAULT_PERMITTED_MODELS = {
    "gen": ["qwen3:1.7b", "qwen3:4b", "mistral:7b", "qwen2.5-coder:1.5b"],
    "embed": ["nomic-embed-text", "mxbai-embed-large"],
    "stt": ["whisper-tiny", "whisper-base", "whisper-small", "whisper-medium"],
    "tts": ["piper-en-us-lessac-medium", "piper-en-us-amy-medium"],
}


async def _get_permitted_models() -> dict[str, list[str]]:
    """Read permitted models from system_settings, falling back to defaults."""
    async with get_db_session_manual() as session:
        stored = await get_setting(
            session, key="local_permitted_models", scope="system", default=None
        )
    if not stored or not isinstance(stored, dict):
        return {k: list(v) for k, v in DEFAULT_PERMITTED_MODELS.items()}

    merged: dict[str, list[str]] = {}
    for slot in ("gen", "embed", "stt", "tts"):
        combined = stored.get(slot, []) + DEFAULT_PERMITTED_MODELS.get(slot, [])
        merged[slot] = list(dict.fromkeys(combined))
    return merged

class ModelPullRequest(BaseModel):
    slot: str
    model_name: str


class KeeperConfigUpdateRequest(BaseModel):
    num_ctx: int | None = None
    num_batch: int | None = None
    think: bool | None = None


def _keeper_headers() -> dict[str, str]:
    token = create_internal_token("core", ["internal"], expires_minutes=5)
    return {"X-Internal-Auth": token}


def _is_audio_slot(slot: str) -> bool:
    return slot in ("stt", "tts")


@router.get("/status")
async def get_model_status():
    settings = get_settings()
    current = {}
    available_ollama = []
    available_audio = []
    keeper_status = "offline"
    audio_status = "offline"

    # Query Keeper for gen/embed
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{settings.keeper_url}/dashboard", headers=_keeper_headers())
            resp.raise_for_status()
            data = resp.json()
            current["gen"] = data["identity"]["default_gen_model"]
            current["embed"] = data["identity"]["default_embed_model"]
            keeper_status = data["health"]["status"]

            models_resp = await client.get(f"{settings.keeper_url}/models", headers=_keeper_headers())
            if models_resp.status_code == 200:
                available_ollama = models_resp.json().get("models", [])
    except Exception:
        pass

    # Query Audio service for stt/tts
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            config_resp = await client.get(f"{settings.audio_url}/admin/config", headers=_keeper_headers())
            if config_resp.status_code == 200:
                cfg = config_resp.json().get("config", {})
                current["stt"] = cfg.get("stt", "")
                current["tts"] = cfg.get("tts", "")
                audio_status = "online"

            models_resp = await client.get(f"{settings.audio_url}/models", headers=_keeper_headers())
            if models_resp.status_code == 200:
                mdata = models_resp.json()
                available_audio = mdata.get("stt", []) + mdata.get("tts", [])
    except Exception:
        pass

    overall_status = "online" if keeper_status in ("online", "ready", "ok") or audio_status == "online" else "offline"

    # Ensure all expected keys exist even if services are offline
    current.setdefault("gen", "")
    current.setdefault("embed", "")
    current.setdefault("stt", "")
    current.setdefault("tts", "")

    permitted = await _get_permitted_models()

    return {
        "current": current,
        "permitted": permitted,
        "available": {
            "ollama": available_ollama,
            "audio": available_audio,
        },
        "status": overall_status,
    }


@router.get("/config")
async def get_keeper_config():
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{settings.keeper_url}/admin/config",
                headers=_keeper_headers(),
            )
            resp.raise_for_status()
            return resp.json()
    except Exception:
        raise HTTPException(status_code=503, detail="Keeper unavailable") from None


@router.put("/config")
async def update_keeper_config(
    payload: KeeperConfigUpdateRequest,
    admin: str = Depends(require_admin_auth),
):
    settings = get_settings()
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{settings.keeper_url}/admin/config",
                json=payload.model_dump(exclude_unset=True),
                headers=_keeper_headers(),
            )
            resp.raise_for_status()
            return resp.json()
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="Keeper unavailable") from None


class ModelActivateRequest(BaseModel):
    slot: str
    model_name: str


class ModelRemoveRequest(BaseModel):
    model_name: str


def _check_active_sessions():
    from isli_core.db import get_db_session_manual
    async def _inner():
        async with get_db_session_manual() as session:
            active_count = await get_active_sessions_count(session)
        if active_count > 0:
            raise HTTPException(
                status_code=409,
                detail=f"Model switch blocked: {active_count} active sessions in progress."
            )
    return _inner


@router.post("/activate")
async def activate_model(
    payload: ModelActivateRequest,
    admin: str = Depends(require_admin_auth),
):
    await _check_active_sessions()()

    permitted = await _get_permitted_models()
    if payload.model_name not in permitted.get(payload.slot, []):
        raise HTTPException(status_code=400, detail="Model not in permitted list")

    settings = get_settings()
    target_url = (
        f"{settings.audio_url}/admin/activate"
        if _is_audio_slot(payload.slot)
        else f"{settings.keeper_url}/admin/activate"
    )

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            target_url,
            json=payload.model_dump(),
            headers=_keeper_headers(),
        )
        resp.raise_for_status()
        return resp.json()


@router.post("/remove")
async def remove_model(
    payload: ModelRemoveRequest,
    admin: str = Depends(require_admin_auth),
):
    permitted = await _get_permitted_models()

    # Validate model appears in any permitted slot
    all_permitted: set[str] = set()
    for slot_models in permitted.values():
        if isinstance(slot_models, list):
            all_permitted.update(slot_models)

    if payload.model_name not in all_permitted:
        raise HTTPException(status_code=400, detail="Model not in permitted list")

    settings = get_settings()
    # Determine slot from model name
    target_slot = None
    for slot, models in permitted.items():
        if isinstance(models, list) and payload.model_name in models:
            target_slot = slot
            break

    if target_slot is None:
        raise HTTPException(status_code=400, detail="Could not determine slot for model")

    target_url = (
        f"{settings.audio_url}/admin/remove"
        if _is_audio_slot(target_slot)
        else f"{settings.keeper_url}/admin/remove"
    )

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            target_url,
            json={"model_name": payload.model_name, "slot": target_slot},
            headers=_keeper_headers(),
        )
        resp.raise_for_status()
        return resp.json()


@router.post("/pull", status_code=status.HTTP_202_ACCEPTED)
async def pull_model(
    payload: ModelPullRequest,
    admin: str = Depends(require_admin_auth),
):
    permitted = await _get_permitted_models()
    if payload.model_name not in permitted.get(payload.slot, []):
        raise HTTPException(status_code=400, detail="Model not in permitted list")

    settings = get_settings()
    target_url = (
        f"{settings.audio_url}/admin/pull"
        if _is_audio_slot(payload.slot)
        else f"{settings.keeper_url}/admin/pull"
    )

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            target_url,
            json=payload.model_dump(),
            headers=_keeper_headers(),
        )
        resp.raise_for_status()
        return resp.json()


# ─── Dynamic permitted-model list management ───────────────────────────

class PermittedModelAddRequest(BaseModel):
    slot: str
    model_name: str


@router.post("/permitted")
async def add_permitted_model(
    payload: PermittedModelAddRequest,
    admin: str = Depends(require_admin_auth),
) -> dict[str, Any]:
    if payload.slot not in ("gen", "embed", "stt", "tts"):
        raise HTTPException(status_code=400, detail="Invalid slot")

    model_name = payload.model_name.strip()
    if not model_name or len(model_name) > 128:
        raise HTTPException(status_code=400, detail="model_name must be 1-128 chars")

    permitted = await _get_permitted_models()
    if model_name in permitted.get(payload.slot, []):
        raise HTTPException(status_code=409, detail="Model already in permitted list for this slot")

    permitted.setdefault(payload.slot, []).append(model_name)

    async with get_db_session_manual() as session:
        result = await session.execute(
            select(SystemSetting).where(
                SystemSetting.key == "local_permitted_models",
                SystemSetting.scope == "system",
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            row = SystemSetting(
                key="local_permitted_models",
                scope="system",
                value=permitted,
                description="Permitted local models per slot for Keeper and Audio services.",
            )
            session.add(row)
        else:
            row.value = permitted

        await session.commit()

    invalidate_cache(key="local_permitted_models")
    return {"status": "ok", "slot": payload.slot, "model": model_name, "permitted": permitted}


@router.delete("/permitted/{slot}/{model_name}")
async def remove_permitted_model(
    slot: str,
    model_name: str,
    admin: str = Depends(require_admin_auth),
) -> dict[str, Any]:
    if slot not in ("gen", "embed", "stt", "tts"):
        raise HTTPException(status_code=400, detail="Invalid slot")

    permitted = await _get_permitted_models()
    slot_list = permitted.get(slot, [])
    if model_name not in slot_list:
        raise HTTPException(status_code=404, detail="Model not found in slot")

    slot_list.remove(model_name)
    if not slot_list:
        permitted.pop(slot, None)

    async with get_db_session_manual() as session:
        result = await session.execute(
            select(SystemSetting).where(
                SystemSetting.key == "local_permitted_models",
                SystemSetting.scope == "system",
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="Setting not found")

        row.value = permitted
        await session.commit()

    invalidate_cache(key="local_permitted_models")
    return {"status": "ok", "removed": model_name, "slot": slot, "permitted": permitted}
