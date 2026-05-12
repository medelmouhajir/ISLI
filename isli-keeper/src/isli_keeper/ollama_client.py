import os
import structlog
from contextlib import asynccontextmanager

import httpx

logger = structlog.get_logger()

OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY")
KEEPER_IDENTITY = os.getenv("KEEPER_IDENTITY", "isli-keeper")


def _auth_headers() -> dict[str, str]:
    headers: dict[str, str] = {"X-Keeper-Identity": KEEPER_IDENTITY}
    if OLLAMA_API_KEY:
        headers["Authorization"] = f"Bearer {OLLAMA_API_KEY}"
    return headers


class OllamaClient:
    """Secure Ollama client with API key / mTLS support."""

    def __init__(self, base_url: str | None = None):
        self.base_url = base_url or os.getenv("OLLAMA_HOST", "http://localhost:11434")
        self.headers = _auth_headers()
        # TODO: mTLS client certs can be passed via httpx.Client(cert=...)
        self._client: httpx.AsyncClient | None = None

    @asynccontextmanager
    async def session(self):
        self._client = httpx.AsyncClient(base_url=self.base_url, headers=self.headers, timeout=60.0)
        try:
            yield self._client
        finally:
            await self._client.aclose()
            self._client = None

    async def generate(self, model: str, prompt: str, options: dict | None = None) -> dict:
        if self._client is None:
            raise RuntimeError("OllamaClient session not started")
        payload = {"model": model, "prompt": prompt, "stream": False}
        if options:
            payload["options"] = options
        resp = await self._client.post("/api/generate", json=payload)
        resp.raise_for_status()
        return resp.json()

    async def embed(self, model: str, input_text: str) -> list[float]:
        if self._client is None:
            raise RuntimeError("OllamaClient session not started")
        payload = {"model": model, "input": input_text}
        resp = await self._client.post("/api/embed", json=payload)
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
