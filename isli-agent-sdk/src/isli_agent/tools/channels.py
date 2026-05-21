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
) -> dict[str, Any]:
    """Send a proactive message to a user through one of the agent's assigned channels."""
    resp = await core_client.client.post(
        "/v1/skills/send-message/send",
        json={"agent_id": agent_id, "channel": channel, "channel_user_id": channel_user_id, "text": text},
        headers=core_client._get_headers(),
    )
    resp.raise_for_status()
    return resp.json()


SEND_MESSAGE_DEF = {
    "type": "function",
    "function": {
        "name": "send_message",
        "description": _get_tool_desc("send_message", "Send a proactive message to a user through one of the agent's assigned channels (e.g., telegram). The agent must have the channel in its assigned channels list."),
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
            },
            "required": ["channel", "channel_user_id", "text"],
        },
    },
}
