import json
import os
import structlog
from isli_audio.config import get_settings

logger = structlog.get_logger()

CONFIG_PATH = "/app/data/audio_model_config.json"


class AudioModelManager:
    """Manages audio model slots (stt, tts) with language support."""

    def __init__(self):
        self.settings = get_settings()
        self.config = {
            "stt": self.settings.audio_stt_model,
            "tts": self.settings.audio_tts_model,
            "language": self.settings.audio_language,
            "tts_voices_by_language": {
                "en": self.settings.audio_tts_model,
            },
        }
        self.load()

    def load(self):
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r") as f:
                    self.config.update(json.load(f))
                logger.info("audio_model_manager.loaded_config", config=self.config)
            except Exception as e:
                logger.error("audio_model_manager.load_failed", error=str(e))

    def save(self):
        try:
            os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
            with open(CONFIG_PATH, "w") as f:
                json.dump(self.config, f)
            logger.info("audio_model_manager.saved_config", config=self.config)
        except Exception as e:
            logger.error("audio_model_manager.save_failed", error=str(e))

    def set_model(self, slot: str, model_name: str):
        if slot in ("stt", "tts", "language"):
            self.config[slot] = model_name
            if slot == "tts":
                lang = self.config.get("language", "en")
                self.config.setdefault("tts_voices_by_language", {})
                self.config["tts_voices_by_language"][lang] = model_name
            self.save()
        else:
            raise ValueError(f"Invalid slot: {slot}")

    def get_model(self, slot: str) -> str:
        return self.config.get(slot, "")

    def get_tts_voice_for_language(self, language: str | None = None) -> str:
        lang = language or self.config.get("language", "en")
        voices = self.config.get("tts_voices_by_language", {})
        return voices.get(lang, self.config.get("tts", ""))
