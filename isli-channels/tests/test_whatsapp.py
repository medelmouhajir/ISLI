from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from isli_channels.adapters.whatsapp import WhatsAppAdapter, _normalize_jid


def asyncio_run(coro):
    import asyncio
    return asyncio.get_event_loop().run_until_complete(coro)


class TestJidNormalization:
    def test_plain_jid(self):
        assert _normalize_jid("1234567890@s.whatsapp.net") == "1234567890"

    def test_device_suffix(self):
        assert _normalize_jid("1234567890:2@s.whatsapp.net") == "1234567890"

    def test_bare_number(self):
        assert _normalize_jid("1234567890") == "1234567890"


class TestWhatsAppAdapterInternals:
    def test_session_key(self):
        adapter = WhatsAppAdapter("http://core:8000")
        assert adapter._session_key("agent-1", "12345") == "active_session:whatsapp:agent-1:12345"

    def test_pending_key(self):
        adapter = WhatsAppAdapter("http://core:8000")
        expected = "new_session_pending:whatsapp:agent-1:12345"
        assert adapter._pending_key("agent-1", "12345") == expected


class TestWhatsAppAdapterState:
    @pytest.fixture
    def adapter(self):
        return WhatsAppAdapter(
            core_api_url="http://core:8000",
            webhook_secret="secret",
            sidecar_api_token="token",
            sidecar_webhook_secret="wh-secret",
        )

    @pytest.mark.asyncio
    async def test_create_session_idempotency_open(self, adapter):
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_status_resp = MagicMock()
            mock_status_resp.status_code = 200
            mock_status_resp.json.return_value = {"status": "open"}

            mock_client = AsyncMock()
            mock_client.get.return_value = mock_status_resp
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            mock_client_cls.return_value.__aexit__.return_value = False

            result = await adapter.create_session("agent-x")
            assert result["status"] == "already_connected"

    @pytest.mark.asyncio
    async def test_create_session_idempotency_connecting(self, adapter):
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_status_resp = MagicMock()
            mock_status_resp.status_code = 200
            mock_status_resp.json.return_value = {"status": "connecting"}

            mock_start_resp = MagicMock()
            mock_start_resp.raise_for_status = MagicMock()
            mock_start_resp.json.return_value = {"status": "starting"}

            mock_client = AsyncMock()
            mock_client.get.return_value = mock_status_resp
            mock_client.post.return_value = mock_start_resp
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            mock_client_cls.return_value.__aexit__.return_value = False

            result = await adapter.create_session("agent-y")
            assert result["status"] == "starting"

    def test_get_qr_returns_shape(self, adapter):
        adapter.qr_codes["agent-a"] = "1@qrdata"
        adapter.qr_sequences["agent-a"] = 3

        result = adapter.get_qr("agent-a")
        assert result["qr"] == "1@qrdata"
        assert result["qr_sequence"] == 3
        assert result["qr_expires_at"] is not None

    def test_get_qr_no_qr(self, adapter):
        result = adapter.get_qr("agent-b")
        assert result["qr"] is None
        assert result["qr_sequence"] == 0
        assert result["qr_expires_at"] is None

    def test_get_status(self, adapter):
        adapter.connection_states["agent-c"] = {
            "status": "open",
            "is_new_login": True,
            "last_disconnect_reason": None,
        }
        result = adapter.get_status("agent-c")
        assert result["status"] == "open"
        assert result["is_new_login"] is True
        assert result["last_disconnect_reason"] is None

    def test_get_status_missing(self, adapter):
        result = adapter.get_status("agent-d")
        assert result["status"] == "disconnected"
        assert result["is_new_login"] is False

    def test_list_sessions(self, adapter):
        adapter.connection_states["agent-e"] = {"status": "open", "is_new_login": True}
        adapter.connection_states["agent-f"] = {"status": "connecting", "is_new_login": False}

        result = adapter.list_sessions()
        assert len(result) == 2
        assert result[0]["agent_id"] == "agent-e"
        assert result[0]["status"] == "open"

    @pytest.mark.asyncio
    async def test_delete_session_clears_state(self, adapter):
        adapter.connection_states["agent-g"] = {"status": "open"}
        adapter.qr_codes["agent-g"] = "qr"
        adapter.qr_sequences["agent-g"] = 1

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json.return_value = {"status": "deleted"}
            mock_client = AsyncMock()
            mock_client.delete.return_value = mock_resp
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            mock_client_cls.return_value.__aexit__.return_value = False

            result = await adapter.delete_session("agent-g")
            assert result["status"] == "deleted"
            assert "agent-g" not in adapter.connection_states
            assert "agent-g" not in adapter.qr_codes

    def test_parse_update(self, adapter):
        raw = {"type": "message", "payload": {"key": {"id": "msg-1"}}}
        msg = adapter.parse_update(raw)
        # In proxy mode parse_update returns None
        assert msg is None

    @pytest.mark.asyncio
    async def test_health_check_success(self, adapter):
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"status": "ok"}
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_resp
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            mock_client_cls.return_value.__aexit__.return_value = False

            result = await adapter.health_check()
            assert result is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self, adapter):
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.side_effect = Exception("conn refused")
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            mock_client_cls.return_value.__aexit__.return_value = False

            result = await adapter.health_check()
            assert result is False


class TestSendMessage:
    @pytest.fixture
    def adapter(self):
        return WhatsAppAdapter(
            core_api_url="http://core:8000",
            sidecar_url="http://sidecar:3001",
            sidecar_api_token="token",
        )

    @pytest.mark.asyncio
    async def test_send_message_missing_agent_id(self, adapter):
        result = await adapter.send_message("12345", "hello")
        assert result is False

    @pytest.mark.asyncio
    async def test_send_message_success(self, adapter):
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json.return_value = {"success": True}
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_resp
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            mock_client_cls.return_value.__aexit__.return_value = False

            result = await adapter.send_message("12345", "hello", agent_id="agent-x")
            assert result is True
            mock_client.post.assert_called()
            call_args = mock_client.post.call_args
            assert call_args[1]["json"]["jid"] == "12345@s.whatsapp.net"
            assert call_args[1]["json"]["text"] == "hello"
            assert call_args[1]["headers"]["Authorization"] == "Bearer token"

    @pytest.mark.asyncio
    async def test_send_message_chunking(self, adapter):
        long_text = "a" * 2000
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json.return_value = {"success": True}
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_resp
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            mock_client_cls.return_value.__aexit__.return_value = False

            result = await adapter.send_message("12345", long_text, agent_id="agent-x")
            assert result is True
            assert mock_client.post.call_count == 2

    @pytest.mark.asyncio
    async def test_send_message_retry_then_fail(self, adapter):
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json.return_value = {"success": False}
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_resp
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            mock_client_cls.return_value.__aexit__.return_value = False

            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await adapter.send_message("12345", "hello", agent_id="agent-x")
                assert result is False
                assert mock_client.post.call_count == 4

    @pytest.mark.asyncio
    async def test_send_typing(self, adapter):
        await adapter.send_typing("12345", agent_id="agent-x")


class TestInboundMessageHandling:
    @pytest.fixture
    def adapter(self):
        return WhatsAppAdapter(
            core_api_url="http://core:8000",
            webhook_secret="secret",
            sidecar_api_token="token",
        )

    @pytest.mark.asyncio
    async def test_handle_inbound_text_message(self, adapter):
        data = {
            "key": {"remoteJid": "12345@s.whatsapp.net", "id": "msg-1"},
            "message": {"conversation": "Hello"},
        }
        with patch.object(adapter, "_forward_to_core", new_callable=AsyncMock) as mock_forward:
            await adapter._handle_inbound_message("agent-1", data)
            mock_forward.assert_awaited_once()
            payload = mock_forward.call_args[0][2]
            assert payload["text"] == "Hello"
            assert payload["user_id"] == "12345"

    @pytest.mark.asyncio
    async def test_handle_inbound_attachment(self, adapter):
        data = {
            "key": {"remoteJid": "12345@s.whatsapp.net", "id": "msg-2"},
            "message": {
                "imageMessage": {
                    "mimetype": "image/jpeg",
                    "caption": "My photo",
                    "fileLength": 12345,
                }
            },
        }
        with patch.object(adapter, "_forward_to_core", new_callable=AsyncMock) as mock_forward:
            await adapter._handle_inbound_message("agent-1", data)
            payload = mock_forward.call_args[0][2]
            assert payload["attachments"][0]["type"] == "image"
            assert payload["attachments"][0]["caption"] == "My photo"

    @pytest.mark.asyncio
    async def test_handle_inbound_no_text_no_attachment(self, adapter):
        data = {
            "key": {"remoteJid": "12345@s.whatsapp.net", "id": "msg-3"},
            "message": {},
        }
        with patch.object(adapter, "_forward_to_core", new_callable=AsyncMock) as mock_forward:
            await adapter._handle_inbound_message("agent-1", data)
            mock_forward.assert_not_awaited()


class TestWebhookHandling:
    @pytest.fixture
    def adapter(self):
        return WhatsAppAdapter(
            core_api_url="http://core:8000",
            webhook_secret="secret",
            sidecar_api_token="token",
        )

    @pytest.mark.asyncio
    async def test_handle_webhook_connection_update(self, adapter):
        payload = {"type": "connection.update", "payload": {"connection": "open"}}
        await adapter.handle_webhook("agent-1", payload)
        assert adapter.connection_states["agent-1"]["status"] == "open"

    @pytest.mark.asyncio
    async def test_handle_webhook_qr_code(self, adapter):
        payload = {"type": "connection.update", "payload": {"qr": "QR123", "connection": "connecting"}}
        await adapter.handle_webhook("agent-1", payload)
        assert adapter.qr_codes["agent-1"] == "QR123"
        assert adapter.qr_sequences["agent-1"] == 1

    @pytest.mark.asyncio
    async def test_handle_webhook_duplicate_ignored(self, adapter):
        adapter.idempotency = MagicMock()
        adapter.idempotency.is_duplicate = AsyncMock(return_value=True)
        payload = {"type": "connection.update", "payload": {"connection": "open"}}
        await adapter.handle_webhook("agent-1", payload)
        assert "agent-1" not in adapter.connection_states


class TestRedisSessionTracking:
    @pytest.fixture
    def adapter(self):
        return WhatsAppAdapter(core_api_url="http://core:8000")

    @pytest.mark.asyncio
    async def test_get_active_session_id_from_redis(self, adapter):
        redis = AsyncMock()
        redis.get = AsyncMock(return_value="sess-custom-123")
        adapter.redis = redis

        result = await adapter._get_active_session_id("agent-1", "user-1")
        assert result == "sess-custom-123"
        redis.get.assert_awaited_once_with("active_session:whatsapp:agent-1:user-1")

    @pytest.mark.asyncio
    async def test_get_active_session_id_fallback(self, adapter):
        adapter.redis = None
        result = await adapter._get_active_session_id("agent-1", "user-1")
        assert result == "sess_wa_agent-1_user-1"

    @pytest.mark.asyncio
    async def test_set_active_session_id_with_ttl(self, adapter):
        redis = AsyncMock()
        adapter.redis = redis

        await adapter._set_active_session_id("agent-1", "user-1", "sess-abc")
        redis.setex.assert_awaited_once_with("active_session:whatsapp:agent-1:user-1", 86400 * 30, "sess-abc")

    @pytest.mark.asyncio
    async def test_is_new_session_pending(self, adapter):
        redis = AsyncMock()
        redis.exists = AsyncMock(return_value=1)
        adapter.redis = redis

        result = await adapter._is_new_session_pending("agent-1", "user-1")
        assert result is True

    @pytest.mark.asyncio
    async def test_set_new_session_pending(self, adapter):
        redis = AsyncMock()
        adapter.redis = redis

        await adapter._set_new_session_pending("agent-1", "user-1")
        redis.setex.assert_awaited_once_with("new_session_pending:whatsapp:agent-1:user-1", 10, "1")

    @pytest.mark.asyncio
    async def test_clear_new_session_pending(self, adapter):
        redis = AsyncMock()
        adapter.redis = redis

        await adapter._clear_new_session_pending("agent-1", "user-1")
        redis.delete.assert_awaited_once_with("new_session_pending:whatsapp:agent-1:user-1")


class TestAccessDeniedReplies:
    @pytest.fixture
    def adapter(self):
        return WhatsAppAdapter(
            core_api_url="http://core:8000",
            webhook_secret="secret",
            sidecar_api_token="token",
        )

    @pytest.mark.asyncio
    async def test_closed_mode_reply(self, adapter):
        from httpx import HTTPStatusError, Response
        resp = Response(403, json={"detail": "closed_mode"})
        exc = HTTPStatusError("Forbidden", request=MagicMock(), response=resp)
        with patch.object(adapter, "send_message", new_callable=AsyncMock) as mock_send:
            with patch.object(adapter, "_forward_to_core", side_effect=exc):
                await adapter._handle_inbound_message("agent-1", {
                    "key": {"remoteJid": "12345@s.whatsapp.net", "id": "msg-1"},
                    "message": {"conversation": "Hello"},
                })
            mock_send.assert_awaited_once()
            assert "only accepts messages from its owner" in mock_send.call_args[0][1]

    @pytest.mark.asyncio
    async def test_rate_limited_reply(self, adapter):
        from httpx import HTTPStatusError, Response
        resp = Response(429, json={"detail": "rate_limited"})
        exc = HTTPStatusError("Too Many Requests", request=MagicMock(), response=resp)
        with patch.object(adapter, "send_message", new_callable=AsyncMock) as mock_send:
            with patch.object(adapter, "_forward_to_core", side_effect=exc):
                await adapter._handle_inbound_message("agent-1", {
                    "key": {"remoteJid": "12345@s.whatsapp.net", "id": "msg-1"},
                    "message": {"conversation": "Hello"},
                })
            mock_send.assert_awaited_once()
            assert "too many messages" in mock_send.call_args[0][1]

    @pytest.mark.asyncio
    async def test_outside_schedule_reply_with_custom_text(self, adapter):
        from httpx import HTTPStatusError, Response
        resp = Response(403, json={"detail": {"reason": "outside_schedule", "off_hours_reply": "Closed until 9am."}})
        exc = HTTPStatusError("Forbidden", request=MagicMock(), response=resp)
        with patch.object(adapter, "send_message", new_callable=AsyncMock) as mock_send:
            with patch.object(adapter, "_forward_to_core", side_effect=exc):
                await adapter._handle_inbound_message("agent-1", {
                    "key": {"remoteJid": "12345@s.whatsapp.net", "id": "msg-1"},
                    "message": {"conversation": "Hello"},
                })
            mock_send.assert_awaited_once()
            assert mock_send.call_args[0][1] == "Closed until 9am."

    @pytest.mark.asyncio
    async def test_not_in_whitelist_reply(self, adapter):
        from httpx import HTTPStatusError, Response
        resp = Response(403, json={"detail": "not_in_whitelist"})
        exc = HTTPStatusError("Forbidden", request=MagicMock(), response=resp)
        with patch.object(adapter, "send_message", new_callable=AsyncMock) as mock_send:
            with patch.object(adapter, "_forward_to_core", side_effect=exc):
                await adapter._handle_inbound_message("agent-1", {
                    "key": {"remoteJid": "12345@s.whatsapp.net", "id": "msg-1"},
                    "message": {"conversation": "Hello"},
                })
            mock_send.assert_awaited_once()
            assert "not on the access list" in mock_send.call_args[0][1]
