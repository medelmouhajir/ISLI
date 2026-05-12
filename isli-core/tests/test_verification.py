"""Tests for grounding verification and retry policy."""

import asyncio
import pytest

from isli_core.verification.grounding import GroundingVerifier, VerificationResult
from isli_core.verification.retry_policy import RetryPolicyMapper
from isli_core.verification.schema_registry import SKILL_OUTPUT_SCHEMAS


class TestGroundingVerifier:
    def test_valid_response_passes(self):
        result = GroundingVerifier.verify("web-fetch", {"status_code": 200, "url": "http://example.com"})
        assert result.is_valid is True

    def test_contradiction_success_and_error(self):
        result = GroundingVerifier.verify("web-fetch", {"success": True, "error": "Internal Server Error"})
        assert result.is_valid is False
        assert "Contradiction" in result.reason

    def test_contradiction_status_ok_and_error(self):
        result = GroundingVerifier.verify("web-fetch", {"status": "ok", "error": "something broke"})
        assert result.is_valid is False
        assert "Contradiction" in result.reason

    def test_http_error_marker(self):
        result = GroundingVerifier.verify("web-fetch", {"status_code": 500, "error": "Internal Server Error"})
        assert result.is_valid is False
        assert "HTTP error marker" in result.reason

    def test_missing_required_field(self):
        result = GroundingVerifier.verify("web-fetch", {"url": "http://example.com"})
        assert result.is_valid is False
        assert "Missing required fields" in result.reason

    def test_wrong_field_type(self):
        result = GroundingVerifier.verify("web-fetch", {"status_code": "200", "url": "http://example.com"})
        assert result.is_valid is False
        assert "expected int" in result.reason

    def test_unknown_skill_no_schema(self):
        result = GroundingVerifier.verify("unknown-skill", {"data": "anything"})
        assert result.is_valid is True

    def test_success_false_with_error_is_valid(self):
        result = GroundingVerifier.verify("summarize", {"success": False, "error": "Rate limited", "summary": ""})
        assert result.is_valid is True

    @pytest.mark.asyncio
    async def test_verify_with_retry_succeeds_first_try(self):
        call_count = 0

        async def call_fn():
            nonlocal call_count
            call_count += 1
            return {"status_code": 200, "url": "http://example.com"}

        raw, result = await GroundingVerifier.verify_with_retry("web-fetch", call_fn)
        assert result.is_valid is True
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_verify_with_retry_succeeds_on_second_attempt(self):
        call_count = 0

        async def call_fn():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"success": True, "error": "fail"}
            return {"status_code": 200, "url": "http://example.com"}

        raw, result = await GroundingVerifier.verify_with_retry("web-fetch", call_fn)
        assert result.is_valid is True
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_verify_with_retry_exhausted(self):
        call_count = 0

        async def call_fn():
            nonlocal call_count
            call_count += 1
            return {"success": True, "error": "fail"}

        raw, result = await GroundingVerifier.verify_with_retry("web-fetch", call_fn, max_retries=2)
        assert result.is_valid is False
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_verify_with_retry_call_exception(self):
        call_count = 0

        async def call_fn():
            nonlocal call_count
            call_count += 1
            raise RuntimeError("boom")

        raw, result = await GroundingVerifier.verify_with_retry("web-fetch", call_fn, max_retries=1)
        assert result.is_valid is False
        assert "Call failed" in result.reason
        assert call_count == 2


class TestRetryPolicyMapper:
    def test_default_policy(self):
        p = RetryPolicyMapper.get("unknown")
        assert p["max_retries"] == 3

    def test_verification_fail_policy(self):
        p = RetryPolicyMapper.get("verification_fail")
        assert p["max_retries"] == 2

    def test_delay_computation(self):
        delay = RetryPolicyMapper.compute_delay(attempt=1, base=1.0, cap=10.0, jitter=False)
        assert delay == 2.0

    def test_delay_cap(self):
        delay = RetryPolicyMapper.compute_delay(attempt=10, base=1.0, cap=5.0, jitter=False)
        assert delay == 5.0

    def test_delay_jitter(self):
        delay = RetryPolicyMapper.compute_delay(attempt=0, base=1.0, cap=10.0, jitter=True)
        assert 0.5 <= delay <= 1.0


class TestSchemaRegistry:
    def test_web_fetch_schema(self):
        assert "web-fetch" in SKILL_OUTPUT_SCHEMAS
        assert "status_code" in SKILL_OUTPUT_SCHEMAS["web-fetch"]["required"]

    def test_summarize_schema(self):
        assert "summarize" in SKILL_OUTPUT_SCHEMAS
        assert "summary" in SKILL_OUTPUT_SCHEMAS["summarize"]["required"]
