"""Speech-to-Text engine using faster-whisper."""

import io
import structlog
from faster_whisper import WhisperModel

from isli_audio.config import get_settings

logger = structlog.get_logger()

# Map user-friendly names to faster-whisper model sizes
_STT_MODEL_MAP = {
    "whisper-tiny": "tiny",
    "whisper-base": "base",
    "whisper-small": "small",
    "whisper-medium": "medium",
    "whisper-large-v3": "large-v3",
}


class STTEngine:
    """Local STT engine backed by faster-whisper (CTranslate2)."""

    def __init__(self):
        self._model: WhisperModel | None = None
        self._loaded_size: str = ""
        self.settings = get_settings()

    def _resolve_size(self, model_name: str) -> str:
        """Resolve configured model name to faster-whisper size string or local directory path."""
        if model_name == "whisper-base-darija":
            return f"{self.settings.models_dir}/whisper/whisper-base-darija"
        return _STT_MODEL_MAP.get(model_name, model_name.replace("whisper-", ""))

    def load(self, model_name: str) -> None:
        """Load (or reload) the STT model."""
        size = self._resolve_size(model_name)
        if self._model is not None and self._loaded_size == size:
            logger.debug("stt.model_already_loaded", size=size)
            return

        logger.info("stt.loading_model", model_name=model_name, size=size)
        try:
            self._model = WhisperModel(
                size,
                device="cpu",
                compute_type="int8",
                download_root=f"{self.settings.models_dir}/whisper",
                cpu_threads=4,
            )
            self._loaded_size = size
            logger.info("stt.model_loaded", size=size)
        except Exception as exc:
            logger.error("stt.load_failed", size=size, error=str(exc))
            raise

    def ensure_loaded(self, model_name: str) -> None:
        if self._model is None or self._loaded_size != self._resolve_size(model_name):
            self.load(model_name)

    def transcribe(
        self,
        audio_bytes: bytes,
        model_name: str,
        language: str = "auto",
    ) -> dict:
        """Transcribe audio bytes to text.

        Args:
            audio_bytes: Raw audio file bytes (wav, mp3, ogg, etc. — faster-whisper handles ffmpeg internally).
            model_name: The configured STT model name (e.g. "whisper-tiny").
            language: Language hint or "auto" for auto-detection.

        Returns:
            {"text": str, "language": str, "confidence": float}
        """
        self.ensure_loaded(model_name)
        if self._model is None:
            raise RuntimeError("STT model not loaded")

        # Override auto language detection for whisper-base-darija as it only supports Arabic/Darija script
        if model_name == "whisper-base-darija" and language == "auto":
            language = "ar"

        lang_hint = None if language == "auto" else language

        try:
            segments, info = self._model.transcribe(
                io.BytesIO(audio_bytes),
                language=lang_hint,
                beam_size=5,
                best_of=5,
                condition_on_previous_text=True,
            )
            text_parts = []
            for segment in segments:
                text_parts.append(segment.text.strip())

            full_text = " ".join(text_parts).strip()
            detected_lang = info.language if info.language else language
            confidence = getattr(info, "language_probability", 0.0) or 0.0

            logger.info(
                "stt.transcribed",
                model=model_name,
                language=detected_lang,
                confidence=round(confidence, 3),
                text_len=len(full_text),
            )
            return {
                "text": full_text,
                "language": detected_lang,
                "confidence": round(confidence, 3),
            }
        except Exception as exc:
            logger.error("stt.transcribe_failed", model=model_name, error=str(exc))
            raise


_stt_instance: STTEngine | None = None


def get_stt_engine() -> STTEngine:
    global _stt_instance
    if _stt_instance is None:
        _stt_instance = STTEngine()
    return _stt_instance
