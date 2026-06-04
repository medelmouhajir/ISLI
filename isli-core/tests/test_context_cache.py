"""Unit tests for ContextCache."""

import pytest

from isli_core.memory.context_cache import ContextCache, _full_key, _session_map_key, _turn_hash


class TestTurnHash:
    def test_deterministic(self):
        h1 = _turn_hash("sess-1", "hello world", ["m1", "m2"])
        h2 = _turn_hash("sess-1", "hello world", ["m1", "m2"])
        assert h1 == h2

    def test_different_inputs(self):
        h1 = _turn_hash("sess-1", "hello", ["m1"])
        h2 = _turn_hash("sess-1", "hello", ["m2"])
        assert h1 != h2


class TestCacheKeyHelpers:
    def test_full_key_format(self):
        assert _full_key("agent-1", "abc123") == "ctx:full:agent-1:abc123"

    def test_session_map_key_format(self):
        assert _session_map_key("sess-1") == "ctx:session_map:sess-1"


@pytest.mark.asyncio
class TestContextCache:
    async def test_cache_hit_returns_exact_string(self, mocker):
        redis_mock = mocker.AsyncMock()
        redis_mock.get.return_value = b"assembled context"
        mocker.patch(
            "isli_core.memory.context_cache.get_redis",
            return_value=redis_mock,
        )

        result = await ContextCache.get(
            agent_id="agent-1",
            session_id="sess-1",
            task_description="hello",
            last_message_ids=["m1"],
        )
        assert result == "assembled context"
        redis_mock.get.assert_awaited_once()

    async def test_cache_miss_returns_none(self, mocker):
        redis_mock = mocker.AsyncMock()
        redis_mock.get.return_value = None
        mocker.patch(
            "isli_core.memory.context_cache.get_redis",
            return_value=redis_mock,
        )

        result = await ContextCache.get(
            agent_id="agent-1",
            session_id="sess-1",
            task_description="hello",
            last_message_ids=["m1"],
        )
        assert result is None

    async def test_cache_set_writes_redis(self, mocker):
        redis_mock = mocker.AsyncMock()
        mocker.patch(
            "isli_core.memory.context_cache.get_redis",
            return_value=redis_mock,
        )

        await ContextCache.set(
            agent_id="agent-1",
            session_id="sess-1",
            task_description="hello",
            last_message_ids=["m1"],
            context_summary="assembled context",
            ttl=30,
        )
        redis_mock.setex.assert_awaited_once()
        redis_mock.setex.call_args[0][0].startswith("ctx:full:agent-1:")

    async def test_invalidate_for_agent_deletes_keys(self, mocker):
        redis_mock = mocker.AsyncMock()
        redis_mock.scan.side_effect = [
            (b"0", [b"ctx:full:agent-1:abc", b"ctx:full:agent-1:def"]),
        ]
        mocker.patch(
            "isli_core.memory.context_cache.get_redis",
            return_value=redis_mock,
        )

        count = await ContextCache.invalidate_for_agent("agent-1")
        assert count == 2
        redis_mock.delete.assert_awaited_once_with(
            b"ctx:full:agent-1:abc", b"ctx:full:agent-1:def"
        )

    async def test_invalidate_for_session_deletes_keys(self, mocker):
        redis_mock = mocker.AsyncMock()
        redis_mock.get.return_value = b"agent-1"
        redis_mock.scan.side_effect = [
            (b"0", [b"ctx:full:agent-1:abc"]),
        ]
        mocker.patch(
            "isli_core.memory.context_cache.get_redis",
            return_value=redis_mock,
        )

        count = await ContextCache.invalidate_for_session("sess-1")
        assert count == 1
        redis_mock.delete.assert_any_call(b"ctx:full:agent-1:abc")
        redis_mock.delete.assert_any_call("ctx:session_map:sess-1")

    async def test_invalidate_for_session_no_agent(self, mocker):
        redis_mock = mocker.AsyncMock()
        redis_mock.get.return_value = None
        mocker.patch(
            "isli_core.memory.context_cache.get_redis",
            return_value=redis_mock,
        )

        count = await ContextCache.invalidate_for_session("sess-1")
        assert count == 0
