"""API tests for isli-channels endpoints."""

import pytest
from httpx import AsyncClient


class TestChannelsAPI:
    @pytest.mark.asyncio
    async def test_health(self, client: AsyncClient):
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["service"] == "isli-channels"

    @pytest.mark.asyncio
    async def test_live(self, client: AsyncClient):
        resp = await client.get("/live")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "alive"

    @pytest.mark.asyncio
    async def test_ready(self, client: AsyncClient):
        resp = await client.get("/ready")
        assert resp.status_code == 200
        data = resp.json()
        assert data["service"] == "isli-channels"
        assert "redis" in data

    @pytest.mark.asyncio
    async def test_chunk_message(self, client: AsyncClient):
        resp = await client.post("/chunk", json={
            "text": "Hello world. This is a test message.",
            "channel": "telegram",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "chunks" in data
        assert len(data["chunks"]) >= 1

    @pytest.mark.asyncio
    async def test_validate_attachment(self, client: AsyncClient):
        resp = await client.post("/validate-attachment", json={
            "mime_type": "image/jpeg",
            "size_bytes": 1024,
            "channel": "telegram",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True

    @pytest.mark.asyncio
    async def test_validate_attachment_too_large(self, client: AsyncClient):
        resp = await client.post("/validate-attachment", json={
            "mime_type": "video/mp4",
            "size_bytes": 100 * 1024 * 1024,
            "channel": "telegram",
        })
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_convert_attachment(self, client: AsyncClient):
        resp = await client.post("/convert-attachment", json={
            "attachment": {
                "mime_type": "image/jpg",
                "size_bytes": 1024,
                "filename": "test.jpg",
            },
            "target_channel": "whatsapp",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "converted" in data
        assert data["converted"]["media_type"] == "image"

    @pytest.mark.asyncio
    async def test_rate_limit_check(self, client: AsyncClient):
        resp = await client.post("/rate-limit/check", json={"channel": "telegram"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["channel"] == "telegram"
        assert isinstance(data["limited"], bool)
