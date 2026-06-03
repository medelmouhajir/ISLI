"""Settings router — global configuration endpoints."""

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from isli_core.db import get_db
from isli_core.models import LlmProvider, PermittedModel, SystemSetting
from isli_core.auth import require_admin_auth
from isli_core.audit_writer import AuditWriter
from isli_core.dynamic_config import invalidate_cache

router = APIRouter(prefix="/settings", tags=["settings"])


class PermittedModelIn(BaseModel):
    model_id: str
    name: str | None = None
    enabled: bool = True


class PermittedModelOut(PermittedModelIn):
    id: int
    created_at: datetime

    model_config = {"from_attributes": True}


class ProviderOut(BaseModel):
    provider: str
    enabled: bool
    has_api_key: bool
    api_key_mask: str | None
    models: list[PermittedModelOut]


class ProviderUpsert(BaseModel):
    api_key: str | None = None
    enabled: bool = True


class SettingOut(BaseModel):
    key: str
    scope: str
    value: Any
    description: str | None
    updated_at: datetime


class SettingUpsert(BaseModel):
    value: Any
    description: str | None = None


def _mask_key(key: str | None) -> str | None:
    if not key:
        return None
    if len(key) <= 8:
        return "***"
    return f"{key[:3]}...{key[-4:]}"


def _build_provider_out(provider: LlmProvider, models: list[PermittedModel]) -> ProviderOut:
    return ProviderOut(
        provider=provider.provider,
        enabled=provider.enabled,
        has_api_key=bool(provider.api_key),
        api_key_mask=_mask_key(provider.api_key),
        models=[PermittedModelOut.model_validate(m) for m in models],
    )


@router.get("/providers", response_model=list[ProviderOut])
async def list_providers(db: AsyncSession = Depends(get_db), _admin: str = Depends(require_admin_auth)):
    result = await db.execute(select(LlmProvider))
    providers = result.scalars().all()

    out: list[ProviderOut] = []
    for provider in providers:
        model_result = await db.execute(
            select(PermittedModel).where(PermittedModel.provider == provider.provider)
        )
        models = model_result.scalars().all()
        out.append(_build_provider_out(provider, models))
    return out


@router.get("/providers/{provider}", response_model=ProviderOut)
async def get_provider(provider: str, db: AsyncSession = Depends(get_db), _admin: str = Depends(require_admin_auth)):
    result = await db.execute(select(LlmProvider).where(LlmProvider.provider == provider))
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Provider not found")

    model_result = await db.execute(
        select(PermittedModel).where(PermittedModel.provider == provider)
    )
    models = model_result.scalars().all()
    return _build_provider_out(row, models)


@router.put("/providers/{provider}", response_model=ProviderOut)
async def update_provider(
    provider: str,
    payload: ProviderUpsert,
    db: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin_auth),
):
    result = await db.execute(select(LlmProvider).where(LlmProvider.provider == provider))
    row = result.scalar_one_or_none()

    if row is None:
        row = LlmProvider(provider=provider, api_key=payload.api_key, enabled=payload.enabled)
        db.add(row)
    else:
        if payload.api_key is not None:
            row.api_key = payload.api_key
        row.enabled = payload.enabled
        row.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(row)

    await AuditWriter.write(
        db,
        actor_type="admin",
        actor_id="settings-api",
        action="update_provider",
        target_type="provider",
        target_id=provider,
        payload={"enabled": row.enabled, "api_key_set": bool(row.api_key)},
    )
    await db.commit()

    model_result = await db.execute(
        select(PermittedModel).where(PermittedModel.provider == provider)
    )
    models = model_result.scalars().all()
    return _build_provider_out(row, models)


@router.delete("/providers/{provider}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_provider(
    provider: str,
    db: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin_auth),
):
    result = await db.execute(select(LlmProvider).where(LlmProvider.provider == provider))
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Provider not found")

    row.enabled = False
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()

    await AuditWriter.write(
        db,
        actor_type="admin",
        actor_id="settings-api",
        action="disable_provider",
        target_type="provider",
        target_id=provider,
    )
    await db.commit()
    return


@router.get("/providers/{provider}/models", response_model=list[PermittedModelOut])
async def list_provider_models(
    provider: str,
    db: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin_auth),
):
    result = await db.execute(
        select(PermittedModel).where(PermittedModel.provider == provider)
    )
    return result.scalars().all()


@router.post(
    "/providers/{provider}/models",
    response_model=PermittedModelOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_provider_model(
    provider: str,
    payload: PermittedModelIn,
    db: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin_auth),
):
    provider_result = await db.execute(select(LlmProvider).where(LlmProvider.provider == provider))
    if not provider_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Provider not found")

    existing = await db.execute(
        select(PermittedModel).where(
            PermittedModel.provider == provider,
            PermittedModel.model_id == payload.model_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Model already exists for this provider")

    model = PermittedModel(
        provider=provider,
        model_id=payload.model_id,
        name=payload.name,
        enabled=payload.enabled,
    )
    db.add(model)
    await db.commit()
    await db.refresh(model)

    await AuditWriter.write(
        db,
        actor_type="admin",
        actor_id="settings-api",
        action="add_permitted_model",
        target_type="provider",
        target_id=provider,
        payload={"model_id": payload.model_id, "name": payload.name},
    )
    await db.commit()

    return model


@router.delete("/providers/{provider}/models/{model_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_provider_model(
    provider: str,
    model_id: str,
    db: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin_auth),
):
    result = await db.execute(
        select(PermittedModel).where(
            PermittedModel.provider == provider,
            PermittedModel.model_id == model_id,
        )
    )
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")

    await db.delete(model)
    await db.commit()

    await AuditWriter.write(
        db,
        actor_type="admin",
        actor_id="settings-api",
        action="delete_permitted_model",
        target_type="provider",
        target_id=provider,
        payload={"model_id": model_id},
    )
    await db.commit()
    return


# ─── Generic System Settings endpoints ──────────────────────────────

@router.get("", response_model=list[SettingOut])
async def list_settings(
    scope: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin_auth),
):
    stmt = select(SystemSetting)
    if scope:
        stmt = stmt.where(SystemSetting.scope == scope)
    stmt = stmt.order_by(SystemSetting.key)
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [
        SettingOut(
            key=r.key,
            scope=r.scope,
            value=r.value,
            description=r.description,
            updated_at=r.updated_at,
        )
        for r in rows
    ]


@router.get("/{key}", response_model=SettingOut)
async def get_setting(
    key: str,
    db: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin_auth),
):
    result = await db.execute(select(SystemSetting).where(SystemSetting.key == key))
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Setting not found")
    return SettingOut(
        key=row.key,
        scope=row.scope,
        value=row.value,
        description=row.description,
        updated_at=row.updated_at,
    )


@router.put("/{key}", response_model=SettingOut)
async def update_setting(
    key: str,
    payload: SettingUpsert,
    db: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin_auth),
):
    result = await db.execute(select(SystemSetting).where(SystemSetting.key == key))
    row = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)
    if row is None:
        row = SystemSetting(
            key=key,
            scope="global",
            value=payload.value,
            description=payload.description,
            updated_at=now,
            updated_by="admin",
        )
        db.add(row)
    else:
        row.value = payload.value
        if payload.description is not None:
            row.description = payload.description
        row.updated_at = now
        row.updated_by = "admin"

    await db.commit()
    await db.refresh(row)
    invalidate_cache(key=key)

    await AuditWriter.write(
        db,
        actor_type="admin",
        actor_id="settings-api",
        action="update_setting",
        target_type="setting",
        target_id=key,
        payload={"value": payload.value},
    )
    await db.commit()

    return SettingOut(
        key=row.key,
        scope=row.scope,
        value=row.value,
        description=row.description,
        updated_at=row.updated_at,
    )


@router.delete("/{key}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_setting(
    key: str,
    db: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin_auth),
):
    result = await db.execute(select(SystemSetting).where(SystemSetting.key == key))
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Setting not found")

    await db.delete(row)
    await db.commit()
    invalidate_cache(key=key)

    await AuditWriter.write(
        db,
        actor_type="admin",
        actor_id="settings-api",
        action="delete_setting",
        target_type="setting",
        target_id=key,
    )
    await db.commit()
    return
