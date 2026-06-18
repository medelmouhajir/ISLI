"""LiteLLM model client: routing, auth injection, retry, fallback, circuit breaker."""

import asyncio
import random
from typing import TYPE_CHECKING, Any

import structlog
from litellm import acompletion

from ..utils.tokens import count_message_tokens
from .errors import ModelErrorCategory, _classify_model_error
from .providers import OLLAMA_NATIVE_OPT_OUT_KEY, OLLAMA_OPENAI_BASE, _normalize_provider

logger = structlog.get_logger()

if TYPE_CHECKING:
    from .core import AgentRunner


class ModelClient:
    """Wraps LiteLLM completion with routing, auth, retry, fallback, and circuit breaker logic."""

    def __init__(self, runner: "AgentRunner"):
        self.runner = runner

    def resolve_model(self, routed: dict | None = None) -> str:
        """Pick the model string for LiteLLM.

        Priority:
        1. Routed model (if present and valid)
        2. Agent default model

        Ollama Cloud agents default to the OpenAI-compatible endpoint because
        LiteLLM's native 'ollama/...' adapter can loop on tool results and
        return empty final answers. Agents can opt out via
        config.use_native_ollama_endpoint=true.
        """
        config = self.runner.config
        if routed and routed.get("model_id"):
            provider = _normalize_provider(routed.get("provider", config.model_provider or ""))
            model_id = routed["model_id"]
            return f"{self._ollama_openai_provider(provider)}/{model_id}"
        provider = _normalize_provider(config.model_provider or "")
        return f"{self._ollama_openai_provider(provider)}/{config.model_id}"

    def _ollama_openai_provider(self, provider: str) -> str:
        """Map ollama -> openai unless the agent opts into the native endpoint."""
        config = self.runner.config
        if provider == "ollama" and not config.config.get(OLLAMA_NATIVE_OPT_OUT_KEY, False):
            return "openai"
        return provider

    async def acompletion_with_retry(self, completion_kwargs: dict[str, Any], turn_label: str) -> Any:
        """Call acompletion with transient-error retry and ±50% jitter."""
        max_retries = 3
        base_delay = 1.0

        for attempt in range(max_retries):
            try:
                return await acompletion(**completion_kwargs)
            except Exception as exc:
                category, _ = _classify_model_error(exc)
                if category not in (ModelErrorCategory.RATE_LIMIT, ModelErrorCategory.TIMEOUT, ModelErrorCategory.OVERLOADED):
                    raise

                if attempt == max_retries - 1:
                    raise

                delay = min(base_delay * (2 ** attempt), 30.0)
                delay = delay * (0.5 + random.random() * 0.5)

                logger.warning(
                    "runner.model_retry",
                    turn=turn_label,
                    attempt=attempt + 1,
                    max_retries=max_retries,
                    delay=round(delay, 2),
                    category=category.value,
                    error=str(exc),
                )
                await asyncio.sleep(delay)

    def apply_auth_to_kwargs(self, completion_kwargs: dict[str, Any]) -> None:
        """Inject api_key, api_base, and provider-specific env vars into kwargs."""
        import os

        config = self.runner.config
        provider = _normalize_provider(config.model_provider or "")
        use_ollama_openai = (
            provider == "ollama"
            and not config.config.get(OLLAMA_NATIVE_OPT_OUT_KEY, False)
        )

        if config.api_key:
            completion_kwargs["api_key"] = config.api_key
            # LiteLLM and some downstream libraries also read env vars.
            provider_env_map = {
                "ollama": "OLLAMA_API_KEY",
                "openai": "OPENAI_API_KEY",
                "anthropic": "ANTHROPIC_API_KEY",
                "gemini": "GEMINI_API_KEY",
                "google": "GEMINI_API_KEY",
                "nvidia": "NVIDIA_NIM_API_KEY",
                "nvidia_nim": "NVIDIA_NIM_API_KEY",
                "deepseek": "DEEPSEEK_API_KEY",
                "azure": "AZURE_API_KEY",
                "vertex_ai": "VERTEXAI_API_KEY",
                "vertex": "VERTEXAI_API_KEY",
            }
            env_var = provider_env_map.get(provider)
            if env_var:
                os.environ[env_var] = config.api_key
            # When remapping ollama -> openai, ensure OPENAI_API_KEY is also set.
            if use_ollama_openai:
                os.environ["OPENAI_API_KEY"] = config.api_key

        # Ollama Cloud agents default to the OpenAI-compatible /v1 endpoint.
        if use_ollama_openai and not config.api_base:
            completion_kwargs["api_base"] = OLLAMA_OPENAI_BASE
        elif config.api_base:
            completion_kwargs["api_base"] = config.api_base

    async def model_with_fallback(self, completion_kwargs: dict, turn_label: str) -> Any:
        """Execute acompletion with deterministic fallback. Auth errors do NOT fallback."""
        config = self.runner.config
        routed = completion_kwargs.get("_routed_model")
        default = {"provider": config.model_provider, "model_id": config.model_id}

        if not default.get("model_id"):
            raise RuntimeError(
                "Agent default model is missing. "
                "Set model_provider + model_id on the agent record."
            )

        attempts: list[tuple[str, dict]] = []
        if routed and routed.get("model_id"):
            attempts.append(("routed", routed))
        attempts.append(("default", default))

        last_error: Exception | None = None
        for attempt_name, model_cfg in attempts:
            try:
                completion_kwargs["model"] = self.resolve_model(model_cfg)
                return await self.acompletion_with_retry(completion_kwargs, turn_label)
            except Exception as exc:
                last_error = exc
                category, _ = _classify_model_error(exc)
                if category == ModelErrorCategory.AUTH:
                    raise
                logger.warning(
                    "runner.model_fallback",
                    attempt=attempt_name,
                    from_model=completion_kwargs.get("model"),
                    category=category.value,
                    error=str(exc),
                )
        raise last_error or RuntimeError("No model available")

    def truncate_tool_results_to_cap(self, messages: list[dict], max_tokens: int = 1000) -> list[dict]:
        """Proportionally truncate 'tool' role results if the total turn exceeds turn_token_cap."""
        config = self.runner.config
        if not config.turn_token_cap:
            return messages

        current_tokens = count_message_tokens(messages)
        # We reserve 'max_tokens' for the model's output
        total_estimated = current_tokens + max_tokens

        if total_estimated <= config.turn_token_cap:
            return messages

        # How much we need to trim
        overage = total_estimated - config.turn_token_cap

        # Identify tool results that can be truncated
        tool_messages = [m for m in messages if m.get("role") == "tool"]
        if not tool_messages:
            return messages

        total_tool_len = sum(len(str(m.get("content", ""))) for m in tool_messages)
        if total_tool_len == 0:
            return messages

        # Calculate truncation factor. We need to reduce total_tool_len by approx 'overage' tokens.
        # heuristic: 1 token ~= 3.5 chars.
        chars_to_remove = overage * 3.5
        if chars_to_remove >= total_tool_len * 0.9:
            # Don't truncate more than 90% of a tool result to keep some context
            chars_to_remove = total_tool_len * 0.9

        truncation_ratio = 1.0 - (chars_to_remove / total_tool_len)

        new_messages = []
        truncated_count = 0
        original_total_tokens = current_tokens

        for m in messages:
            if m.get("role") == "tool" and m.get("content"):
                content = str(m["content"])
                orig_len = len(content)
                target_len = int(orig_len * truncation_ratio)
                if target_len < orig_len:
                    m = m.copy()
                    m["content"] = content[:target_len] + "... [TRUNCATED DUE TO TURN_TOKEN_CAP]"
                    truncated_count += 1
            new_messages.append(m)

        if truncated_count > 0:
            new_total_tokens = count_message_tokens(new_messages)
            logger.warning(
                "runner.turn_token_cap_enforced",
                agent_id=config.id,
                original_tokens=original_total_tokens,
                truncated_tokens=new_total_tokens,
                cap=config.turn_token_cap,
                tool_results_truncated=truncated_count
            )
            # Emit a structured log for the UI
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(
                    self.runner._emit_stream_event(
                        "system",
                        "turn_token_cap:truncated",
                        {
                            "original_tokens": original_total_tokens,
                            "truncated_tokens": new_total_tokens,
                            "cap": config.turn_token_cap
                        }
                    )
                )
            except RuntimeError:
                # No running loop, skip emitting event (likely in a test or sync context)
                pass

        return new_messages
