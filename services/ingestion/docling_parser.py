"""Launch the pinned Docling engine without exposing application secrets."""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

from .parsers import ParseError, ParsedDocument, ParsedTableBlock, ParsedTextBlock


def parse_with_docling(path: Path, *, kind: str, filename: str) -> ParsedDocument:
    from . import parsers

    limits = {
        "text": parsers.MAX_PARSED_TEXT_CHARACTERS,
        "rows": parsers.MAX_TABLE_ROWS,
        "columns": parsers.MAX_TABLE_COLUMNS,
        "cells": parsers.MAX_TABLE_CELLS,
        "pages": parsers.MAX_PDF_PAGES,
        "archive_bytes": parsers.MAX_ARCHIVE_UNCOMPRESSED_BYTES,
        "archive_entries": parsers.MAX_ARCHIVE_ENTRIES,
    }
    with tempfile.TemporaryDirectory(prefix="docling-result-") as directory:
        result_path = Path(directory) / "result.json"
        environment = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "LANG": os.environ.get("LANG", "C.UTF-8"),
            "LC_ALL": os.environ.get("LC_ALL", "C.UTF-8"),
            "OMP_NUM_THREADS": "4",
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
        }
        artifact_path = os.environ.get("DOCLING_ARTIFACTS_PATH", "").strip()
        if artifact_path:
            environment["DOCLING_ARTIFACTS_PATH"] = artifact_path
        try:
            with tempfile.TemporaryFile() as child_stderr:
                child = subprocess.Popen(
                    [sys.executable, "-m", "services.ingestion.docling_runner", str(path.resolve()), kind, filename, str(result_path), json.dumps(limits)],
                    cwd=Path(__file__).resolve().parents[2],
                    env=environment,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=child_stderr,
                    start_new_session=True,
                )
                try:
                    return_code = child.wait(timeout=parsers.MAX_DOCUMENT_CONVERSION_SECONDS)
                except subprocess.TimeoutExpired as exc:
                    try:
                        os.killpg(child.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    child.wait()
                    raise ParseError("parser_timeout", f"Đọc tệp “{filename}” quá thời gian cho phép.", "Chia nhỏ tài liệu rồi tải lên lại.") from exc
                stderr_size = child_stderr.tell()
                if stderr_size > 256 * 1024:
                    raise ParseError("parser_output_invalid", "Docling tạo lượng log vượt giới hạn an toàn.", "Liên hệ quản trị viên để kiểm tra worker parser.")
                child_stderr.seek(max(0, stderr_size - 4096))
                stderr_tail = child_stderr.read(4096)
        except subprocess.TimeoutExpired as exc:
            raise ParseError("parser_timeout", f"Đọc tệp “{filename}” quá thời gian cho phép.", "Chia nhỏ tài liệu rồi tải lên lại.") from exc
        except OSError as exc:
            raise ParseError("parser_unavailable", "Worker chưa cài Docling.", "Cài đúng bộ dependency Docling cho worker ingestion.", retryable=True) from exc
        detail = stderr_tail.decode("utf-8", "replace") if stderr_tail else ""
        if return_code not in {0, 1}:
            raise ParseError("parser_output_invalid", "Worker Docling kết thúc với mã thực thi không hợp lệ.", "Kiểm tra cài đặt worker ingestion.")
        if not result_path.exists():
            if kind == "pdf" and ("artifact" in detail.casefold() or "model" in detail.casefold()):
                raise ParseError("parser_model_unavailable", "Worker chưa có model Docling cần thiết.", "Quản trị viên cần tải trước model vào thư mục DOCLING_ARTIFACTS_PATH.", retryable=True)
            raise ParseError("parser_unavailable", "Worker không chạy được Docling.", "Kiểm tra dependency Docling và worker ingestion.", retryable=True)
        if result_path.stat().st_size > 256 * 1024 * 1024:
            raise ParseError("parser_output_invalid", "Docling không tạo được kết quả an toàn.", "Thử xử lý lại; nếu lỗi lặp lại hãy gửi mã job cho hỗ trợ.")
        try:
            payload = json.loads(result_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            if "artifact" in detail.casefold() or "model" in detail.casefold():
                raise ParseError("parser_model_unavailable", "Worker chưa có model Docling cần thiết.", "Quản trị viên cần tải trước model vào thư mục DOCLING_ARTIFACTS_PATH.", retryable=True) from exc
            raise ParseError("parser_output_invalid", "Kết quả Docling không hợp lệ.", "Thử xử lý lại; nếu lỗi lặp lại hãy gửi mã job cho hỗ trợ.") from exc
        if not payload.get("ok"):
            error = payload.get("error") or {}
            raise ParseError(
                str(error.get("code") or "parser_unavailable"),
                str(error.get("message") or f"Không đọc được tệp “{filename}”."),
                str(error.get("hint") or "Kiểm tra định dạng và kích thước của tệp."),
                retryable=bool(error.get("retryable", False)),
            )
        raw = payload["document"]
        return ParsedDocument(
            text_blocks=[ParsedTextBlock(**item) for item in raw.get("text_blocks", [])],
            table_blocks=[ParsedTableBlock(**item) for item in raw.get("table_blocks", [])],
            metadata=raw.get("metadata", {}),
            warnings=raw.get("warnings", []),
        )
