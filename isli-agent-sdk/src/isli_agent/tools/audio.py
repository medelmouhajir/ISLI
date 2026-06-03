"""Audio skill tools for ISLI agents — speech-to-text and text-to-speech."""

from typing import Any

import structlog

from isli_agent.client import CoreClient

logger = structlog.get_logger()


async def speech_to_text(
    audio_url: str,
    core_client: CoreClient,
    language: str = "auto",
) -> dict:
    """Transcribe audio from a URL or workspace path to text.

    Use this when you receive an audio attachment from a non-Telegram source
    (web upload, email attachment, task attachment) and need the text content.
    For Telegram voice messages, transcription is already done by the adapter.

    Args:
        audio_url: URL or workspace path to the audio file.
        core_client: Injected Core API client.
        language: Language hint (e.g. 'en', 'fr', 'auto'). Defaults to auto-detection.

    Returns:
        {"text": str, "language": str, "confidence": float, "model": str}
    """
    payload = {"audio_url": audio_url, "language": language}
    try:
        resp = await core_client.client.post(
            "/v1/skills/speech-to-text/transcribe",
            json=payload,
            headers=core_client._get_headers(),
        )
        resp.raise_for_status()
        data = resp.json()
        logger.info(
            "tools.speech_to_text",
            audio_url=audio_url,
            language=data.get("language"),
            confidence=data.get("confidence"),
        )
        return data
    except Exception as exc:
        logger.error("tools.speech_to_text_failed", audio_url=audio_url, error=str(exc))
        return {"error": f"Speech-to-text failed: {exc}"}


async def text_to_speech(
    text: str,
    core_client: CoreClient,
    voice: str | None = None,
    language: str | None = None,
) -> dict:
    """Synthesize speech from text.

    Invoke this when you decide a voice reply is appropriate,
    e.g. "this user prefers voice mode, let me TTS my response."

    Args:
        text: The text to synthesize.
        core_client: Injected Core API client.
        voice: Specific Piper voice name (optional).
        language: Target language for voice selection (optional).

    Returns:
        {"audio_b64": str, "format": "wav", "sample_rate": int, "duration_ms": int, "voice": str}
    """
    payload = {"text": text, "voice": voice, "language": language}
    try:
        resp = await core_client.client.post(
            "/v1/skills/text-to-speech/synthesize",
            json=payload,
            headers=core_client._get_headers(),
        )
        resp.raise_for_status()
        data = resp.json()
        logger.info(
            "tools.text_to_speech",
            text_len=len(text),
            voice=data.get("voice"),
            duration_ms=data.get("duration_ms"),
        )
        return data
    except Exception as exc:
        logger.error("tools.text_to_speech_failed", text_len=len(text), error=str(exc))
        return {"error": f"Text-to-speech failed: {exc}"}


SPEECH_TO_TEXT_DEF = {
    "type": "function",
    "function": {
        "name": "speech_to_text",
        "description": (
            "Transcribe an audio file to text. Use when you receive an audio "
            "attachment from web, email, or workspace and need its text content. "
            "For Telegram voice messages, the adapter already transcribes them."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "audio_url": {
                    "type": "string",
                    "description": "URL or workspace path to the audio file.",
                },
                "language": {
                    "type": "string",
                    "description": "Language hint (e.g. 'en', 'fr', 'auto').",
                    "default": "auto",
                },
            },
            "required": ["audio_url"],
        },
    },
}


TEXT_TO_SPEECH_DEF = {
    "type": "function",
    "function": {
        "name": "text_to_speech",
        "description": (
            "Synthesize speech from text into a base64-encoded WAV audio file. "
            "Use when you want to send a voice reply instead of text, e.g. when the user "
            "has indicated they prefer voice messages. After calling this tool, simply "
            "reply normally with your text response — the audio will be attached "
            "automatically to the outgoing message. Do NOT call send_message with the audio."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The text to synthesize into speech.",
                },
                "voice": {
                    "type": "string",
                    "description": "Specific voice name (optional).",
                },
                "language": {
                    "type": "string",
                    "description": "Target language for voice selection (optional).",
                },
            },
            "required": ["text"],
        },
    },
}


async def send_voice_message(
    agent_id: str,
    channel: str,
    channel_user_id: str,
    text: str,
    core_client: CoreClient,
    voice: str | None = None,
    language: str | None = None,
) -> dict[str, Any]:
    """Convenience wrapper: synthesize text to speech, then send as a voice message.

    This combines text_to_speech and send_message into a single call.
    """
    tts_result = await text_to_speech(text, core_client, voice=voice, language=language)
    if tts_result.get("error"):
        return {"error": f"TTS failed: {tts_result['error']}", "text_sent": False, "voice_sent": False}

    audio_b64 = tts_result.get("audio_b64")
    if not audio_b64:
        return {"error": "TTS returned no audio", "text_sent": False, "voice_sent": False}

    send_result = await send_message(
        agent_id, channel, channel_user_id, text, core_client, audio_b64=audio_b64
    )
    return {
        **send_result,
        "voice_sent": True,
        "duration_ms": tts_result.get("duration_ms"),
        "voice": tts_result.get("voice"),
    }


SEND_VOICE_MESSAGE_DEF = {
    "type": "function",
    "function": {
        "name": "send_voice_message",
        "description": (
            "Send a voice message to a user by synthesizing text to speech and delivering it. "
            "Use this when the user prefers audio replies or when a voice message is more appropriate than text."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "channel": {
                    "type": "string",
                    "description": "Channel identifier, e.g. 'telegram'",
                },
                "channel_user_id": {
                    "type": "string",
                    "description": "The user's identifier on the target channel",
                },
                "text": {
                    "type": "string",
                    "description": "The text to synthesize and send as voice.",
                },
                "voice": {
                    "type": "string",
                    "description": "Specific voice name (optional).",
                },
                "language": {
                    "type": "string",
                    "description": "Target language for voice selection (optional).",
                },
            },
            "required": ["channel", "channel_user_id", "text"],
        },
    },
}
