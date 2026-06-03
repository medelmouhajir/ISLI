"""Text-to-Speech engine using Piper TTS (ONNX)."""

import io
import os
import structlog
import soundfile as sf

from isli_audio.config import get_settings

logger = structlog.get_logger()

# Map user-friendly names to piper voice files
_TTS_VOICE_MAP = {
    "piper-en-us-lessac-medium": {
        "url": "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/lessac/medium/en_US-lessac-medium.onnx",
        "json_url": "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json",
        "lang": "en",
    },
    "piper-en-us-amy-medium": {
        "url": "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/amy/medium/en_US-amy-medium.onnx",
        "json_url": "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/amy/medium/en_US-amy-medium.onnx.json",
        "lang": "en",
    },
}


class TTSEngine:
    """Local TTS engine backed by Piper TTS (ONNX Runtime)."""

    def __init__(self):
        self._synthesizer = None
        self._loaded_voice: str = ""
        self.settings = get_settings()

    def _voice_dir(self, voice_name: str) -> str:
        lang = _TTS_VOICE_MAP.get(voice_name, {}).get("lang", "en")
        return f"{self.settings.models_dir}/piper/{lang}"

    def _model_path(self, voice_name: str) -> str:
        return os.path.join(self._voice_dir(voice_name), f"{voice_name}.onnx")

    def _config_path(self, voice_name: str) -> str:
        return os.path.join(self._voice_dir(voice_name), f"{voice_name}.onnx.json")

    def is_downloaded(self, voice_name: str) -> bool:
        return os.path.exists(self._model_path(voice_name)) and os.path.exists(self._config_path(voice_name))

    async def download(self, voice_name: str) -> None:
        """Download a Piper voice model + config."""
        import httpx
        meta = _TTS_VOICE_MAP.get(voice_name)
        if not meta:
            raise ValueError(f"Unknown voice: {voice_name}")

        os.makedirs(self._voice_dir(voice_name), exist_ok=True)

        async with httpx.AsyncClient() as client:
            # Download ONNX model
            model_path = self._model_path(voice_name)
            if not os.path.exists(model_path):
                logger.info("tts.downloading_model", voice=voice_name, url=meta["url"])
                resp = await client.get(meta["url"], follow_redirects=True, timeout=120.0)
                resp.raise_for_status()
                with open(model_path, "wb") as f:
                    f.write(resp.content)
                logger.info("tts.model_downloaded", voice=voice_name, size=len(resp.content))

            # Download JSON config
            config_path = self._config_path(voice_name)
            if not os.path.exists(config_path):
                logger.info("tts.downloading_config", voice=voice_name, url=meta["json_url"])
                resp = await client.get(meta["json_url"], follow_redirects=True, timeout=30.0)
                resp.raise_for_status()
                with open(config_path, "wb") as f:
                    f.write(resp.content)
                logger.info("tts.config_downloaded", voice=voice_name)

    def load(self, voice_name: str) -> None:
        """Load (or reload) the TTS synthesizer."""
        if self._synthesizer is not None and self._loaded_voice == voice_name:
            logger.debug("tts.voice_already_loaded", voice=voice_name)
            return

        model_path = self._model_path(voice_name)
        config_path = self._config_path(voice_name)

        if not os.path.exists(model_path) or not os.path.exists(config_path):
            raise FileNotFoundError(f"Voice files not found for {voice_name}. Run download first.")

        logger.info("tts.loading_voice", voice=voice_name)
        try:
            from piper import PiperVoice
            self._synthesizer = PiperVoice.load(model_path, config_path)
            self._loaded_voice = voice_name
            logger.info("tts.voice_loaded", voice=voice_name)
        except Exception as exc:
            logger.error("tts.load_failed", voice=voice_name, error=str(exc))
            raise

    def ensure_loaded(self, voice_name: str) -> None:
        if self._synthesizer is None or self._loaded_voice != voice_name:
            self.load(voice_name)

    def synthesize(self, text: str, voice_name: str) -> dict:
        """Synthesize text to audio.

        Returns:
            {"audio_b64": str, "format": "wav", "sample_rate": int, "duration_ms": int}
        """
        self.ensure_loaded(voice_name)
        if self._synthesizer is None:
            raise RuntimeError("TTS synthesizer not loaded")

        try:
            import numpy as np
            from piper.config import SynthesisConfig

            # Newer Piper API uses SynthesisConfig + returns AudioChunk iterable
            config = SynthesisConfig(
                speaker_id=None,
                length_scale=1.0,
                noise_scale=0.667,
                noise_w_scale=0.8,
            )
            chunks = self._synthesizer.synthesize(text, syn_config=config)

            # Collect raw int16 bytes from all chunks
            raw_bytes = b"".join(chunk.audio_int16_bytes for chunk in chunks)
            pcm_data = np.frombuffer(raw_bytes, dtype=np.int16)
            sample_rate = self._synthesizer.config.sample_rate if hasattr(self._synthesizer, "config") else 22050

            # Convert to standard WAV using soundfile
            wav_buffer = io.BytesIO()
            sf.write(wav_buffer, pcm_data, sample_rate, format="WAV", subtype="PCM_16")
            wav_bytes = wav_buffer.getvalue()

            import base64
            audio_b64 = base64.b64encode(wav_bytes).decode("utf-8")
            duration_ms = int((len(pcm_data) / sample_rate) * 1000)

            logger.info(
                "tts.synthesized",
                voice=voice_name,
                text_len=len(text),
                duration_ms=duration_ms,
            )
            return {
                "audio_b64": audio_b64,
                "format": "wav",
                "sample_rate": sample_rate,
                "duration_ms": duration_ms,
            }
        except Exception as exc:
            logger.error("tts.synthesize_failed", voice=voice_name, error=str(exc))
            raise


_tts_instance: TTSEngine | None = None


def get_tts_engine() -> TTSEngine:
    global _tts_instance
    if _tts_instance is None:
        _tts_instance = TTSEngine()
    return _tts_instance
