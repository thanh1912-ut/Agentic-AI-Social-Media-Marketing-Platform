from datetime import datetime, timezone
from itertools import count
from types import SimpleNamespace

import pytest

from packages.contracts import NormalizedDocument, TableBlock, TextBlock


@pytest.fixture(autouse=True)
def fake_page_activation_for_tests(monkeypatch):
    """Keep unit/integration tests isolated from Meta while exercising activation."""
    from services.api import workspaces as workspaces_module
    from services.api.meta_client import MetaPage

    next_page_id = count(8_000_000_000)

    class FakeMetaGraphClient:
        def __init__(self, page_id, _token, _version):
            self.page_id = page_id

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def verify_page(self):
            return MetaPage(id=self.page_id, name=f"Test Page {self.page_id}", picture_url=None)

        async def verify_posts_read_access(self):
            return None

        async def list_page_posts(self, **_kwargs):
            return SimpleNamespace(posts=[], next_cursor=None)

    monkeypatch.setattr(workspaces_module, "MetaGraphClient", FakeMetaGraphClient)
    monkeypatch.setattr(workspaces_module, "encrypt_page_token", lambda token: f"test-ciphertext:{len(token)}")
    monkeypatch.setattr(workspaces_module, "_next_test_page_id", lambda: str(next(next_page_id)), raising=False)


@pytest.fixture
def normalized_document() -> NormalizedDocument:
    return NormalizedDocument(
        company_id="company-1",
        brand_id="brand-1",
        document_id="doc-1",
        source_id="source-menu",
        source_version="v1",
        source_hash="sha256:menu-v1",
        text_blocks=[
            TextBlock(
                block_id="block-1",
                heading="Thương hiệu",
                text="Bếp Mộc phục vụ món Việt gia đình tại Đà Nẵng. Giọng nói thân thiện, rõ ràng và không phóng đại công dụng.",
                locator="page=1;heading=Thương hiệu",
            ),
            TextBlock(
                block_id="block-2",
                heading="Đối tượng khách hàng",
                text="Khách hàng chính là gia đình địa phương và du khách muốn ăn món Việt nhanh, dễ hiểu về nguyên liệu.",
                locator="page=2;heading=Đối tượng khách hàng",
            ),
        ],
        table_blocks=[
            TableBlock(
                block_id="table-1",
                headers=["Sản phẩm", "Giá niêm yết"],
                rows=[["Cơm gà", "65.000đ"], ["Bún chả", "55.000đ"]],
                locator="page=3;table=1",
            )
        ],
    )


@pytest.fixture
def measured_at() -> datetime:
    return datetime(2026, 1, 15, tzinfo=timezone.utc)
