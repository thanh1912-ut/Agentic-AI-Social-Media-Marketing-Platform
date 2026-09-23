from datetime import datetime, timezone

import pytest

from packages.contracts import NormalizedDocument, TableBlock, TextBlock


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
