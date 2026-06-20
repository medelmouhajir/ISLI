#!/usr/bin/env python3
"""Minimal hello-world USR skill."""

import json
import sys


def run(payload: dict) -> dict:
    """Return a greeting for the provided name."""
    name = payload.get("name", "World")
    if not isinstance(name, str):
        raise ValueError("'name' must be a string")
    return {"message": f"Hello, {name}!"}


if __name__ == "__main__":
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
        result = run(payload)
        print(json.dumps(result))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        sys.exit(1)
