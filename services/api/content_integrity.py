"""Canonical fingerprints for immutable post content and its attached media."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def content_sha256(content: dict[str, Any]) -> str:
    canonical = json.dumps(
        content, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()
