from typing import Any

from isli_agent.client import CoreClient


class NotificationRateLimitError(Exception):
    """Raised when the agent exceeds the per-hour notification rate limit."""


class NotificationDeliveryError(Exception):
    """Raised when the notification could not be delivered to Core."""


def _get_tool_desc(name: str, default: str) -> str:
    try:
        from isli_agent.prompts_loader import get_prompts
        return get_prompts()["agent"]["tool_descriptions"].get(name, default)
    except Exception:
        return default


async def notify_user(
    user_id: str,
    title: str,
    message: str,
    priority: str,
    agent_id: str,
    core_client: CoreClient,
) -> dict[str, Any]:
    """Send a notification to a user through the unified notification system.

    The notification appears in the user's Board UI inbox and, depending on
    their preferences and quiet hours, may also escalate to Telegram.
    Rate-limited to 20 notifications per hour per user per agent.
    """
    resp = await core_client.client.post(
        "/v1/notifications/send",
        json={
            "user_id": user_id,
            "title": title,
            "message": message,
            "priority": priority,
            "agent_id": agent_id,
        },
        headers=core_client._get_headers(),
    )
    if resp.status_code == 429:
        raise NotificationRateLimitError(
            "Notification rate limit exceeded for this agent (max 20/hour per user)."
        )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("ok"):
        raise NotificationDeliveryError(
            f"Notification delivery failed: {data.get('detail', 'unknown error')}"
        )
    return data


NOTIFY_USER_DEF = {
    "type": "function",
    "function": {
        "name": "notify_user",
        "description": _get_tool_desc(
            "notify_user",
            "Display a notification card in the user's web UI. "
            "Use this when the user asks you to send a notification, reminder, or alert."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "The target user's identifier (e.g., Telegram user ID, email, or internal user UUID).",
                },
                "title": {
                    "type": "string",
                    "description": "Short notification title (max 120 characters).",
                },
                "message": {
                    "type": "string",
                    "description": "Notification body text. Keep concise — users may receive this on mobile.",
                },
                "priority": {
                    "type": "string",
                    "enum": ["critical", "high", "normal", "low"],
                    "description": "Priority level. Critical bypasses quiet hours; low is batched into digests.",
                },
            },
            "required": ["user_id", "title", "message", "priority"],
        },
    },
}
