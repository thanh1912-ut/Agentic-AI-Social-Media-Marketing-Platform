from __future__ import annotations

from pathlib import Path

import pytest

from services.agents.providers import fastembed
from services.agents.providers.errors import ProviderOutputError


class FakeTextEmbedding:
    def __init__(self, result=None):
        self.inputs: list[list[str]] = []
        self.result = result

    def embed(self, texts, *, batch_size):
        self.inputs.append(list(texts))
        if self.result is not None:
            return iter(self.result)
        return iter([[1.0, *([0.0] * (fastembed.LOCAL_E5_DIMENSIONS - 1))] for _ in texts])


def make_provider(monkeypatch, model):
    monkeypatch.setattr(fastembed, "_load_model", lambda *args: model)
    monkeypatch.setattr(fastembed, "version", lambda _: "0.8.1")
    return fastembed.FastEmbedLocalEmbeddingProvider(cache_dir=Path("/tmp/models"))


def test_local_e5_uses_separate_query_and_passage_prefixes(monkeypatch):
    model = FakeTextEmbedding()
    provider = make_provider(monkeypatch, model)

    passages = provider.embed(["Thương hiệu bán cà phê rang xay."])
    query = provider.embed_query("Cà phê rang xay")

    assert model.inputs == [
        ["passage: Thương hiệu bán cà phê rang xay."],
        ["query: Cà phê rang xay"],
    ]
    assert len(passages) == 1 and len(passages[0]) == fastembed.LOCAL_E5_DIMENSIONS
    assert len(query) == fastembed.LOCAL_E5_DIMENSIONS
    assert provider.model_name.startswith(f"{fastembed.LOCAL_E5_MODEL}@{fastembed.LOCAL_E5_REVISION}:")


@pytest.mark.parametrize(
    "result",
    [
        [],
        [[1.0]],
        [[float("nan")] * fastembed.LOCAL_E5_DIMENSIONS],
    ],
)
def test_local_e5_rejects_invalid_model_vectors(monkeypatch, result):
    provider = make_provider(monkeypatch, FakeTextEmbedding(result))

    with pytest.raises(ProviderOutputError, match="invalid vector|mismatched batch"):
        provider.embed(["Một đoạn tiếng Việt."])
