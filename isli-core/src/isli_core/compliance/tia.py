"""Transfer Impact Assessment (TIA) per jurisdiction.

Documented SCCs and data transfer risk assessment.
"""

from typing import Any


class TransferImpactAssessment:
    """Generate and validate TIA for cross-border data transfers."""

    SCC_TEMPLATES: dict[str, dict[str, Any]] = {
        "eu-us": {
            "scc_version": "EU Commission 2021/914 (new SCCs)",
            "module": "Module Two (Controller to Processor)",
            "transfer_mechanism": "Standard Contractual Clauses",
            "supplementary_measures": ["Encryption at rest (AES-256-GCM)", "Pseudonymization where possible"],
            "risk_assessment": "Low risk with supplementary measures in place.",
            "review_date": "2026-12-31",
        },
        "eu-sg": {
            "scc_version": "EU Commission 2021/914 (new SCCs)",
            "module": "Module Two (Controller to Processor)",
            "transfer_mechanism": "Standard Contractual Clauses + Singapore PDPA adequacy",
            "supplementary_measures": ["Regional data residency (SG)"],
            "risk_assessment": "Low risk. Singapore has adequate data protection frameworks.",
            "review_date": "2026-12-31",
        },
        "eu-mena": {
            "scc_version": "EU Commission 2021/914 (new SCCs)",
            "module": "Module Two (Controller to Processor)",
            "transfer_mechanism": "Standard Contractual Clauses",
            "supplementary_measures": [
                "Data residency in EU for EU citizens",
                "Encryption in transit (TLS 1.3)",
                "Encryption at rest (AES-256-GCM)",
            ],
            "risk_assessment": "Medium risk. MENA jurisdictions may have surveillance laws. Supplementary measures required.",
            "review_date": "2026-12-31",
        },
    }

    @staticmethod
    def get_scc(source: str, target: str) -> dict[str, Any] | None:
        key = f"{source}-{target}"
        return TransferImpactAssessment.SCC_TEMPLATES.get(key)

    @staticmethod
    def generate_tia(
        source_jurisdiction: str,
        target_jurisdiction: str,
        data_categories: list[str],
        volume_estimate: str,
    ) -> dict[str, Any]:
        scc = TransferImpactAssessment.get_scc(source_jurisdiction, target_jurisdiction)
        if scc is None:
            return {
                "status": "blocked",
                "reason": f"No SCC template for {source_jurisdiction} -> {target_jurisdiction}",
            }

        return {
            "status": "approved",
            "source": source_jurisdiction,
            "target": target_jurisdiction,
            "data_categories": data_categories,
            "volume_estimate": volume_estimate,
            "scc": scc,
            "recommendations": [
                "Enable encryption at rest",
                "Enable encryption in transit",
                "Enable data residency controls",
                "Review annually",
            ],
        }

    @staticmethod
    def list_routes() -> list[str]:
        return list(TransferImpactAssessment.SCC_TEMPLATES.keys())
