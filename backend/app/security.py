"""Security primitives: password hashing, session tokens, secret encryption.

Design notes
------------
* Password hashing uses ``hashlib.scrypt`` from the standard library, so there
  is no dependency on an external bcrypt build and no version-detection issues.
* Session tokens are random 256-bit strings. Only their SHA-256 digest is
  stored, so a database leak does not yield usable session cookies.
* Secrets at rest are encrypted with Fernet (AES-128-CBC + HMAC). The key is
  written to a *separate* file with ``0600`` permissions, so possession of the
  database alone is not enough to decrypt stored API keys.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

# scrypt parameters. n=2**14 keeps hashing well under 100 ms on typical hosts.
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 32
_SALT_BYTES = 16


class SecretDecryptionError(RuntimeError):
    """Raised when an encrypted secret cannot be decrypted."""


# --------------------------------------------------------------------------- #
# Password hashing
# --------------------------------------------------------------------------- #
def hash_password(password: str) -> str:
    """Hash *password* with scrypt, returning a self-describing string."""
    salt = os.urandom(_SALT_BYTES)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_DKLEN,
    )
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time verification of *password* against a stored hash."""
    try:
        scheme, n_s, r_s, p_s, salt_hex, digest_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=bytes.fromhex(salt_hex),
            n=int(n_s),
            r=int(r_s),
            p=int(p_s),
            dklen=len(bytes.fromhex(digest_hex)),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest.hex(), digest_hex)


# --------------------------------------------------------------------------- #
# Session tokens
# --------------------------------------------------------------------------- #
def new_session_token() -> tuple[str, str]:
    """Return ``(raw_token, token_hash)``. Only the hash is persisted."""
    raw = secrets.token_urlsafe(32)
    return raw, hash_token(raw)


def hash_token(raw: str) -> str:
    """SHA-256 digest (hex) of a session token."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# Secret encryption at rest
# --------------------------------------------------------------------------- #
class SecretCipher:
    """Fernet-based encrypt/decrypt with an on-disk key file."""

    def __init__(self, key_path: Path) -> None:
        self._key_path = key_path
        self._fernet = Fernet(self._load_or_create_key())

    def _load_or_create_key(self) -> bytes:
        if self._key_path.exists():
            return self._key_path.read_bytes().strip()
        key = Fernet.generate_key()
        self._key_path.parent.mkdir(parents=True, exist_ok=True)
        # Create exclusively with 0600 so the key is never world-readable.
        fd = os.open(self._key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            os.write(fd, key)
        finally:
            os.close(fd)
        return key

    def encrypt(self, plaintext: str) -> str:
        """Encrypt *plaintext*, returning a URL-safe token string."""
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")

    def decrypt(self, token: str) -> str:
        """Decrypt a token produced by :meth:`encrypt`."""
        try:
            return self._fernet.decrypt(token.encode("ascii")).decode("utf-8")
        except (InvalidToken, ValueError) as exc:  # pragma: no cover - corrupt store
            raise SecretDecryptionError("stored secret could not be decrypted") from exc

    def try_decrypt(self, token: str | None) -> str | None:
        """Best-effort decrypt; returns ``None`` instead of raising."""
        if not token:
            return None
        try:
            return self.decrypt(token)
        except SecretDecryptionError:
            return None


def mask_secret(value: str | None) -> str | None:
    """Return a display-safe masked representation of a secret.

    Only the last four characters are revealed, which is enough for a user to
    confirm which key is configured without leaking the key itself.
    """
    if not value:
        return None
    if len(value) <= 4:
        return "*" * len(value)
    return "*" * (len(value) - 4) + value[-4:]
