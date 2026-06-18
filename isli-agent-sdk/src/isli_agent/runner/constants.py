"""Module-level constants for the agent runner."""

# Runtime params injected by the runner, not provided by the LLM
RUNTIME_INJECTED_PARAMS = {"agent_id", "core_client"}
MAX_LLM_TURNS = 50
MAX_CONSECUTIVE_TOOL_FAILURES = 3
TOOL_RESULT_SPILL_THRESHOLD = 2000

# Circuit breaker: seconds before allowing a half-open probe
CIRCUIT_HALF_OPEN_AFTER = 300  # 5 minutes
