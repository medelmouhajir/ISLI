"""AES-256-GCM encryption for raw PII in archive."""

import os
import structlog
from base64 import b64encode, b64decode
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = structlog.get_logger()

ENCRYPTION_KEY = os.getenv("PII_ENCRYPTION_KEY", "")


def _get_key() -> bytes:
    if not ENCRYPTION_KEY:
        raise RuntimeError("PII_ENCRYPTION_KEY environment variable is not set")
    key = ENCRYPTION_KEY.encode()
    if len(key) != 32:
        # Derive 32-byte key from provided key using SHA-256
        import hashlib

        return hashlib.sha256(key).digest()
    return key


class PIIEncryption:
    """Encrypt/decrypt PII fields using AES-256-GCM."""

    @staticmethod
    def encrypt(plaintext: str, associated_data: bytes | None = None) -> dict[str, str]:
        key = _get_key()
        aesgcm = AESGCM(key)
        nonce = os.urandom(12)
        ciphertext = aesgcm.encrypt(nonce, plaintext.encode(), associated_data or b"")
        return {
            "ciphertext": b64encode(ciphertext).decode(),
            "nonce": b64encode(nonce).decode(),
            "aad": b64encode(associated_data).decode() if associated_data else "",
        }

    @staticmethod
    def decrypt(ciphertext_b64: str, nonce_b64: str, aad_b64: str = "") -> str:
        key = _get_key()
        aesgcm = AESGCM(key)
        ciphertext = b64decode(ciphertext_b64)
        nonce = b64decode(nonce_b64)
        aad = b64decode(aad_b64) if aad_b64 else b""
        plaintext = aesgcm.decrypt(nonce, ciphertext, aad)
        return plaintext.decode()

    @staticmethod
    def encrypt_field(plaintext: str, context: str = "") -> str:
        """Encrypt and return as a single JSON string for storage."""
        import json

        result = PIIEncryption.encrypt(plaintext, associated_data=context.encode() if context else None)
        return json.dumps(result)

    @staticmethod
    def decrypt_field(encrypted_json: str) -> str:
        import json

        data = json.loads(encrypted_json)
        return PIIEncryption.decrypt(data["ciphertext"], data["nonce"], data.get("aad", ""))
