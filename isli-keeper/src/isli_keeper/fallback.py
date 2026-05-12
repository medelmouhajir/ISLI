import os
import structlog

import httpx

from isli_keeper.ollama_client import OllamaClient
from isli_core.circuit_breaker import CircuitBreaker

logger = structlog.get_logger()


class KeeperFallback:
    """When Ollama is unreachable, fall back to a cloud model with reduced scope."""

    def __init__(self):
        self.ollama_cb = CircuitBreaker(
            name="ollama",
            failure_threshold=3,
            recovery_timeout=60.0,
            expected_exception=(httpx.ConnectError, httpx.TimeoutException),
        )
        self.cloud_client = httpx.AsyncClient(timeout=30.0)
        self.cloud_model = os.getenv("KEEPER_FALLBACK_MODEL", "anthropic:claude-sonnet-4-6")
        self.cloud_api_key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("OPENAI_API_KEY")

    async def generate(self, prompt: str, model: str = "qwen3:1.7b") -> dict:
        async def _ollama_call():
            async with OllamaClient().session() as client:
                # Reconstruct a simple generate call
                payload = {"model": model, "prompt": prompt, "stream": False}
                resp = await client.post("/api/generate", json=payload)
                resp.raise_for_status()
                return resp.json()

        try:
            return await self.ollama_cb.call(_ollama_call)
        except Exception:
            logger.warning("keeper.ollama_unavailable", fallback=self.cloud_model)
            return await self._cloud_generate(prompt)

    async def _cloud_generate(self, prompt: str) -> dict:
        provider, model_id = self.cloud_model.split(":", 1)
        if provider == "anthropic" and self.cloud_api_key:
            return await self._anthropic_call(model_id, prompt)
        elif provider == "openai" and self.cloud_api_key:
            return await self._openai_call(model_id, prompt)
        raise RuntimeError(f"No fallback available for {self.cloud_model}")

    async def _anthropic_call(self, model_id: str, prompt: str) -> dict:
        resp = await self.cloud_client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": self.cloud_api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model_id,
                "max_tokens": 1024,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return {"response": data["content"][0]["text"]}

    async def _openai_call(self, model_id: str, prompt: str) -> dict:
        resp = await self.cloud_client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {self.cloud_api_key}",
                "content-type": "application/json",
            },
            json={
                "model": model_id,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return {"response": data["choices"][0]["message"]["content"]}
