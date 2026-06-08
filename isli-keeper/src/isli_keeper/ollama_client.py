# NOTE: Intentionally no circuit breaker here.
# Keeper's charter is "honest 503" — local Ollama failures should surface immediately so
# Core and callers can react. A circuit breaker would mask outages for 30+ seconds and
# create false confidence. If that ever changes, use isli_core.circuit_breaker.
from contextlib import asynccontextmanager
from typing import Any

import httpx
import structlog

from isli_keeper.config import get_settings

logger = structlog.get_logger()


def _auth_headers() -> dict[str, str]:
    settings = get_settings()
    headers: dict[str, str] = {"X-Keeper-Identity": settings.keeper_identity}
    if settings.ollama_api_key:
        headers["Authorization"] = f"Bearer {settings.ollama_api_key}"
    return headers


class OllamaClient:
    """Secure Ollama client with API key / mTLS support."""

    def __init__(self, base_url: str | None = None):
        settings = get_settings()
        self.base_url = base_url or settings.ollama_host or "http://localhost:11434"
        self.headers = _auth_headers()
        # TODO: mTLS client certs can be passed via httpx.Client(cert=...)
        self._client: httpx.AsyncClient | None = None

    @asynccontextmanager
    async def session(self):
        self._client = httpx.AsyncClient(base_url=self.base_url, headers=self.headers, timeout=300.0)
        try:
            yield self
        finally:
            await self._client.aclose()
            self._client = None

    async def generate(self, model: str, prompt: str, options: dict | None = None, timeout: float | None = None, format: str | None = None, keep_alive: int | str | None = None) -> dict:
        if self._client is None:
            raise RuntimeError("OllamaClient session not started")

        # Inject CPU-optimized defaults for context and batch sizes
        default_options = {"num_ctx": 4096, "num_batch": 512}
        merged_options = {**default_options, **(options or {})}

        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": merged_options,
        }
        if format:
            payload["format"] = format
        if keep_alive is not None:
            payload["keep_alive"] = keep_alive
        # Use provided timeout or fall back to client's default (300s)
        resp = await self._client.post("/api/generate", json=payload, timeout=timeout)
        resp.raise_for_status()
        return resp.json()

    async def embed(self, model: str, input_text: str, timeout: float | None = None) -> list[float]:
        if self._client is None:
            raise RuntimeError("OllamaClient session not started")
        payload = {"model": model, "input": input_text}
        resp = await self._client.post("/api/embed", json=payload, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        return data["embeddings"][0]

    async def list_models(self) -> list[str]:
        if self._client is None:
            raise RuntimeError("OllamaClient session not started")
        resp = await self._client.get("/api/tags")
        resp.raise_for_status()
        data = resp.json()
        return [m["name"] for m in data.get("models", [])]

    async def ps(self) -> dict[str, Any]:
        if self._client is None:
            raise RuntimeError("OllamaClient session not started")
        resp = await self._client.get("/api/ps")
        resp.raise_for_status()
        return resp.json()

    async def show_model(self, model: str) -> dict[str, Any]:
        if self._client is None:
            raise RuntimeError("OllamaClient session not started")
        resp = await self._client.post("/api/show", json={"name": model})
        resp.raise_for_status()
        return resp.json()

    async def pull_model(self, model: str, timeout: float | None = None) -> dict[str, Any]:
        if self._client is None:
            raise RuntimeError("OllamaClient session not started")
        payload = {"name": model, "stream": False}
        resp = await self._client.post("/api/pull", json=payload, timeout=timeout)
        resp.raise_for_status()
        return resp.json()

    async def delete_model(self, model: str) -> dict[str, Any]:
        if self._client is None:
            raise RuntimeError("OllamaClient session not started")
        resp = await self._client.request("DELETE", "/api/delete", json={"name": model})
        resp.raise_for_status()
        text = resp.text.strip()
        return resp.json() if text else {"status": "ok"}

    async def model_exists(self, model: str) -> bool:
        if self._client is None:
            raise RuntimeError("OllamaClient session not started")
        resp = await self._client.get("/api/tags")
        resp.raise_for_status()
        data = resp.json()
        return any(m.get("name") == model for m in data.get("models", []))
