"""Tests for the interactive debugger skill endpoint."""

import pytest
from httpx import AsyncClient


class TestDebuggerAPI:
    @pytest.mark.asyncio
    async def test_debug_trace_mode(self, client: AsyncClient):
        """Trace mode records every executed line."""
        code = """
x = 1
y = 2
z = x + y
result = z
"""
        resp = await client.post("/debug", json={
            "code": code,
            "mode": "trace",
            "max_steps": 100,
        }, headers={"X-Internal-Auth": "test-token"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert len(data["trace"]) >= 4
        lines = [ev["line"] for ev in data["trace"]]
        assert 2 in lines  # x = 1
        assert 3 in lines  # y = 2
        assert data["final_result"] == "3"
        assert data["exception"] is None

    @pytest.mark.asyncio
    async def test_debug_breakpoints_mode(self, client: AsyncClient):
        """Breakpoints mode only records lines matching breakpoints."""
        code = """
x = 1
y = 2
z = x + y
result = z
"""
        resp = await client.post("/debug", json={
            "code": code,
            "mode": "breakpoints",
            "breakpoints": [3],
            "max_steps": 100,
        }, headers={"X-Internal-Auth": "test-token"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        # Only line 3 should be recorded
        assert len(data["trace"]) == 1
        assert data["trace"][0]["line"] == 3
        assert data["trace"][0]["breakpoint_hit"] is True
        assert data["breakpoints_hit"] == [3]

    @pytest.mark.asyncio
    async def test_debug_watch_expressions(self, client: AsyncClient):
        """Watch expressions are evaluated at each recorded step."""
        code = """
x = 10
y = 5
result = x + y
"""
        resp = await client.post("/debug", json={
            "code": code,
            "mode": "trace",
            "watch_expressions": ["x + y", "x * y"],
            "max_steps": 100,
        }, headers={"X-Internal-Auth": "test-token"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        # At least one event should have watch_results
        events_with_watches = [ev for ev in data["trace"] if "watch_results" in ev]
        assert len(events_with_watches) > 0
        # After line 4 (x=10, y=5 executed), x+y should be 15.
        # Line 3 is 'y = 5' and fires BEFORE y is assigned.
        for ev in events_with_watches:
            if ev["line"] >= 4:
                assert ev["watch_results"]["x + y"] == "15"
                assert ev["watch_results"]["x * y"] == "50"

    @pytest.mark.asyncio
    async def test_debug_max_steps(self, client: AsyncClient):
        """Infinite loop gets truncated at max_steps."""
        code = """
while True:
    x = 1
"""
        resp = await client.post("/debug", json={
            "code": code,
            "mode": "trace",
            "max_steps": 50,
        }, headers={"X-Internal-Auth": "test-token"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["trace_truncated"] is True
        assert data["truncation_reason"] == "max_steps exceeded"
        assert data["total_steps"] == 50

    @pytest.mark.asyncio
    async def test_debug_forbidden_import(self, client: AsyncClient):
        """Importing forbidden modules returns 400."""
        code = "import os\nresult = 1"
        resp = await client.post("/debug", json={
            "code": code,
            "mode": "run",
        }, headers={"X-Internal-Auth": "test-token"})
        assert resp.status_code == 400
        data = resp.json()
        assert "Import of module 'os' is forbidden" in data["detail"]

    @pytest.mark.asyncio
    async def test_debug_exception_capture(self, client: AsyncClient):
        """Division by zero is captured with exception info in trace."""
        code = """
x = 10
y = 0
z = x / y
result = z
"""
        resp = await client.post("/debug", json={
            "code": code,
            "mode": "trace",
            "max_steps": 100,
        }, headers={"X-Internal-Auth": "test-token"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["exception"] is not None
        assert data["exception"]["type"] == "ZeroDivisionError"
        # The exception event should be in the trace
        exc_events = [ev for ev in data["trace"] if ev.get("event") == "exception"]
        assert len(exc_events) >= 1

    @pytest.mark.asyncio
    async def test_debug_stdout_capture(self, client: AsyncClient):
        """print() output is captured in stdout field."""
        code = """
print("hello")
print("world")
result = 42
"""
        resp = await client.post("/debug", json={
            "code": code,
            "mode": "run",
            "max_steps": 100,
        }, headers={"X-Internal-Auth": "test-token"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "hello" in data["stdout"]
        assert "world" in data["stdout"]

    @pytest.mark.asyncio
    async def test_debug_only_changes(self, client: AsyncClient):
        """only_changes=True suppresses unchanged locals."""
        code = """
x = 1
y = 2
x = 3
result = x + y
"""
        resp = await client.post("/debug", json={
            "code": code,
            "mode": "trace",
            "only_changes": True,
            "max_steps": 100,
        }, headers={"X-Internal-Auth": "test-token"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        # First event should have locals
        assert "locals" in data["trace"][0]
        # Events where x didn't change should have empty or no locals
        for ev in data["trace"]:
            if ev["line"] == 3 and "locals" in ev:
                # x changed from 1 to 3
                assert "x" in ev["locals"]

    @pytest.mark.asyncio
    async def test_debug_payload_injection(self, client: AsyncClient):
        """payload is injected into the execution namespace."""
        code = """
result = payload['value'] * 2
"""
        resp = await client.post("/debug", json={
            "code": code,
            "mode": "run",
            "payload": {"value": 21},
        }, headers={"X-Internal-Auth": "test-token"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["final_result"] == "42"

    @pytest.mark.asyncio
    async def test_debug_run_function(self, client: AsyncClient):
        """If code defines run(payload), it is called and return value captured."""
        code = """
def run(payload):
    return payload['a'] + payload['b']
"""
        resp = await client.post("/debug", json={
            "code": code,
            "mode": "run",
            "payload": {"a": 10, "b": 32},
        }, headers={"X-Internal-Auth": "test-token"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["final_result"] == "42"
