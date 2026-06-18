from typing import Any

from jsonschema import Draft202012Validator
from jsonschema import ValidationError as JSONSchemaValidationError

EVENT_SCHEMAS: dict[str, dict[str, Any]] = {
    "v1": {
        "task:created": {
            "type": "object",
            "required": ["type", "task"],
            "properties": {
                "type": {"const": "task:created"},
                "task": {"type": "object"},
            },
        },
        "task:updated": {
            "type": "object",
            "required": ["type", "task_id", "changes"],
            "properties": {
                "type": {"const": "task:updated"},
                "task_id": {"type": "string"},
                "changes": {"type": "object"},
            },
        },
        "task:moved": {
            "type": "object",
            "required": ["type", "task_id", "from", "to"],
            "properties": {
                "type": {"const": "task:moved"},
                "task_id": {"type": "string"},
                "from": {"type": "string"},
                "to": {"type": "string"},
            },
        },
        "agent:heartbeat": {
            "type": "object",
            "required": ["type", "agent_id", "status"],
            "properties": {
                "type": {"const": "agent:heartbeat"},
                "agent_id": {"type": "string"},
                "status": {"type": "string"},
                "anomaly": {"type": ["string", "null"]},
            },
        },
        "agent:online": {
            "type": "object",
            "required": ["type", "agent_id"],
            "properties": {
                "type": {"const": "agent:online"},
                "agent_id": {"type": "string"},
            },
        },
        "agent:offline": {
            "type": "object",
            "required": ["type", "agent_id"],
            "properties": {
                "type": {"const": "agent:offline"},
                "agent_id": {"type": "string"},
            },
        },
        "keeper:event": {
            "type": "object",
            "required": ["type", "event_type", "payload"],
            "properties": {
                "type": {"const": "keeper:event"},
                "event_type": {"type": "string"},
                "payload": {"type": "object"},
            },
        },
        "system:alert": {
            "type": "object",
            "required": ["type", "severity", "message"],
            "properties": {
                "type": {"const": "system:alert"},
                "severity": {"type": "string", "enum": ["info", "warning", "critical"]},
                "message": {"type": "string"},
                "category": {"type": "string"},
                "agent_id": {"type": ["string", "null"]},
                "task_id": {"type": ["string", "null"]},
                "user_id": {"type": ["string", "null"]},
            },
        },
        "notification:new": {
            "type": "object",
            "required": ["type", "notification"],
            "properties": {
                "type": {"const": "notification:new"},
                "notification": {"type": "object"},
            },
        },
        "notification:read": {
            "type": "object",
            "required": ["type", "notification_id"],
            "properties": {
                "type": {"const": "notification:read"},
                "notification_id": {"type": "string"},
                "user_id": {"type": "string"},
            },
        },
        "notification:read_all": {
            "type": "object",
            "required": ["type", "user_id"],
            "properties": {
                "type": {"const": "notification:read_all"},
                "user_id": {"type": "string"},
            },
        },
        "session:message": {
            "type": "object",
            "required": ["type", "session_id", "agent_id", "message"],
            "properties": {
                "type": {"const": "session:message"},
                "session_id": {"type": "string"},
                "agent_id": {"type": "string"},
                "user_id": {"type": ["string", "null"]},
                "channel": {"type": ["string", "null"]},
                "message": {"type": "object"},
                "messages": {"type": "array"},
                "context_summary": {"type": ["string", "null"]},
                "audio_url": {"type": ["string", "null"]},
                "room_id": {"type": ["string", "null"]},
            },
        },
        "room:updated": {
            "type": "object",
            "required": ["type", "room_id"],
            "properties": {
                "type": {"const": "room:updated"},
                "room_id": {"type": "string"},
                "status": {"type": ["string", "null"]},
                "parent_id": {"type": ["string", "null"]},
            },
        },
        "room:agent_joined": {
            "type": "object",
            "required": ["type", "room_id", "agent_id"],
            "properties": {
                "type": {"const": "room:agent_joined"},
                "room_id": {"type": "string"},
                "agent_id": {"type": "string"},
                "agent_name": {"type": ["string", "null"]},
                "picture": {"type": ["string", "null"]},
            },
        },
    }
}

CURRENT_VERSION = "v1"


class SchemaValidationError(Exception):
    pass


class BackwardCompatibilityError(Exception):
    pass


def validate_event(payload: dict[str, Any], version: str = CURRENT_VERSION) -> None:
    schema_version = EVENT_SCHEMAS.get(version)
    if schema_version is None:
        raise SchemaValidationError(f"Unknown schema version: {version}")
    event_type = payload.get("type")
    schema = schema_version.get(event_type)
    if schema is None:
        raise SchemaValidationError(f"Unknown event type: {event_type} in version {version}")
    try:
        Draft202012Validator(schema).validate(payload)
    except JSONSchemaValidationError as exc:
        raise SchemaValidationError(f"Event validation failed: {exc.message}") from exc


def check_backward_compatible(old_version: str, new_version: str) -> None:
    old = EVENT_SCHEMAS.get(old_version)
    new = EVENT_SCHEMAS.get(new_version)
    if old is None or new is None:
        raise BackwardCompatibilityError("Missing schema version for comparison")
    for event_type, old_schema in old.items():
        if event_type not in new:
            raise BackwardCompatibilityError(f"Removed event type: {event_type}")
        new_schema = new[event_type]
        old_required = set(old_schema.get("required", []))
        new_required = set(new_schema.get("required", []))
        if not old_required.issubset(new_required):
            raise BackwardCompatibilityError(
                f"Event {event_type}: removed required fields {old_required - new_required}"
            )
