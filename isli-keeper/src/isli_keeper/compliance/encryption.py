"""AES-256-GCM encryption for PII at rest — duplicated locally to avoid cross-package imports."""

import hashlib
import json
import os
from base64 import b64decode, b64encode

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ENCRYPTION_KEY = os.getenv("PII_ENCRYPTION_KEY", "")


def _get_key() -> bytes:
    if not ENCRYPTION_KEY:
        raise RuntimeError("PII_ENCRYPTION_KEY environment variable is not set")
    key = ENCRYPTION_KEY.encode()
    if len(key) != 32:
        return hashlib.sha256(key).digest()
    return key


class PIIEncryption:
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
        result = PIIEncryption.encrypt(plaintext, associated_data=context.encode() if context else None)
        return json.dumps(result)

    @staticmethod
    def decrypt_field(encrypted_json: str) -> str:
        data = json.loads(encrypted_json)
        return PIIEncryption.decrypt(data["ciphertext"], data["nonce"], data.get("aad", ""))
