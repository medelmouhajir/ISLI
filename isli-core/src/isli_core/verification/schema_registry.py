"""Per-skill output schema definitions for grounding verification."""

SKILL_OUTPUT_SCHEMAS: dict[str, dict] = {
    "web-fetch": {
        "required": ["status_code", "url"],
        "types": {
            "status_code": int,
            "url": str,
        },
    },
    "summarize": {
        "required": ["summary"],
        "types": {
            "summary": str,
        },
    },
    "translate": {
        "required": ["translation"],
        "types": {
            "translation": str,
        },
    },
    "file-read": {
        "required": ["content", "size_bytes", "encoding"],
        "types": {
            "content": str,
            "size_bytes": int,
            "encoding": str,
        },
    },
    "file-write": {
        "required": ["status", "size_bytes"],
        "types": {
            "status": str,
            "size_bytes": int,
        },
    },
    "file-list": {
        "required": ["entries"],
        "types": {
            "entries": list,
        },
    },
    "file-delete": {
        "required": ["status", "path"],
        "types": {
            "status": str,
            "path": str,
        },
    },
    "send-message": {
        "required": ["status", "session_id"],
        "types": {
            "status": str,
            "session_id": str,
        },
    },
}
