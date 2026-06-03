import asyncio
import structlog
from datetime import datetime, timedelta, timezone
import httpx

from isli_core.db import async_session
from isli_core.config import get_settings
from isli_core.auth import create_internal_token

logger = structlog.get_logger()

AUDIO_RETENTION_DAYS = 7


class AudioCleanupWorker:
    """Periodically purge session audio files older than 7 days from workspace."""

    @classmethod
    async def run_once(cls) -> None:
        settings = get_settings()
        token = create_internal_token("core-api", scopes=["workspace"], expires_minutes=5)
        headers = {"X-Internal-Auth": f"Bearer {token}"}

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                # List all audio directories under _attachments/audio
                url = f"{settings.workspace_url}/list"
                resp = await client.post(
                    url,
                    json={
                        "agent_id": "system",
                        "scope": "attachment",
                        "scope_id": "audio",
                        "path": ".",
                    },
                    headers=headers,
                )
                if resp.status_code != 200:
                    logger.warning("audio_cleanup.list_failed", status=resp.status_code)
                    return

                data = resp.json()
                entries = data.get("entries", [])
                cutoff = datetime.now(timezone.utc) - timedelta(days=AUDIO_RETENTION_DAYS)
                deleted = 0

                for entry in entries:
                    # Each entry is a session directory; we need to list files inside
                    session_path = entry.get("name", "")
                    if not session_path:
                        continue

                    files_resp = await client.post(
                        url,
                        json={
                            "agent_id": "system",
                            "scope": "attachment",
                            "scope_id": f"audio/{session_path}",
                            "path": ".",
                        },
                        headers=headers,
                    )
                    if files_resp.status_code != 200:
                        continue

                    files_data = files_resp.json()
                    for file_entry in files_data.get("entries", []):
                        mtime_str = file_entry.get("modified_at")
                        if mtime_str:
                            try:
                                mtime = datetime.fromisoformat(mtime_str.replace("Z", "+00:00"))
                            except Exception:
                                continue
                            if mtime < cutoff:
                                delete_url = f"{settings.workspace_url}/delete"
                                del_resp = await client.post(
                                    delete_url,
                                    json={
                                        "agent_id": "system",
                                        "scope": "attachment",
                                        "scope_id": f"audio/{session_path}",
                                        "path": file_entry["name"],
                                    },
                                    headers=headers,
                                )
                                if del_resp.status_code in (200, 404):
                                    deleted += 1
                                else:
                                    logger.warning(
                                        "audio_cleanup.delete_failed",
                                        path=file_entry["name"],
                                        status=del_resp.status_code,
                                    )

                if deleted > 0:
                    logger.info("audio_cleanup.completed", deleted=deleted)
            except Exception as exc:
                logger.error("audio_cleanup.error", error=str(exc))

    @classmethod
    async def loop(cls) -> None:
        while True:
            try:
                if async_session:
                    await cls.run_once()
            except Exception as exc:
                logger.error("audio_cleanup.loop_error", error=str(exc))

            # Run once every 24 hours
            await asyncio.sleep(86400)
