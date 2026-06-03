import structlog
import subprocess
from typing import Any

logger = structlog.get_logger()

MAX_VOICE_DURATION_SEC = 300

MIME_ALIASES = {
    "image/jpg": "image/jpeg",
    "audio/mp3": "audio/mpeg",
    "video/mpg": "video/mpeg",
}

PLATFORM_FORMATS = {
    "telegram": {
        "allowed_types": {"image", "video", "audio", "document", "voice"},
        "max_size_mb": 20,
    },
    "whatsapp": {
        "allowed_types": {"image", "video", "audio", "document"},
        "max_size_mb": 16,
    },
    "email": {
        "allowed_types": {"image", "video", "audio", "document"},
        "max_size_mb": 25,
    },
    "web": {
        "allowed_types": {"image", "video", "audio", "document"},
        "max_size_mb": 100,
    },
}


def normalize_mime(mime_type: str) -> str:
    """Normalize MIME type aliases to canonical form."""
    normalized = mime_type.lower().strip()
    return MIME_ALIASES.get(normalized, normalized)


def mime_to_media_type(mime_type: str) -> str:
    """Map MIME type to platform-agnostic media type category."""
    mime = normalize_mime(mime_type)
    if mime.startswith("image/"):
        return "image"
    if mime.startswith("video/"):
        return "video"
    if mime.startswith("audio/"):
        return "audio"
    return "document"


def validate_for_channel(media_type: str, size_bytes: int, channel: str) -> None:
    config = PLATFORM_FORMATS.get(channel, PLATFORM_FORMATS["web"])
    cat = mime_to_media_type(media_type)
    if cat not in config["allowed_types"]:
        raise ValueError(f"Media type '{cat}' not allowed on {channel}")
    size_mb = size_bytes / (1024 * 1024)
    if size_mb > config["max_size_mb"]:
        raise ValueError(
            f"File size {size_mb:.1f}MB exceeds {channel} limit of {config['max_size_mb']}MB"
        )


def convert_wav_to_opus_ogg(wav_bytes: bytes) -> bytes:
    """Convert WAV audio bytes to Opus/OGG using ffmpeg.

    Raises RuntimeError if ffmpeg fails.
    """
    proc = subprocess.run(
        [
            "ffmpeg",
            "-i", "-",
            "-f", "ogg",
            "-c:a", "libopus",
            "-b:a", "24k",
            "-vbr", "on",
            "-compression_level", "10",
            "-",
        ],
        input=wav_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", errors="ignore")[:500]
        logger.error("ffmpeg.wav_to_opus_failed", stderr=stderr)
        raise RuntimeError(f"ffmpeg WAV→OGG conversion failed: {stderr}")
    return proc.stdout


def convert_attachment(attachment: dict[str, Any], target_channel: str) -> dict[str, Any]:
    """Convert attachment metadata for target channel."""
    mime = normalize_mime(attachment.get("mime_type", "application/octet-stream"))
    media_type = mime_to_media_type(mime)
    size = attachment.get("size_bytes", 0)

    validate_for_channel(mime, size, target_channel)

    converted = {
        "mime_type": mime,
        "media_type": media_type,
        "size_bytes": size,
        "filename": attachment.get("filename"),
        "url": attachment.get("url"),
        "caption": attachment.get("caption"),
    }

    # Platform-specific field mapping
    if target_channel == "telegram":
        converted["telegram_type"] = media_type
    elif target_channel == "whatsapp":
        converted["whatsapp_type"] = media_type

    logger.info(
        "attachment.converted",
        source_mime=attachment.get("mime_type"),
        target_channel=target_channel,
        media_type=media_type,
    )
    return converted
