from typing import Any

from isli_agent.client import CoreClient


def _get_tool_desc(name: str, default: str) -> str:
    try:
        from isli_agent.prompts_loader import get_prompts
        return get_prompts()["agent"]["tool_descriptions"].get(name, default)
    except Exception:
        return default


async def send_message(
    agent_id: str,
    channel: str,
    channel_user_id: str,
    text: str,
    core_client: CoreClient,
    audio_b64: str | None = None,
) -> dict[str, Any]:
    """Send a proactive message to a user through one of the agent's assigned channels."""
    payload = {
        "agent_id": agent_id,
        "channel": channel,
        "channel_user_id": channel_user_id,
        "text": text,
    }
    if audio_b64:
        payload["audio_b64"] = audio_b64
    resp = await core_client.client.post(
        "/v1/skills/send-message/send",
        json=payload,
        headers=core_client._get_headers(),
    )
    resp.raise_for_status()
    return resp.json()


def stage_reply_attachment(
    runner: Any,
    session_id: str,
    path: str,
    workspace_id: str | None = None,
    caption: str | None = None,
) -> dict[str, Any]:
    """Stage a file from the agent's workspace or a shared workspace to be attached to the next session reply.

    The file will be sent as an attachment when the agent finishes its current turn.
    Call this tool once per file; up to 5 attachments are allowed per reply.
    """
    staged = {
        "path": path,
        "workspace_id": workspace_id,
        "caption": caption,
    }
    runner._pending_attachments.setdefault(session_id, []).append(staged)
    return {
        "status": "staged",
        "path": path,
        "workspace_id": workspace_id,
        "caption": caption,
        "total_staged": len(runner._pending_attachments[session_id]),
    }


STAGE_REPLY_ATTACHMENT_DEF = {
    "type": "function",
    "x_isli_always_active": True,
    "function": {
        "name": "stage_reply_attachment",
        "description": _get_tool_desc(
            "stage_reply_attachment",
            "Stage a file from the agent's workspace (or a shared workspace) to be returned as an attachment in the next reply to the user. Provide the workspace file path and an optional caption. Up to 5 attachments per reply.",
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Workspace file path, e.g. 'reports/summary.pdf'",
                },
                "workspace_id": {
                    "type": "string",
                    "description": "Optional shared workspace ID. If omitted, the agent's own workspace is used.",
                },
                "caption": {
                    "type": "string",
                    "description": "Optional short caption shown with the attachment.",
                },
            },
            "required": ["path"],
        },
    },
}


SEND_MESSAGE_DEF = {
    "type": "function",
    "function": {
        "name": "send_message",
        "description": _get_tool_desc("send_message", "Send a proactive message to a user through one of the agent's assigned channels (e.g., telegram). The agent must have the channel in its assigned channels list. Optionally include audio_b64 to send a voice message alongside the text."),
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
                    "description": "The message text to send",
                },
                "audio_b64": {
                    "type": "string",
                    "description": "Optional base64-encoded WAV audio to send as a voice message. Use the text_to_speech tool to generate this.",
                },
            },
            "required": ["channel", "channel_user_id", "text"],
        },
    },
}
