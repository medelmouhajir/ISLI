"""Per-agent PII mesh: anonymize before LLM, rehydrate locally after."""

from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from .core import AgentRunner

logger = structlog.get_logger()


class PIIManager:
    """Manages PII anonymization/rehydration for a single agent runner."""

    def __init__(self, runner: "AgentRunner"):
        self.runner = runner
        if not hasattr(runner, "_session_token_maps"):
            runner._session_token_maps = {}

    @property
    def mesh_enabled(self) -> bool:
        return (self.runner.config.config or {}).get("pii_mesh_enabled", False)

    @property
    def use_slm(self) -> bool:
        return (self.runner.config.config or {}).get("pii_use_slm", True)

    async def prepare_llm_payload(
        self, system_prompt: str, messages: list[dict], session_id: str
    ) -> tuple[str, list[dict]]:
        """Anonymize PII before sending to the Cloud LLM."""
        if not self.mesh_enabled:
            return system_prompt, messages

        client = self.runner._pii_client
        combined = system_prompt + "\n".join(m.get("content", "") for m in messages)
        if not client.regex_hits(combined) and not client.session_has_tokens(session_id):
            return system_prompt, messages

        try:
            prep = await client.session_prep(
                session_id=session_id,
                agent_id=self.runner.config.id,
                messages=messages,
                context_summary=system_prompt,
                mode="pii_only",
                use_slm=self.use_slm,
            )
            client.cache_token_map(session_id, prep.get("token_map", {}))
            return prep.get("scrubbed_context_summary", system_prompt), prep.get("scrubbed_messages", messages)
        except Exception as exc:
            logger.error("runner.pii_prep_failed", session_id=session_id, error=str(exc))
            return system_prompt, messages

    def post_process_response(self, text: str, session_id: str) -> str:
        """Re-hydrate tokens locally after the Cloud LLM responds."""
        if not self.mesh_enabled:
            return text
        return self.runner._pii_client.rehydrate_local(text, session_id)
