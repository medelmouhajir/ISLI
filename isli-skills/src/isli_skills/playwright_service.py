import asyncio
from typing import Any
from playwright.async_api import async_playwright
import structlog

logger = structlog.get_logger()

async def browse_url(url: str, wait_for_selector: str | None = None, screenshot: bool = False) -> dict[str, Any]:
    """Navigates to a URL, extracts page content, and optionally takes a screenshot."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        try:
            logger.info("playwright.navigate", url=url)
            await page.goto(url, wait_until="networkidle", timeout=30000)
            
            if wait_for_selector:
                await page.wait_for_selector(wait_for_selector, timeout=10000)
            
            title = await page.title()
            content = await page.content()
            
            result: dict[str, Any] = {
                "title": title,
                "content": content,
                "url": page.url
            }
            
            if screenshot:
                import base64
                screenshot_bytes = await page.screenshot(type="png", full_page=False)
                result["screenshot_b64"] = base64.b64encode(screenshot_bytes).decode("utf-8")
                
            return result
            
        except Exception as exc:
            logger.error("playwright.error", url=url, error=str(exc))
            return {"error": str(exc), "url": url}
        finally:
            await browser.close()
