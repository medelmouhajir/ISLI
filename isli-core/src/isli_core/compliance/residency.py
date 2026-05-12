"""Data residency controls: geo-fencing and SCC enforcement."""

import os
import structlog
from typing import Any

logger = structlog.get_logger()

# Configurable per deployment
DEFAULT_REGION = os.getenv("ISLI_DATA_REGION", "eu-west-1")
ALLOWED_REGIONS = os.getenv("ISLI_ALLOWED_REGIONS", "eu-west-1,eu-central-1").split(",")
BLOCKED_JURISDICTIONS = os.getenv("ISLI_BLOCKED_JURISDICTIONS", "cn,rus,irn").split(",")


class DataResidency:
    """Enforce data residency and cross-border transfer rules."""

    @staticmethod
    def current_region() -> str:
        return DEFAULT_REGION

    @staticmethod
    def is_allowed_region(region: str) -> bool:
        return region in ALLOWED_REGIONS

    @staticmethod
    def is_blocked_jurisdiction(jurisdiction: str) -> bool:
        return jurisdiction.lower() in BLOCKED_JURISDICTIONS

    @staticmethod
    def can_store(user_region: str) -> bool:
        """Check if user data from a region can be stored in the current deployment."""
        if not DataResidency.is_allowed_region(DataResidency.current_region()):
            logger.error("residency.current_region_not_allowed", region=DEFAULT_REGION)
            return False
        if DataResidency.is_blocked_jurisdiction(user_region):
            logger.error("residency.blocked_jurisdiction", jurisdiction=user_region)
            return False
        # EU data must stay in EU
        if user_region.startswith("eu") and not DEFAULT_REGION.startswith("eu"):
            logger.error("residency.eu_data_outside_eu", user_region=user_region, deploy_region=DEFAULT_REGION)
            return False
        return True

    @staticmethod
    def scc_required(source_region: str, target_region: str) -> bool:
        """Determine if Standard Contractual Clauses are required."""
        eu_regions = {"eu-west-1", "eu-central-1", "eu-north-1"}
        source_in_eu = source_region in eu_regions
        target_in_eu = target_region in eu_regions
        if source_in_eu and not target_in_eu:
            return True
        return False

    @staticmethod
    def get_scc_version() -> str:
        return "EU Commission 2021/914 (new SCCs)"
