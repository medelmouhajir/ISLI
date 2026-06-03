import pytest
from isli_core.cost.rate_card import CostEstimator, RATE_CARD

class TestGeminiPricing:
    def test_gemini_2_5_pro_pricing(self):
        # Input: $1.25/1M ($0.00125/1K), Output: $10.00/1M ($0.01/1K)
        # 1000 input tokens = $0.00125
        # 1000 output tokens = $0.01
        cost = CostEstimator.estimate_turn("gemini-2.5-pro", 1000, 1000)
        assert round(cost, 5) == 0.01125

    def test_gemini_3_1_pro_pricing(self):
        # Input: $2.00/1M ($0.002/1K), Output: $12.00/1M ($0.012/1K)
        # 1000 input tokens = $0.002
        # 1000 output tokens = $0.012
        cost = CostEstimator.estimate_turn("gemini-3.1-pro", 1000, 1000)
        assert round(cost, 5) == 0.014

    def test_gemini_3_0_flash_pricing(self):
        # Input: $0.50/1M ($0.0005/1K), Output: $3.00/1M ($0.003/1K)
        cost = CostEstimator.estimate_turn("gemini-3.0-flash", 1000, 1000)
        assert round(cost, 5) == 0.0035

    def test_gemini_rates_exist(self):
        assert "gemini-2.5-pro" in RATE_CARD
        assert "gemini-3.1-pro" in RATE_CARD
        assert RATE_CARD["gemini-2.5-pro"].provider == "google"
