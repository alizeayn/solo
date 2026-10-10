"""Unit tests for security primitives."""

from __future__ import annotations

import logging
import os

import pytest

from app.logging_setup import RedactionFilter, redact, register_secret
from app.security import (
    SecretCipher,
    hash_password,
    hash_token,
    mask_secret,
    new_session_token,
    verify_password,
)


def test_password_hash_roundtrip():
    stored = hash_password("s3cret-password")
    assert stored.startswith("scrypt$")
    assert "s3cret-password" not in stored
    assert verify_password("s3cret-password", stored)
    assert not verify_password("wrong-password", stored)


def test_password_hash_is_salted():
    assert hash_password("same") != hash_password("same")


@pytest.mark.parametrize(
    "stored",
    ["", "garbage", "scrypt$1$2$3$nothex$nothex", "bcrypt$1$2$3$aa$bb"],
)
def test_verify_password_rejects_malformed_hashes(stored):
    assert verify_password("anything", stored) is False


def test_session_tokens_are_unique_and_hashed():
    raw1, hash1 = new_session_token()
    raw2, hash2 = new_session_token()
    assert raw1 != raw2
    assert hash1 != hash2
    assert hash1 == hash_token(raw1)
    assert raw1 not in hash1


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("", None),
        ("abcd", "****"),
        ("abcdefgh", "****efgh"),
    ],
)
def test_mask_secret(value, expected):
    assert mask_secret(value) == expected


def test_cipher_roundtrip_and_key_permissions(tmp_path):
    key_path = tmp_path / "master.key"
    cipher = SecretCipher(key_path)
    token = cipher.encrypt("sk-or-v1-abcdef123456")
    assert "abcdef" not in token
    assert cipher.decrypt(token) == "sk-or-v1-abcdef123456"
    assert key_path.exists()
    if os.name == "posix":
        assert (key_path.stat().st_mode & 0o077) == 0


def test_cipher_key_is_stable_across_instances(tmp_path):
    key_path = tmp_path / "master.key"
    token = SecretCipher(key_path).encrypt("value")
    assert SecretCipher(key_path).decrypt(token) == "value"


def test_try_decrypt_returns_none_for_corrupt_data(tmp_path):
    cipher = SecretCipher(tmp_path / "master.key")
    assert cipher.try_decrypt("not-a-valid-token") is None
    assert cipher.try_decrypt(None) is None


def test_redact_scrubs_registered_secrets_and_patterns():
    register_secret("sk-or-v1-super-secret-value")
    assert "sk-or-v1-super-secret-value" not in redact(
        "using key sk-or-v1-super-secret-value now"
    )
    for text in (
        "token=abc123def456",
        "api_key: xyz",
        "Authorization: Bearer something",
    ):
        assert "***" in redact(text)


def test_redaction_filter_rewrites_log_messages(caplog):
    register_secret("elevenlabs-super-secret")
    record = logging.LogRecord(
        "test",
        logging.INFO,
        __file__,
        1,
        "calling with elevenlabs-super-secret",
        (),
        None,
    )
    assert RedactionFilter().filter(record) is True
    assert "elevenlabs-super-secret" not in record.getMessage()
