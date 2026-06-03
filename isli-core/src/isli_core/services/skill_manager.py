import importlib.util
import json
import os
from typing import Any

import structlog

from isli_core.config import get_settings

logger = structlog.get_logger()


class DynamicSkillManager:
    def __init__(self):
        settings = get_settings()
        self.base_path = settings.installed_skills_path
        self._skills: dict[str, dict[str, Any]] = {}
        self._handlers: dict[str, Any] = {}

        if not os.path.exists(self.base_path):
            os.makedirs(self.base_path, exist_ok=True)

        self.refresh_registry()

    def refresh_registry(self):
        """Scans the installed_skills directory for skills."""
        new_skills = {}
        if not os.path.exists(self.base_path):
            return

        for skill_id in os.listdir(self.base_path):
            skill_dir = os.path.join(self.base_path, skill_id)
            if not os.path.isdir(skill_dir):
                continue

            manifest_path = os.path.join(skill_dir, "skill.json")
            if os.path.exists(manifest_path):
                try:
                    with open(manifest_path, "r") as f:
                        meta = json.load(f)
                        new_skills[skill_id] = meta
                except Exception as e:
                    logger.error("skill_manager.load_manifest_failed", skill_id=skill_id, error=str(e))
            else:
                # Default metadata if no manifest
                new_skills[skill_id] = {
                    "name": skill_id,
                    "description": "Installed via Skills Store",
                    "type": "dynamic",
                    "category": "custom",
                }

        self._skills = new_skills
        logger.info("skill_manager.registry_refreshed", count=len(self._skills))

    def get_skill_metadata(self) -> dict[str, dict[str, Any]]:
        return self._skills

    def get_handler(self, skill_id: str):
        """Dynamically loads the main.py from the skill directory."""
        if skill_id in self._handlers:
            return self._handlers[skill_id]

        skill_dir = os.path.join(self.base_path, skill_id)
        main_py = os.path.join(skill_dir, "main.py")

        if not os.path.exists(main_py):
            return None

        try:
            spec = importlib.util.spec_from_file_location(f"dynamic_skill_{skill_id}", main_py)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            self._handlers[skill_id] = module
            return module
        except Exception as e:
            logger.error("skill_manager.load_handler_failed", skill_id=skill_id, error=str(e))
            return None


# Singleton instance
skill_manager = DynamicSkillManager()
