"""Mention parsing utilities for Council rooms.

Rules:
- `@agent_id` anywhere in text is a mention.
- Case-insensitive matching against the agent's id and name.
- `@all` / `@everyone` resolves to the current room roster.
- Unknown tokens are ignored (treated as plain text).
"""
from __future__ import annotations

import re
from collections.abc import Iterable

from isli_core.models import Agent

MENTION_RE = re.compile(r"@([a-zA-Z0-9_\-]+)")


def _agent_match_tokens(agent: Agent) -> set[str]:
    """Return the lowercase tokens that can refer to this agent."""
    tokens = {agent.id.lower()}
    if agent.name:
        # Name may contain spaces; use the first word only for compact mentions
        tokens.add(agent.name.lower().split()[0])
    return tokens


def parse_mentions(
    text: str,
    agents: Iterable[Agent],
    roster_agent_ids: Iterable[str] | None = None,
) -> list[str]:
    """Return a deduplicated, ordered list of agent ids mentioned in ``text``.

    Args:
        text: The user message.
        agents: All candidate agents available in the system.
        roster_agent_ids: Current room roster; used to expand ``@all`` / ``@everyone``.

    Returns:
        Ordered list of mentioned agent ids without duplicates.
    """
    tokens = [m.group(1).lower() for m in MENTION_RE.finditer(text or "")]
    if not tokens:
        return []

    lookup: dict[str, Agent] = {}
    for agent in agents:
        for token in _agent_match_tokens(agent):
            lookup[token] = agent

    roster_list = [a.lower() for a in (roster_agent_ids or [])]
    mentioned: list[str] = []
    seen: set[str] = set()

    for token in tokens:
        if token in {"all", "everyone"}:
            for agent_id in roster_list:
                if agent_id not in seen:
                    seen.add(agent_id)
                    mentioned.append(agent_id)
            continue

        matched: Agent | None = lookup.get(token)
        if matched and matched.id not in seen:
            seen.add(matched.id)
            mentioned.append(matched.id)

    return mentioned
