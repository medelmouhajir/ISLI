import math
import structlog
from typing import Any

logger = structlog.get_logger()


class MemoryValidator:
    """Validation gates for memory quality: cosine similarity, ROUGE-L, dimension checks."""

    DEFAULT_SIMILARITY_THRESHOLD = 0.70
    DEFAULT_QUALITY_THRESHOLD = 0.60

    @staticmethod
    def cosine_similarity(a: list[float], b: list[float]) -> float:
        if len(a) != len(b):
            raise ValueError(f"Dimension mismatch: {len(a)} vs {len(b)}")
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    @staticmethod
    def rouge_l_summary(summary: str, original: str) -> float:
        """Simplified ROUGE-L F1 score (longest common subsequence based)."""
        def _lcs(a: list[str], b: list[str]) -> int:
            m, n = len(a), len(b)
            dp = [[0] * (n + 1) for _ in range(m + 1)]
            for i in range(1, m + 1):
                for j in range(1, n + 1):
                    if a[i - 1] == b[j - 1]:
                        dp[i][j] = dp[i - 1][j - 1] + 1
                    else:
                        dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
            return dp[m][n]

        s_words = summary.lower().split()
        o_words = original.lower().split()
        lcs_len = _lcs(s_words, o_words)
        if len(s_words) == 0 or len(o_words) == 0:
            return 0.0
        precision = lcs_len / len(s_words)
        recall = lcs_len / len(o_words)
        if precision + recall == 0:
            return 0.0
        return 2 * precision * recall / (precision + recall)

    @staticmethod
    def validate_summary_quality(summary: str, original_messages: list[dict[str, Any]], threshold: float | None = None) -> bool:
        original = " ".join(str(m.get("content", "")) for m in original_messages)
        score = MemoryValidator.rouge_l_summary(summary, original)
        threshold = threshold or MemoryValidator.DEFAULT_QUALITY_THRESHOLD
        logger.info("memory.validation.rouge_l", score=score, threshold=threshold)
        return score >= threshold

    @staticmethod
    def validate_embedding_similarity(
        summary_embedding: list[float],
        original_embedding: list[float],
        threshold: float | None = None,
    ) -> bool:
        sim = MemoryValidator.cosine_similarity(summary_embedding, original_embedding)
        threshold = threshold or MemoryValidator.DEFAULT_SIMILARITY_THRESHOLD
        logger.info("memory.validation.cosine_sim", score=sim, threshold=threshold)
        return sim >= threshold

    @staticmethod
    def validate_dimension(embedding: list[float], expected: int) -> None:
        actual = len(embedding)
        if actual != expected:
            raise ValueError(f"Vector dimension mismatch: expected {expected}, got {actual}")
        logger.info("memory.validation.dimension_ok", dim=actual)
