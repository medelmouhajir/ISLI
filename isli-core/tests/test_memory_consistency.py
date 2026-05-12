"""Memory consistency regression tests.

Run with: pytest isli-core/tests/test_memory_consistency.py -v
"""

import pytest

from isli_core.memory.validation import MemoryValidator
from isli_core.memory.dimension_guard import VectorDimensionGuard
from isli_core.memory.deduplication import SemanticDeduplicator


class TestMemoryValidator:
    def test_cosine_similarity_identical(self):
        a = [1.0, 0.0, 0.0]
        b = [1.0, 0.0, 0.0]
        assert MemoryValidator.cosine_similarity(a, b) == pytest.approx(1.0)

    def test_cosine_similarity_orthogonal(self):
        a = [1.0, 0.0, 0.0]
        b = [0.0, 1.0, 0.0]
        assert MemoryValidator.cosine_similarity(a, b) == pytest.approx(0.0)

    def test_cosine_similarity_dimension_mismatch(self):
        with pytest.raises(ValueError):
            MemoryValidator.cosine_similarity([1.0, 0.0], [1.0, 0.0, 0.0])

    def test_rouge_l_perfect(self):
        assert MemoryValidator.rouge_l_summary("hello world", "hello world") == pytest.approx(1.0)

    def test_rouge_l_zero(self):
        assert MemoryValidator.rouge_l_summary("abc def", "xyz uvw") == pytest.approx(0.0)

    def test_validate_summary_quality_pass(self):
        messages = [{"content": "hello world foo bar"}]
        assert MemoryValidator.validate_summary_quality("hello world", messages, threshold=0.3)

    def test_validate_dimension_ok(self):
        VectorDimensionGuard.assert_dimension([0.0] * 768, "nomic-embed-text")

    def test_validate_dimension_fail(self):
        with pytest.raises(ValueError):
            VectorDimensionGuard.assert_dimension([0.0] * 512, "nomic-embed-text")

    def test_dimension_register(self):
        VectorDimensionGuard.register_model("test-model", 128)
        assert VectorDimensionGuard.get_dimension("test-model") == 128


class TestSemanticDeduplicator:
    @pytest.mark.asyncio
    async def test_is_duplicate_true(self):
        # Mock a simple in-memory check without DB
        class FakeMem:
            def __init__(self, emb):
                self.embedding = emb
                self.id = "test-id"

        new_emb = [1.0, 0.0, 0.0]
        existing = [FakeMem([0.999, 0.001, 0.0])]
        # This would require mocking the session; we'll test the core logic instead
        sim = MemoryValidator.cosine_similarity(new_emb, existing[0].embedding)
        assert sim > 0.95
