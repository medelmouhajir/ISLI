"""Local-model TCO (Total Cost of Ownership) worksheet.

Electricity + depreciation + labor model.
"""

from dataclasses import dataclass
from typing import Any


@dataclass
class HardwareConfig:
    gpu_watts: float = 300.0  # e.g., RTX 4090 at full load
    cpu_watts: float = 65.0
    hours_per_day: float = 8.0
    kwh_price_usd: float = 0.15
    hardware_cost_usd: float = 2000.0
    depreciation_years: float = 3.0
    admin_hours_per_month: float = 2.0
    admin_hourly_rate_usd: float = 50.0


class TCOEstimator:
    """Estimate TCO for running local models (Ollama) vs cloud APIs."""

    @staticmethod
    def electricity_cost(config: HardwareConfig | None = None) -> float:
        cfg = config or HardwareConfig()
        total_watts = cfg.gpu_watts + cfg.cpu_watts
        daily_kwh = (total_watts * cfg.hours_per_day) / 1000.0
        monthly_kwh = daily_kwh * 30
        return monthly_kwh * cfg.kwh_price_usd

    @staticmethod
    def depreciation_cost(config: HardwareConfig | None = None) -> float:
        cfg = config or HardwareConfig()
        return cfg.hardware_cost_usd / (cfg.depreciation_years * 12)

    @staticmethod
    def labor_cost(config: HardwareConfig | None = None) -> float:
        cfg = config or HardwareConfig()
        return cfg.admin_hours_per_month * cfg.admin_hourly_rate_usd

    @staticmethod
    def monthly_tco(config: HardwareConfig | None = None) -> dict[str, Any]:
        elec = TCOEstimator.electricity_cost(config)
        depr = TCOEstimator.depreciation_cost(config)
        labor = TCOEstimator.labor_cost(config)
        total = elec + depr + labor
        return {
            "electricity_usd": round(elec, 2),
            "depreciation_usd": round(depr, 2),
            "labor_usd": round(labor, 2),
            "monthly_tco_usd": round(total, 2),
            "yearly_tco_usd": round(total * 12, 2),
            "cost_per_hour": round(total / (config.hours_per_day * 30 if config else 240), 4),
        }

    @staticmethod
    def break_even_cloud_turns(
        cloud_model_id: str,
        avg_input_tokens: int,
        avg_output_tokens: int,
        turns_per_day: int,
        config: HardwareConfig | None = None,
    ) -> dict[str, Any]:
        from isli_core.cost.rate_card import CostEstimator

        monthly_tco = TCOEstimator.monthly_tco(config)["monthly_tco_usd"]
        cloud_cost_per_turn = CostEstimator.estimate_turn(
            cloud_model_id, avg_input_tokens, avg_output_tokens
        )
        if cloud_cost_per_turn == 0:
            return {"break_even_turns": float("inf"), "note": "Cloud model is free"}

        daily_cloud = cloud_cost_per_turn * turns_per_day
        monthly_cloud = daily_cloud * 30
        break_even_turns = int(monthly_tco / cloud_cost_per_turn) if cloud_cost_per_turn > 0 else 0

        return {
            "cloud_model": cloud_model_id,
            "local_monthly_tco_usd": monthly_tco,
            "cloud_monthly_cost_usd": round(monthly_cloud, 2),
            "break_even_turns_per_month": break_even_turns,
            "break_even_turns_per_day": int(break_even_turns / 30),
            "savings_at_2x_break_even": round(monthly_cloud - monthly_tco * 2, 2),
        }
