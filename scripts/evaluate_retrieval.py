#!/usr/bin/env python3
"""Run a small local multilingual E5 retrieval/no-answer calibration set."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from packages.contracts import NormalizedDocument, TextBlock
from services.agents.knowledge import InMemoryKnowledgeIndex
from services.agents.providers.fastembed import FastEmbedLocalEmbeddingProvider


COMPANY_ID = "retrieval-eval-company"
BRAND_ID = "retrieval-eval-brand"
PASSAGES = (
    ("chicken", "Cơm gà xối mỡ giá 55.000 đồng, phục vụ tại quán từ 10 giờ đến 21 giờ."),
    ("ingredients", "Món cơm gà gồm gạo thơm, thịt gà ta, nước mắm, hành phi và rau ăn kèm."),
    ("voice", "Thương hiệu thân thiện, gần gũi, nói chuyện tự nhiên với khách hàng."),
    ("promotion", "Ưu đãi cuối tuần giảm 15 phần trăm cho khách đặt món trực tuyến."),
    ("hours", "Nhà hàng mở cửa hằng ngày từ 10 giờ sáng đến 9 giờ tối."),
    (
        "address",
        "Địa chỉ cửa hàng tại số 12 đường Nguyễn Huệ, Quận 1, Thành phố Hồ Chí Minh.",
    ),
)
POSITIVE_QUERIES = (
    ("chicken", "Quán bán cơm gà bao nhiêu tiền?"),
    ("ingredients", "Trong món cơm gà có những nguyên liệu nào?"),
    ("voice", "Thương hiệu nên giao tiếp với khách theo phong cách nào?"),
    ("promotion", "Khách đặt món online dịp cuối tuần được ưu đãi gì?"),
    ("hours", "Nhà hàng mở cửa vào thời gian nào?"),
    ("address", "Cửa hàng nằm ở đâu tại Thành phố Hồ Chí Minh?"),
)
NO_ANSWER_QUERIES = (
    "Hồ sơ kê khai thuế doanh nghiệp quý ba",
    "Thời tiết Đà Lạt cuối tuần",
    "Bác sĩ nha khoa chữa sâu răng",
    "Hướng dẫn nộp hồ sơ visa du học",
    "Kết quả bóng đá đội tuyển quốc gia",
    "lãi suất vay ngân hàng mua nhà",
    "cài Linux trên máy tính cá nhân",
    "bảo dưỡng xe máy định kỳ",
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path(".data/embedding-models"),
        help="Local FastEmbed model cache (default: .data/embedding-models)",
    )
    parser.add_argument(
        "--local-files-only",
        action="store_true",
        help="Fail instead of downloading pinned public model weights when cache is empty",
    )
    args = parser.parse_args()

    embedder = FastEmbedLocalEmbeddingProvider(
        cache_dir=args.cache_dir,
        local_files_only=args.local_files_only,
    )
    index = InMemoryKnowledgeIndex(max_candidates=20, max_context=6)
    for position, (source_id, passage) in enumerate(PASSAGES):
        index.upsert(
            NormalizedDocument(
                company_id=COMPANY_ID,
                brand_id=BRAND_ID,
                document_id=source_id,
                source_id=source_id,
                source_version="synthetic-v1",
                source_hash=f"synthetic:{source_id}",
                text_blocks=[
                    TextBlock(
                        block_id=source_id,
                        heading=None,
                        text=passage,
                        locator=f"paragraph={position + 1}",
                    )
                ],
            ),
            embedder=embedder,
        )

    positive_results = []
    for expected_source, query in POSITIVE_QUERIES:
        retrieved = index.retrieve(
            query,
            company_id=COMPANY_ID,
            brand_id=BRAND_ID,
            embedder=embedder,
        )
        rank = next(
            (position for position, item in enumerate(retrieved, start=1) if item.source_id == expected_source),
            None,
        )
        positive_results.append(
            {"query": query, "expected_source": expected_source, "rank": rank}
        )

    no_answer_results = []
    for query in NO_ANSWER_QUERIES:
        retrieved = index.retrieve(
            query,
            company_id=COMPANY_ID,
            brand_id=BRAND_ID,
            embedder=embedder,
        )
        no_answer_results.append(
            {"query": query, "returned_sources": [item.source_id for item in retrieved]}
        )

    payload = {
        "model": embedder.model_name,
        "positive_queries": positive_results,
        "positive_hit_at_1": sum(item["rank"] == 1 for item in positive_results),
        "positive_count": len(positive_results),
        "no_answer_queries": no_answer_results,
        "no_answer_false_contexts": sum(bool(item["returned_sources"]) for item in no_answer_results),
        "no_answer_count": len(no_answer_results),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
