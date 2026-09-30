"""Local, purpose-separated encryption for unreviewed comment candidates.

These candidates remain personal-data processing inputs. Neither masking nor
encryption makes them anonymous or authorizes sending them to an AI provider.
"""

from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass, field

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from services.api.config import settings
from .privacy import redact_facebook_text


COMMENT_REDACTOR_VERSION = "comment-contact-mentions-v1"
MAX_COMMENT_CHARACTERS = 20_000
_MENTION = re.compile(r"(?<![\w@])@[\w.]{1,100}", re.UNICODE)
_LABELLED_NAME = re.compile(r"\b(?:họ và tên|họ tên|tên cá nhân)\s*[:：]\s*[^\n;.!?]{2,120}", re.IGNORECASE)


class CommentQuarantineUnavailable(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class CommentCandidate:
    text: str = field(repr=False)
    metadata: dict[str, object]


def screen_comment_candidate(message: str) -> CommentCandidate:
    if not isinstance(message, str) or len(message) > MAX_COMMENT_CHARACTERS:
        raise ValueError("invalid bounded comment candidate")
    candidate, metadata = redact_facebook_text(message)
    candidate, mentions = _MENTION.subn("[đã che tên tài khoản]", candidate)
    candidate, names = _LABELLED_NAME.subn("[đã che tên cá nhân]", candidate)
    return CommentCandidate(candidate, {
        "redactor_version": COMMENT_REDACTOR_VERSION,
        "status": "privacy_hold",
        "redacted_fields": {**metadata["redacted_fields"], "person_handle": mentions, "labelled_name": names},
        "limitations": ["unlabelled_names_not_detected", "not_anonymization", "review_required"],
    })


def _cipher() -> MultiFernet:
    # Derive separate keys; a quarantined body cannot be decrypted by the Page
    # token cipher. Existing primary/previous-key rotation remains supported.
    configured = (settings.meta_token_encryption_key, settings.meta_token_encryption_key_previous)
    keys = []
    try:
        for value in configured:
            if not value:
                continue
            material = base64.b64decode(value.encode("ascii"), altchars=b"-_", validate=True)
            if len(material) != 32:
                raise ValueError("invalid key size")
            derived = HKDF(algorithm=hashes.SHA256(), length=32, salt=None,
                           info=b"agentic/research/comment-quarantine/v1").derive(material)
            keys.append(Fernet(base64.urlsafe_b64encode(derived)))
        if not keys:
            raise ValueError("key not configured")
        return MultiFernet(keys)
    except (ValueError, UnicodeEncodeError) as error:
        raise CommentQuarantineUnavailable("Comment quarantine encryption is unavailable") from error


def encrypt_candidate(text: str, *, binding: dict[str, str]) -> str:
    if len(text) > MAX_COMMENT_CHARACTERS or not binding or any(not isinstance(v, str) for v in binding.values()):
        raise ValueError("invalid bounded comment envelope")
    envelope = json.dumps({"schema": 1, "binding": binding, "candidate": text}, ensure_ascii=False,
                          sort_keys=True, separators=(",", ":")).encode("utf-8")
    return _cipher().encrypt(envelope).decode("ascii")


def decrypt_candidate(ciphertext: str, *, binding: dict[str, str]) -> str:
    """Internal review primitive; expiry/access checks belong to the caller."""
    if len(ciphertext) > 200_000:
        raise CommentQuarantineUnavailable("Comment quarantine envelope is invalid")
    try:
        envelope = json.loads(_cipher().decrypt(ciphertext.encode("ascii")))
        if envelope.get("schema") != 1 or envelope.get("binding") != binding:
            raise ValueError("binding mismatch")
        text = envelope.get("candidate")
        if not isinstance(text, str) or len(text) > MAX_COMMENT_CHARACTERS:
            raise ValueError("invalid candidate")
        return text
    except (InvalidToken, ValueError, UnicodeError, AttributeError) as error:
        raise CommentQuarantineUnavailable("Comment quarantine envelope is invalid") from error
