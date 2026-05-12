"""HIPAA / SOC 2 / ISO 42001 control-objective mapping.

This module provides a structured mapping of ISLI features to compliance controls.
"""

from typing import Any


class ComplianceMapping:
    """Map ISLI features to HIPAA, SOC 2, and ISO 42001 controls."""

    CONTROLS: dict[str, dict[str, Any]] = {
        "AC-1": {
            "frameworks": ["SOC-2-CC6.1", "ISO-42001-A.7.1"],
            "title": "Access Control Policy",
            "isli_features": ["JWT per-agent auth", "RBAC on skills", "Internal JWT between Core and Skills"],
            "status": "implemented",
        },
        "AC-3": {
            "frameworks": ["SOC-2-CC6.2", "HIPAA-164.312(a)(1)"],
            "title": "Access Enforcement",
            "isli_features": ["Skill proxy auth", "Consent gating per channel"],
            "status": "implemented",
        },
        "AU-6": {
            "frameworks": ["SOC-2-CC7.2", "ISO-42001-A.7.2"],
            "title": "Audit Review",
            "isli_features": ["Audit logs with cryptographic integrity (Merkle chain)", "Cost anomaly detection"],
            "status": "implemented",
        },
        "AU-9": {
            "frameworks": ["SOC-2-CC7.2", "HIPAA-164.312(b)"],
            "title": "Protection of Audit Information",
            "isli_features": ["AES-256-GCM PII encryption", "Merkle chain hash on audit_logs"],
            "status": "implemented",
        },
        "CM-3": {
            "frameworks": ["SOC-2-CC8.1", "ISO-42001-A.8.1"],
            "title": "Configuration Change Control",
            "isli_features": ["Alembic migrations", "Event schema registry with backward-compat checks"],
            "status": "implemented",
        },
        "CP-9": {
            "frameworks": ["SOC-2-A1.2", "HIPAA-164.308(a)(7)"],
            "title": "Information System Backup",
            "isli_features": ["pg_dump cron", "ChromaDB snapshot", "Redis RDB backup", "Agent turn checkpointing"],
            "status": "implemented",
        },
        "IR-4": {
            "frameworks": ["SOC-2-CC7.3", "ISO-42001-A.7.3"],
            "title": "Incident Handling",
            "isli_features": ["Global e-stop", "Dead-letter queue", "Circuit breakers", "Chaos engineering suite"],
            "status": "implemented",
        },
        "SC-7": {
            "frameworks": ["SOC-2-CC6.6", "HIPAA-164.312(e)"],
            "title": "Boundary Protection",
            "isli_features": ["SSRF defense with URL blocklists", "Sandboxed HTTP client"],
            "status": "implemented",
        },
        "SI-3": {
            "frameworks": ["SOC-2-CC7.1", "ISO-42001-A.7.4"],
            "title": "Malicious Code Protection",
            "isli_features": ["Prompt injection defense", "Input sanitization"],
            "status": "partial",
        },
        "PR-1": {
            "frameworks": ["ISO-42001-A.6.1"],
            "title": "AI Privacy Requirements",
            "isli_features": ["GDPR soft-delete", "Crypto-shredding", "SAR fulfillment pipeline", "User consent capture"],
            "status": "implemented",
        },
        "TR-1": {
            "frameworks": ["ISO-42001-A.6.2"],
            "title": "Transparency",
            "isli_features": ["Kanban board visibility", "Per-agent token usage dashboard", "Audit trail"],
            "status": "implemented",
        },
    }

    @staticmethod
    def get_control(control_id: str) -> dict[str, Any] | None:
        return ComplianceMapping.CONTROLS.get(control_id)

    @staticmethod
    def list_by_framework(framework: str) -> list[dict[str, Any]]:
        return [
            {"control_id": k, **v}
            for k, v in ComplianceMapping.CONTROLS.items()
            if any(framework in f for f in v["frameworks"])
        ]

    @staticmethod
    def coverage_summary() -> dict[str, Any]:
        total = len(ComplianceMapping.CONTROLS)
        implemented = sum(1 for v in ComplianceMapping.CONTROLS.values() if v["status"] == "implemented")
        partial = sum(1 for v in ComplianceMapping.CONTROLS.values() if v["status"] == "partial")
        return {
            "total_controls": total,
            "implemented": implemented,
            "partial": partial,
            "not_started": total - implemented - partial,
            "coverage_percent": round((implemented / total) * 100, 1),
        }
