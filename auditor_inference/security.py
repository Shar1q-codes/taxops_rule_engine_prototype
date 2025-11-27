"""Local AES-256 encryption helpers for stored documents.

Dependencies (install if needed):
  pip install cryptography
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Tuple


def _require_crypto():
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: F401
    except ImportError as exc:  # pragma: no cover - import guard
        raise ImportError("cryptography is required for encryption. Install via: pip install cryptography") from exc


def derive_key(password: str, salt: bytes | None = None) -> Tuple[bytes, bytes]:
    """Derive a 256-bit key from password using PBKDF2-HMAC-SHA256."""
    _require_crypto()
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    salt = salt or os.urandom(16)
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=100_000)
    key = kdf.derive(password.encode("utf-8"))
    return key, salt


def encrypt_bytes(data: bytes, password: str) -> bytes:
    """Encrypt bytes with AES-GCM."""
    _require_crypto()
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    key, salt = derive_key(password)
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, data, None)
    return salt + nonce + ciphertext


def decrypt_bytes(token: bytes, password: str) -> bytes:
    """Decrypt bytes produced by encrypt_bytes."""
    _require_crypto()
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    salt, nonce, ciphertext = token[:16], token[16:28], token[28:]
    key, _ = derive_key(password, salt=salt)
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, None)


def encrypt_file(input_path: str | Path, output_path: str | Path, password: str) -> None:
    """Encrypt a file to output_path using password-derived key."""
    data = Path(input_path).read_bytes()
    token = encrypt_bytes(data, password)
    Path(output_path).write_bytes(token)


def decrypt_file(input_path: str | Path, output_path: str | Path, password: str) -> None:
    """Decrypt a file created by encrypt_file."""
    token = Path(input_path).read_bytes()
    data = decrypt_bytes(token, password)
    Path(output_path).write_bytes(data)
