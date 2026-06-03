"""Load prompts from prompts.yaml with env-var override support."""

import os
from functools import lru_cache
from pathlib import Path

import yaml


@lru_cache(maxsize=1)
def get_prompts() -> dict:
    """Load and cache the prompts YAML.

    Search order:
    1. PROMPTS_FILE env var
    2. /app/prompts.yaml (Docker default)
    3. ./prompts.yaml relative to this file (native dev via symlink)
    """
    paths = []
    if env_path := os.getenv("PROMPTS_FILE"):
        paths.append(Path(env_path))
    paths.append(Path("/app/prompts.yaml"))
    paths.append(Path(__file__).resolve().parent.parent.parent / "prompts.yaml")

    for p in paths:
        if p.exists():
            with open(p, encoding="utf-8") as f:
                return yaml.safe_load(f)

    raise FileNotFoundError(
        f"prompts.yaml not found. Searched: {[str(p) for p in paths]}. "
        "Set PROMPTS_FILE or place prompts.yaml in the service root."
    )


def clear_prompts_cache() -> None:
    """Clear the LRU cache so the next call re-reads from disk."""
    get_prompts.cache_clear()
