"""Core PII vault logic — deterministic token minting, Redis-backed storage, AES-GCM encryption."""

import hashlib
import json
import re
from datetime import datetime, timezone

import structlog

from .compliance.encryption import PIIEncryption

logger = structlog.get_logger()

# ── Regex patterns for Tier 1 fast detection ─────────────────────────────
PII_PATTERNS = {
    "email": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
    "phone": r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
    "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
    "credit_card": r"\b(?:\d{4}[-\s]?){3}\d{4}\b",
    "dob": r"\b\d{2}/\d{2}/\d{4}\b",
    "corp_id": r"\b[A-Z]{2,4}-\d{4,8}\b",
}


def _normalize_value(value: str) -> str:
    """Strip whitespace and lowercase for deterministic hashing."""
    return value.strip().lower()


def mint_token(session_id: str, category: str, value: str) -> str:
    """Mint a deterministic token for a PII value within a session."""
    normalized = _normalize_value(value)
    hash_hex = hashlib.sha256(
        f"{session_id}:{category}:{normalized}".encode()
    ).hexdigest()[:16]
    return f"{{{{PII:{category}:{hash_hex}}}}}"


def regex_scan(text: str) -> dict[str, list[str]]:
    """Fast regex scan returning {category: [matches]}."""
    found: dict[str, list[str]] = {}
    for category, pattern in PII_PATTERNS.items():
        matches = list(set(re.findall(pattern, text)))
        if matches:
            found[category] = matches
    return found


def apply_tokens(text: str, token_map: dict[str, str]) -> str:
    """Replace original values with their tokens in a text string."""
    # Sort by original value length descending to avoid partial replacements
    for token, original in sorted(token_map.items(), key=lambda x: len(x[1]), reverse=True):
        text = text.replace(original, token)
    return text


def rehydrate_text(text: str, token_map: dict[str, str]) -> tuple[str, list[str]]:
    """Replace tokens with original values. Returns (text, unresolved_tokens)."""
    unresolved: list[str] = []
    # Sort by token length descending to avoid partial replacements
    for token, original in sorted(token_map.items(), key=lambda x: len(x[0]), reverse=True):
        if token in text:
            text = text.replace(token, original)
    # Check for any remaining tokens
    for token in sorted(token_map.keys(), key=len, reverse=True):
        if token in text:
            unresolved.append(token)
    return text, unresolved


class PiiVault:
    """Redis-backed token vault with AES-256-GCM encryption of original values."""

    def __init__(self, redis_client, token_ttl_seconds: int = 86400):
        self.redis = redis_client
        self.token_ttl = token_ttl_seconds
        self.enc = PIIEncryption()

    def _token_key(self, session_id: str, token_id: str) -> str:
        return f"keeper:pii:tokens:{session_id}:{token_id}"

    def _session_index_key(self, session_id: str) -> str:
        return f"keeper:pii:sessions:{session_id}"

    async def persist_token_map(self, session_id: str, token_map: dict[str, str]) -> None:
        """Store token mappings in Redis with encrypted values."""
        if not token_map:
            return
        pipe = self.redis.pipeline()
        for token, original in token_map.items():
            # Parse token to extract category
            parts = token.strip("{}").split(":")
            category = parts[1] if len(parts) >= 2 else "unknown"
            encrypted = self.enc.encrypt_field(original, context=session_id)
            data = json.dumps({
                "category": category,
                "encrypted_value": encrypted,
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
            pipe.setex(self._token_key(session_id, token), self.token_ttl, data)
            pipe.sadd(self._session_index_key(session_id), token)
        pipe.expire(self._session_index_key(session_id), self.token_ttl)
        await pipe.execute()
        logger.info("pii_vault.tokens_persisted", session_id=session_id, count=len(token_map))

    async def resolve_token(self, session_id: str, token_id: str) -> str | None:
        """Resolve a single token to its original value."""
        raw = await self.redis.get(self._token_key(session_id, token_id))
        if not raw:
            return None
        data = json.loads(raw)
        return self.enc.decrypt_field(data["encrypted_value"])

    async def get_session_token_map(self, session_id: str) -> dict[str, str]:
        """Retrieve all token mappings for a session."""
        token_ids = await self.redis.smembers(self._session_index_key(session_id))
        if not token_ids:
            return {}
        result: dict[str, str] = {}
        for token_id in token_ids:
            original = await self.resolve_token(session_id, token_id)
            if original:
                result[token_id] = original
        return result

    async def build_rehydrate_map(self, session_id: str, text: str) -> dict[str, str]:
        """Build a minimal token map containing only tokens present in the text."""
        full_map = await self.get_session_token_map(session_id)
        return {token: original for token, original in full_map.items() if token in text}
