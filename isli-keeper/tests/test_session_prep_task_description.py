"""Regression tests for task_description propagation in /session-prep."""

from isli_keeper.pii_models import SessionPrepRequest
from isli_keeper.session_prep import _assemble_combined_text


class TestAssembleCombinedText:
    def test_task_description_prepended(self):
        request = SessionPrepRequest(
            session_id="sess-1",
            agent_id="agent-1",
            context_summary="Previous journal context",
            task_description="Write exactly TASK_RECEIVED_OK.",
            messages=[{"role": "user", "content": "Hello"}],
        )
        combined = _assemble_combined_text(request)
        assert combined.startswith("Task:\nWrite exactly TASK_RECEIVED_OK.")
        assert "Previous context:\nPrevious journal context" in combined
        assert "user: Hello" in combined

    def test_no_task_description(self):
        request = SessionPrepRequest(
            session_id="sess-2",
            agent_id="agent-1",
            context_summary="Previous journal context",
            messages=[{"role": "user", "content": "Hello"}],
        )
        combined = _assemble_combined_text(request)
        assert not combined.startswith("Task:")
        assert "Previous context:\nPrevious journal context" in combined

    def test_only_task_description(self):
        request = SessionPrepRequest(
            session_id="sess-3",
            agent_id="agent-1",
            task_description="Only a task",
            messages=[],
        )
        combined = _assemble_combined_text(request)
        assert combined == "Task:\nOnly a task"
