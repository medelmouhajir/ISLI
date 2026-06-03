import json
import os
import structlog
from isli_keeper.config import get_settings

logger = structlog.get_logger()

CONFIG_PATH = "/app/data/model_config.json"

class ModelManager:
    def __init__(self):
        self.settings = get_settings()
        self.config = {
            "gen": self.settings.ollama_gen_model,
            "embed": self.settings.ollama_embed_model,
        }
        self.load()

    def load(self):
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r") as f:
                    self.config.update(json.load(f))
                logger.info("model_manager.loaded_config", config=self.config)
            except Exception as e:
                logger.error("model_manager.load_failed", error=str(e))

    def save(self):
        try:
            os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
            with open(CONFIG_PATH, "w") as f:
                json.dump(self.config, f)
            logger.info("model_manager.saved_config", config=self.config)
        except Exception as e:
            logger.error("model_manager.save_failed", error=str(e))

    def set_model(self, slot: str, model_name: str):
        if slot in self.config:
            self.config[slot] = model_name
            self.save()
        else:
            raise ValueError(f"Invalid model slot: {slot}")

    def get_model(self, slot: str) -> str:
        return self.config.get(slot, "")
