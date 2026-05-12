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
}
