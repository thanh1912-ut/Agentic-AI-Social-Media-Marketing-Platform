"""Encryption for Page tokens entered through the authenticated UI."""

from __future__ import annotations

from hashlib import sha256

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from .config import settings


class TokenEncryptionUnavailable(RuntimeError):
    pass


def _fernet() -> MultiFernet:
    keys = [key for key in (settings.meta_token_encryption_key, settings.meta_token_encryption_key_previous) if key]
    if not keys:
        raise TokenEncryptionUnavailable("META_TOKEN_ENCRYPTION_KEY is not configured")
    try:
        return MultiFernet([Fernet(key.encode("ascii")) for key in keys])
    except (ValueError, UnicodeEncodeError) as error:
        raise TokenEncryptionUnavailable("META_TOKEN_ENCRYPTION_KEY is invalid") from error


def encrypt_page_token(token: str) -> str:
    if not token or len(token) > 4096 or any(char in token for char in "\r\n\x00"):
        raise ValueError("invalid Page token")
    fernet = _fernet()
    return fernet.encrypt(token.encode("utf-8")).decode("ascii")


def decrypt_page_token(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeEncodeError, UnicodeDecodeError) as error:
        raise TokenEncryptionUnavailable("Page token cannot be decrypted with configured keys") from error


def token_fingerprint(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()
