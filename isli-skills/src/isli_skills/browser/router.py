"""Browser automation router — Hermes-style /browse/* endpoints."""

from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from isli_skills.auth import require_internal_auth
from isli_skills.browser.accessibility_tree import get_snapshot
from isli_skills.browser.exceptions import BrowserRefError, BrowserSessionError

logger = structlog.get_logger()

router = APIRouter(prefix="/browse")

# Injected by lifespan in main.py
_session_mgr: Any | None = None


def set_session_manager(mgr: Any) -> None:
    """Called during app lifespan startup to wire the session manager."""
    global _session_mgr
    _session_mgr = mgr


class NavigateRequest(BaseModel):
    agent_id: str
    url: str
    wait_for_selector: str | None = None


class SnapshotRequest(BaseModel):
    agent_id: str
    full: bool = False


class ClickRequest(BaseModel):
    agent_id: str
    ref: str


class TypeRequest(BaseModel):
    agent_id: str
    ref: str
    text: str
    clear: bool = True


class PressRequest(BaseModel):
    agent_id: str
    key: str


class ScrollRequest(BaseModel):
    agent_id: str
    direction: str = "down"
    amount: int = 3


class BackRequest(BaseModel):
    agent_id: str


class ConsoleRequest(BaseModel):
    agent_id: str
    since_cursor: int = 0


class VisionRequest(BaseModel):
    agent_id: str
    question: str | None = None


class ImagesRequest(BaseModel):
    agent_id: str


# ── helpers ──────────────────────────────────────────────────────────────


async def _get_session(agent_id: str):
    """Get or create a browser session, with pool-exhaustion handling."""
    if _session_mgr is None:
        raise HTTPException(status_code=503, detail="Browser service not ready")
    try:
        return await _session_mgr.get_or_create(agent_id)
    except BrowserSessionError as exc:
        raise HTTPException(
            status_code=503,
            detail={"error": str(exc), "retry_after": 30},
            headers={"Retry-After": "30"},
        ) from exc


def _normalize_ref(ref: str) -> str:
    """Strip leading '@' if present — agents may pass '@e3' or 'e3'."""
    return ref.lstrip("@")


# ── endpoints ──────────────────────────────────────────────────────────


@router.post("/navigate")
async def browser_navigate(
    request: NavigateRequest, auth: dict = Depends(require_internal_auth)
):
    """Navigate the agent's browser to a URL."""
    session = await _get_session(request.agent_id)

    # CRITICAL: invalidate refs BEFORE navigation to prevent stale clicks
    session.clear_refs()
    session.reset_console()

    async with session.lock:
        try:
            logger.info("browser.navigate", agent_id=request.agent_id, url=request.url)
            response = await session.page.goto(
                request.url, wait_until="networkidle", timeout=30000
            )
            status_code = response.status if response else 0

            if request.wait_for_selector:
                await session.page.wait_for_selector(
                    request.wait_for_selector, timeout=10000
                )

            title = await session.page.title()
            await _session_mgr.touch(request.agent_id)

            return {
                "success": True,
                "url": session.page.url,
                "title": title,
                "status_code": status_code,
            }
        except Exception as exc:
            logger.error("browser.navigate_error", agent_id=request.agent_id, error=str(exc))
            raise HTTPException(status_code=500, detail=f"Navigation failed: {exc}") from exc


@router.post("/snapshot")
async def browser_snapshot(
    request: SnapshotRequest, auth: dict = Depends(require_internal_auth)
):
    """Return an accessibility-tree snapshot of the current page."""
    session = await _get_session(request.agent_id)

    async with session.lock:
        try:
            from isli_skills.config import get_settings

            settings = get_settings()
            max_chars = getattr(settings, "browser_max_snapshot_chars", 8000)

            snapshot = await get_snapshot(
                session.page,
                ref_map=session.ref_map,
                full=request.full,
                max_chars=max_chars,
            )
            await _session_mgr.touch(request.agent_id)

            return {
                "success": True,
                "url": session.page.url,
                "snapshot": snapshot,
                "full": request.full,
            }
        except Exception as exc:
            logger.error("browser.snapshot_error", agent_id=request.agent_id, error=str(exc))
            raise HTTPException(status_code=500, detail=f"Snapshot failed: {exc}") from exc


@router.post("/click")
async def browser_click(
    request: ClickRequest, auth: dict = Depends(require_internal_auth)
):
    """Click an element by its @ref ID from the last snapshot."""
    session = await _get_session(request.agent_id)
    ref = _normalize_ref(request.ref)

    node = session.ref_map.get(ref)
    if not node:
        raise HTTPException(
            status_code=400,
            detail=f"Ref '{request.ref}' not found — the page may have changed. Re-run snapshot.",
        )

    async with session.lock:
        try:
            # The ref_map stores the raw accessibility node dict from Playwright.
            # We need to query the element by its properties to get a handle.
            # For robustness, use the node's role+name or fallback to a CSS query.
            # Playwright's accessibility node doesn't expose element handles directly,
            # so we query by accessible selectors where possible.
            name = node.get("name", "")
            role = node.get("role", "")
            tag = node.get("tag", "").lower()

            # Try accessible selector first (best match)
            if role and name:
                locator = session.page.get_by_role(role, name=name)
            elif name:
                locator = session.page.get_by_text(name, exact=False)
            elif tag:
                locator = session.page.locator(tag).first
            else:
                raise BrowserRefError(f"Cannot resolve element for ref '{request.ref}'")

            await locator.click(timeout=10000)
            await _session_mgr.touch(request.agent_id)

            return {"success": True, "url": session.page.url}
        except BrowserRefError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            logger.error("browser.click_error", agent_id=request.agent_id, ref=ref, error=str(exc))
            raise HTTPException(status_code=500, detail=f"Click failed: {exc}") from exc


@router.post("/type")
async def browser_type(
    request: TypeRequest, auth: dict = Depends(require_internal_auth)
):
    """Type text into an input field by its @ref ID."""
    session = await _get_session(request.agent_id)
    ref = _normalize_ref(request.ref)

    node = session.ref_map.get(ref)
    if not node:
        raise HTTPException(
            status_code=400,
            detail=f"Ref '{request.ref}' not found — the page may have changed. Re-run snapshot.",
        )

    async with session.lock:
        try:
            name = node.get("name", "")
            role = node.get("role", "")
            tag = node.get("tag", "").lower()

            if role and name:
                locator = session.page.get_by_role(role, name=name)
            elif name:
                locator = session.page.get_by_text(name, exact=False)
            elif tag:
                locator = session.page.locator(tag).first
            else:
                raise BrowserRefError(f"Cannot resolve element for ref '{request.ref}'")

            if request.clear:
                await locator.fill(request.text, timeout=10000)
            else:
                await locator.press_sequentially(request.text, timeout=10000)

            await _session_mgr.touch(request.agent_id)
            return {"success": True, "url": session.page.url}
        except BrowserRefError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            logger.error("browser.type_error", agent_id=request.agent_id, ref=ref, error=str(exc))
            raise HTTPException(status_code=500, detail=f"Type failed: {exc}") from exc


@router.post("/press")
async def browser_press(
    request: PressRequest, auth: dict = Depends(require_internal_auth)
):
    """Press a keyboard key (Enter, Tab, Escape, etc.)."""
    session = await _get_session(request.agent_id)

    async with session.lock:
        try:
            await session.page.keyboard.press(request.key)
            await _session_mgr.touch(request.agent_id)
            return {"success": True, "url": session.page.url}
        except Exception as exc:
            logger.error(
                "browser.press_error",
                agent_id=request.agent_id,
                key=request.key,
                error=str(exc),
            )
            raise HTTPException(status_code=500, detail=f"Key press failed: {exc}") from exc


@router.post("/scroll")
async def browser_scroll(
    request: ScrollRequest, auth: dict = Depends(require_internal_auth)
):
    """Scroll the page up or down."""
    session = await _get_session(request.agent_id)

    async with session.lock:
        try:
            scroll_by = request.amount * 300  # pixels per "unit"
            if request.direction.lower() == "up":
                scroll_by = -scroll_by
            elif request.direction.lower() == "down":
                pass  # positive
            else:
                raise ValueError(f"Invalid scroll direction: {request.direction}")

            await session.page.evaluate(f"window.scrollBy(0, {scroll_by})")
            await _session_mgr.touch(request.agent_id)
            return {"success": True, "url": session.page.url}
        except Exception as exc:
            logger.error("browser.scroll_error", agent_id=request.agent_id, error=str(exc))
            raise HTTPException(status_code=500, detail=f"Scroll failed: {exc}") from exc


@router.post("/back")
async def browser_back(
    request: BackRequest, auth: dict = Depends(require_internal_auth)
):
    """Navigate back in browser history."""
    session = await _get_session(request.agent_id)

    # Invalidate refs before back navigation
    session.clear_refs()

    async with session.lock:
        try:
            await session.page.go_back(wait_until="networkidle", timeout=30000)
            await _session_mgr.touch(request.agent_id)
            return {"success": True, "url": session.page.url}
        except Exception as exc:
            logger.error("browser.back_error", agent_id=request.agent_id, error=str(exc))
            raise HTTPException(status_code=500, detail=f"Back navigation failed: {exc}") from exc


@router.post("/console")
async def browser_console(
    request: ConsoleRequest, auth: dict = Depends(require_internal_auth)
):
    """Return console logs captured since the last call (or since navigate)."""
    session = await _get_session(request.agent_id)

    logs, next_cursor = session.get_console_logs(since_cursor=request.since_cursor)
    await _session_mgr.touch(request.agent_id)

    return {
        "success": True,
        "logs": logs,
        "next_cursor": next_cursor,
    }


@router.post("/vision")
async def browser_vision(
    request: VisionRequest, auth: dict = Depends(require_internal_auth)
):
    """Take a screenshot and optionally describe it via the Keeper."""
    import base64

    session = await _get_session(request.agent_id)

    async with session.lock:
        try:
            screenshot_bytes = await session.page.screenshot(type="png", full_page=False)
            screenshot_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")
            await _session_mgr.touch(request.agent_id)

            return {
                "success": True,
                "url": session.page.url,
                "screenshot_b64": screenshot_b64,
                "question": request.question,
            }
        except Exception as exc:
            logger.error("browser.vision_error", agent_id=request.agent_id, error=str(exc))
            raise HTTPException(status_code=500, detail=f"Vision capture failed: {exc}") from exc


@router.post("/images")
async def browser_images(
    request: ImagesRequest, auth: dict = Depends(require_internal_auth)
):
    """List all image elements on the current page with src and alt text."""
    session = await _get_session(request.agent_id)

    async with session.lock:
        try:
            images = await session.page.eval_on_selector_all(
                "img",
                """elements => elements.map(img => ({
                    src: img.src,
                    alt: img.alt,
                    width: img.naturalWidth,
                    height: img.naturalHeight,
                }))""",
            )
            await _session_mgr.touch(request.agent_id)

            return {
                "success": True,
                "url": session.page.url,
                "images": images,
            }
        except Exception as exc:
            logger.error("browser.images_error", agent_id=request.agent_id, error=str(exc))
            raise HTTPException(status_code=500, detail=f"Image extraction failed: {exc}") from exc
