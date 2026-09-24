"""Storage keys must not escape local or object storage namespaces."""

from __future__ import annotations

import asyncio

import pytest

from services.api.storage import LocalObjectStorage


@pytest.mark.parametrize(
    "key",
    [
        "../outside.txt",
        "tenant/hash/../../outside.txt",
        "/tmp/outside.txt",
        "C:/tmp/outside.txt",
        r"tenant\..\outside.txt",
        "tenant//empty-segment.txt",
    ],
)
def test_local_storage_rejects_unsafe_keys_without_writing_outside(tmp_path, key: str) -> None:
    root = tmp_path / "objects"
    storage = LocalObjectStorage(root)

    with pytest.raises(ValueError, match="invalid storage key"):
        asyncio.run(storage.put(key, b"attacker-controlled"))

    assert not (tmp_path / "outside.txt").exists()


def test_local_storage_writes_and_resolves_valid_nested_keys(tmp_path) -> None:
    storage = LocalObjectStorage(tmp_path / "objects")
    key = "workspace-id/source-hash/document-id"

    asyncio.run(storage.put(key, b"stored safely"))

    stored_path = storage.path(key)
    assert stored_path.read_bytes() == b"stored safely"
    assert (tmp_path / "objects") in stored_path.parents
