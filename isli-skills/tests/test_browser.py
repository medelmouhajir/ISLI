"""Tests for browser automation endpoints."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient


@pytest.fixture
def mock_session_manager():
    """Fixture providing a mocked BrowserSessionManager."""
    mgr = MagicMock()
    mgr.get_or_create = AsyncMock()
    mgr.touch = AsyncMock()
    return mgr


@pytest.fixture
def mock_browser_session():
    """Fixture providing a mocked BrowserSession."""
    session = MagicMock()
    session.lock = MagicMock()
    session.lock.__aenter__ = AsyncMock(return_value=None)
    session.lock.__aexit__ = AsyncMock(return_value=None)
    session.page = MagicMock()
    session.page.url = "https://example.com"
    session.page.title = AsyncMock(return_value="Example Domain")
    session.page.goto = AsyncMock(return_value=MagicMock(status=200))
    session.page.keyboard = MagicMock()
    session.page.keyboard.press = AsyncMock()
    session.page.evaluate = AsyncMock()
    session.page.go_back = AsyncMock()
    session.page.screenshot = AsyncMock(return_value=b"\x89PNG\r\n\x1a\n")
    session.page.eval_on_selector_all = AsyncMock(return_value=[
        {"src": "https://example.com/img.png", "alt": "Example image", "width": 100, "height": 100}
    ])
    session.ref_map = {"e1": {"role": "button", "name": "Submit", "tag": "button"}}
    session.clear_refs = MagicMock()
    session.reset_console = MagicMock()
    session.console_logs = []
    session.console_cursor = 0
    session.get_console_logs = MagicMock(return_value=([], 0))
    session.last_accessed = 0
    return session


class TestBrowserNavigate:
    @pytest.mark.asyncio
    async def test_navigate_success(
        self, client: AsyncClient, mock_session_manager, mock_browser_session
    ):
        mock_session_manager.get_or_create.return_value = mock_browser_session
        with patch("isli_skills.browser.router._session_mgr", mock_session_manager):
            resp = await client.post(
                "/browse/navigate",
                json={"agent_id": "test-agent", "url": "https://example.com"},
                headers={"X-Internal-Auth": "test-token"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["url"] == "https://example.com"
        assert data["title"] == "Example Domain"
        mock_browser_session.clear_refs.assert_called_once()
        mock_browser_session.reset_console.assert_called_once()


class TestBrowserSnapshot:
    @pytest.mark.asyncio
    async def test_snapshot_compact(
        self, client: AsyncClient, mock_session_manager, mock_browser_session
    ):
        mock_session_manager.get_or_create.return_value = mock_browser_session
        with patch("isli_skills.browser.router._session_mgr", mock_session_manager), \
             patch("isli_skills.browser.router.get_snapshot", new_callable=AsyncMock) as mock_snap:
            mock_snap.return_value = '[1] button "Submit" @e1\n[2] link "About" @e2'
            resp = await client.post(
                "/browse/snapshot",
                json={"agent_id": "test-agent", "full": False},
                headers={"X-Internal-Auth": "test-token"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "@e1" in data["snapshot"]


class TestBrowserClick:
    @pytest.mark.asyncio
    async def test_click_success(
        self, client: AsyncClient, mock_session_manager, mock_browser_session
    ):
        mock_session_manager.get_or_create.return_value = mock_browser_session
        mock_browser_session.page.get_by_role = MagicMock(
            return_value=MagicMock(click=AsyncMock())
        )
        with patch("isli_skills.browser.router._session_mgr", mock_session_manager):
            resp = await client.post(
                "/browse/click",
                json={"agent_id": "test-agent", "ref": "@e1"},
                headers={"X-Internal-Auth": "test-token"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    @pytest.mark.asyncio
    async def test_click_unknown_ref(
        self, client: AsyncClient, mock_session_manager, mock_browser_session
    ):
        mock_session_manager.get_or_create.return_value = mock_browser_session
        mock_browser_session.ref_map = {}  # empty
        with patch("isli_skills.browser.router._session_mgr", mock_session_manager):
            resp = await client.post(
                "/browse/click",
                json={"agent_id": "test-agent", "ref": "@e99"},
                headers={"X-Internal-Auth": "test-token"},
            )
        assert resp.status_code == 400
        assert "re-run snapshot" in resp.json()["detail"]


class TestBrowserPoolExhausted:
    @pytest.mark.asyncio
    async def test_max_concurrent_503(self, client: AsyncClient):
        from isli_skills.browser.exceptions import BrowserSessionError
        mgr = MagicMock()
        mgr.get_or_create = AsyncMock(side_effect=BrowserSessionError("pool exhausted"))
        with patch("isli_skills.browser.router._session_mgr", mgr):
            resp = await client.post(
                "/browse/navigate",
                json={"agent_id": "test-agent", "url": "https://example.com"},
                headers={"X-Internal-Auth": "test-token"},
            )
        assert resp.status_code == 503
        assert resp.headers.get("retry-after") == "30"
