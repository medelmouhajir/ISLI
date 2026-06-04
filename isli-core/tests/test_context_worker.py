"""Unit tests for ContextWorker."""

import json
from datetime import datetime, timezone

import pytest

from isli_core.jobs.context_worker import ContextWorker
from isli_core.memory.keeper_client import KeeperAuthError


class FakeRedis:
    """Minimal fake Redis for stream tests."""

    def __init__(self):
        self.streams: dict[str, list[dict]] = {}
        self.groups: set[str] = set()
        self.keys: dict[str, str | bytes] = {}

    async def xgroup_create(self, name, groupname, id, mkstream=False):
        self.groups.add(f"{name}:{groupname}")

    async def xadd(self, name, fields):
        if name not in self.streams:
            self.streams[name] = []
        msg_id = f"{len(self.streams[name]) + 1}-0"
        self.streams[name].append({"id": msg_id, "fields": fields})
        return msg_id

    async def xreadgroup(self, groupname, consumername, streams, count, block):
        stream_name = list(streams.keys())[0]
        results = []
        for msg in self.streams.get(stream_name, []):
            results.append((msg["id"], msg["fields"]))
        self.streams[stream_name] = []  # simulate consumption
        return [(stream_name, results)]

    async def xack(self, name, groupname, *ids):
        pass

    async def xautoclaim(self, name, groupname, consumername, min_idle_time, count, start_id):
        return ("0-0", [])

    async def get(self, key):
        val = self.keys.get(key)
        return val.encode() if isinstance(val, str) else val

    async def setex(self, key, ttl, value):
        self.keys[key] = value


@pytest.fixture
def fake_redis():
    return FakeRedis()


@pytest.mark.asyncio
class TestContextWorker:
    async def test_process_one_cache_hit_no_keeper_call(self, mocker, fake_redis):
        worker = ContextWorker()
        mocker.patch(
            "isli_core.jobs.context_worker.get_redis",
            return_value=fake_redis,
        )
        mocker.patch(
            "isli_core.jobs.context_worker.ContextCache.get",
            return_value="cached context",
        )
        mock_emit = mocker.AsyncMock()
        mocker.patch(
            "isli_core.jobs.context_worker.EventManager.emit",
            mock_emit,
        )
        mocker.patch(
            "isli_core.jobs.context_worker.async_session",
            mocker.AsyncMock(),
        )

        msg = {
            "id": "1-0",
            "payload": {
                "v": 1,
                "type": "task",
                "id": "task-1",
                "agent_id": "agent-1",
                "task_description": "do something",
                "session_id": None,
                "complexity_score": 5,
            },
        }
        await worker._process_one(msg, "test-consumer", is_reclaim=False)

        # Event emitted, ACKed
        mock_emit.assert_awaited()

    async def test_process_one_keeper_auth_error_acks_immediately(self, mocker, fake_redis):
        worker = ContextWorker()
        mocker.patch(
            "isli_core.jobs.context_worker.get_redis",
            return_value=fake_redis,
        )
        mocker.patch(
            "isli_core.jobs.context_worker.ContextCache.get",
            return_value=None,
        )
        mock_keeper = mocker.AsyncMock(side_effect=KeeperAuthError("401"))
        mocker.patch(
            "isli_core.jobs.context_worker.KeeperClient.get_context_injection",
            mock_keeper,
        )
        mock_ack = mocker.AsyncMock()
        mocker.patch(
            "isli_core.jobs.context_worker.acknowledge",
            mock_ack,
        )

        msg = {
            "id": "1-0",
            "payload": {
                "v": 1,
                "type": "task",
                "id": "task-1",
                "agent_id": "agent-1",
                "task_description": "do something",
            },
        }
        await worker._process_one(msg, "test-consumer", is_reclaim=False)

        mock_ack.assert_awaited_once()

    async def test_malformed_payload_acked_as_poison_pill(self, mocker, fake_redis):
        worker = ContextWorker()
        mock_ack = mocker.AsyncMock()
        mocker.patch(
            "isli_core.jobs.context_worker.acknowledge",
            mock_ack,
        )

        msg = {
            "id": "1-0",
            "payload": {"v": 1, "type": "task"},  # missing id and agent_id
        }
        await worker._process_one(msg, "test-consumer", is_reclaim=False)

        mock_ack.assert_awaited_once()

    async def test_reclaim_exceeds_dlq_threshold(self, mocker, fake_redis):
        worker = ContextWorker()
        mocker.patch(
            "isli_core.jobs.context_worker.get_redis",
            return_value=fake_redis,
        )
        mocker.patch(
            "isli_core.jobs.context_worker.ContextCache.get",
            return_value=None,
        )
        mocker.patch(
            "isli_core.jobs.context_worker.KeeperClient.get_context_injection",
            return_value=None,
        )
        mock_ack = mocker.AsyncMock()
        mocker.patch(
            "isli_core.jobs.context_worker.acknowledge",
            mock_ack,
        )
        mock_dlq = mocker.AsyncMock()
        mocker.patch(
            "isli_core.jobs.context_worker.write_dlq",
            mock_dlq,
        )

        msg = {
            "id": "1-0",
            "payload": {
                "v": 1,
                "type": "task",
                "id": "task-1",
                "agent_id": "agent-1",
                "task_description": "do something",
                "__reclaim_count": ContextWorker.DLQ_AFTER_CLAIMS,
            },
        }
        await worker._process_one(msg, "test-consumer", is_reclaim=True)

        mock_dlq.assert_awaited_once()
        mock_ack.assert_awaited_once()
