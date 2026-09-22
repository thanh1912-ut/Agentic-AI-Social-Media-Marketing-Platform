"""Bounded, deterministic parsers used by the background worker.

The parser never executes document content. It returns locators and warnings
for M3; authorization remains in the API/database layer.
"""

from __future__ import annotations

import csv
import io
import mimetypes
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class ParseError(Exception):
    def __init__(self, code: str, message: str, hint: str, *, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint
        self.retryable = retryable


@dataclass(frozen=True)
class ParsedTextBlock:
    text: str
    locator: str
    heading: str | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ParsedTableBlock:
    headers: list[str]
    rows: list[list[str]]
    locator: str
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ParsedDocument:
    text_blocks: list[ParsedTextBlock] = field(default_factory=list)
    table_blocks: list[ParsedTableBlock] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


SUPPORTED_MIME_TYPES = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "text/csv": "csv",
    "text/plain": "txt",
    "image/jpeg": "image",
    "image/png": "image",
    "image/webp": "image",
}
SUPPORTED_EXTENSIONS = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".xlsx": "xlsx",
    ".csv": "csv",
    ".txt": "txt",
    ".jpg": "image",
    ".jpeg": "image",
    ".png": "image",
    ".webp": "image",
}


def infer_kind(filename: str, mime_type: str | None = None) -> str | None:
    if mime_type in SUPPORTED_MIME_TYPES:
        return SUPPORTED_MIME_TYPES[mime_type]
    return SUPPORTED_EXTENSIONS.get(Path(filename).suffix.lower())


def _decode_text(raw: bytes, filename: str) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1258", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ParseError("corrupted", f"Không đọc được tệp “{filename}”.", "Hãy xuất lại tệp ở định dạng UTF-8.")


def _parse_txt(path: Path, filename: str) -> ParsedDocument:
    text = _decode_text(path.read_bytes(), filename).strip()
    if not text:
        raise ParseError("empty_content", f"Tệp “{filename}” không có nội dung.", "Hãy chọn tệp có văn bản.")
    return ParsedDocument(text_blocks=[ParsedTextBlock(text=text, locator="text:1")], metadata={"characters": len(text)})


def _parse_csv(path: Path, filename: str) -> ParsedDocument:
    text = _decode_text(path.read_bytes(), filename)
    rows = list(csv.reader(io.StringIO(text)))
    if not rows or not any(cell.strip() for row in rows for cell in row):
        raise ParseError("empty_content", f"Tệp “{filename}” không có dữ liệu.", "Hãy chọn tệp CSV có ít nhất một dòng dữ liệu.")
    headers = [cell.strip() or f"column_{i + 1}" for i, cell in enumerate(rows[0])]
    normalized_rows = [row + [""] * (len(headers) - len(row)) for row in rows[1:]]
    normalized_rows = [row[: len(headers)] for row in normalized_rows]
    return ParsedDocument(
        table_blocks=[ParsedTableBlock(headers=headers, rows=normalized_rows, locator="csv:row=1")],
        metadata={"rows": len(normalized_rows) + 1, "columns": len(headers)},
    )


def _parse_xlsx(path: Path, filename: str) -> ParsedDocument:
    try:
        import openpyxl
    except ImportError as exc:
        raise ParseError("parser_unavailable", "Chưa cài bộ đọc XLSX.", "Liên hệ quản trị viên để bật parser XLSX.", retryable=True) from exc
    try:
        workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    except Exception as exc:
        raise ParseError("corrupted", f"Không đọc được tệp “{filename}”.", "Hãy mở và lưu lại tệp XLSX rồi tải lên lần nữa.") from exc
    tables: list[ParsedTableBlock] = []
    total_rows = 0
    for sheet in workbook.worksheets:
        values = [["" if value is None else str(value) for value in row] for row in sheet.iter_rows(values_only=True)]
        values = [row for row in values if any(cell.strip() for cell in row)]
        if not values:
            continue
        width = max(len(row) for row in values)
        values = [row + [""] * (width - len(row)) for row in values]
        tables.append(ParsedTableBlock(values[0], values[1:], f"sheet={sheet.title};row=1"))
        total_rows += len(values)
    if not tables:
        raise ParseError("empty_content", f"Tệp “{filename}” không có dữ liệu.", "Hãy chọn bảng tính có dữ liệu.")
    return ParsedDocument(table_blocks=tables, metadata={"rows": total_rows, "sheets": len(tables)})


def _parse_docx(path: Path, filename: str) -> ParsedDocument:
    try:
        from docx import Document as DocxDocument
    except ImportError as exc:
        raise ParseError("parser_unavailable", "Chưa cài bộ đọc DOCX.", "Liên hệ quản trị viên để bật parser DOCX.", retryable=True) from exc
    try:
        document = DocxDocument(path)
    except Exception as exc:
        raise ParseError("corrupted", f"Không đọc được tệp “{filename}”.", "Hãy mở và lưu lại tệp DOCX rồi tải lên lần nữa.") from exc
    blocks = [
        ParsedTextBlock(text=paragraph.text.strip(), locator=f"paragraph={index}")
        for index, paragraph in enumerate(document.paragraphs, start=1)
        if paragraph.text.strip()
    ]
    if not blocks:
        raise ParseError("empty_content", f"Tệp “{filename}” không có văn bản.", "Hãy chọn DOCX có nội dung văn bản.")
    return ParsedDocument(text_blocks=blocks, metadata={"paragraphs": len(blocks)})


def _parse_pdf(path: Path, filename: str) -> ParsedDocument:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise ParseError("parser_unavailable", "Chưa cài bộ đọc PDF.", "Liên hệ quản trị viên để bật parser PDF.", retryable=True) from exc
    try:
        reader = PdfReader(str(path))
        if reader.is_encrypted:
            raise ParseError("encrypted", f"PDF “{filename}” có mật khẩu.", "Hãy gỡ mật khẩu rồi tải tệp lên lại.")
        blocks = []
        for page_number, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            if text:
                blocks.append(ParsedTextBlock(text=text, locator=f"page={page_number}"))
    except ParseError:
        raise
    except Exception as exc:
        raise ParseError("corrupted", f"Không đọc được PDF “{filename}”.", "Hãy xuất lại PDF rồi tải lên lần nữa.") from exc
    if not blocks:
        raise ParseError("pdf_no_text_layer", f"PDF “{filename}” không có lớp văn bản.", "Hãy tải bản PDF có thể chọn/copy chữ hoặc xử lý OCR trước.")
    return ParsedDocument(text_blocks=blocks, metadata={"pages": len(reader.pages), "characters": sum(len(b.text) for b in blocks)})


def _parse_image(path: Path, filename: str) -> ParsedDocument:
    try:
        from PIL import Image
        with Image.open(path) as image:
            metadata = {"width": image.width, "height": image.height, "format": image.format, "images": 1}
    except Exception as exc:
        raise ParseError("corrupted", f"Không đọc được ảnh “{filename}”.", "Hãy tải lên ảnh PNG, JPG hoặc WEBP hợp lệ.") from exc
    return ParsedDocument(metadata=metadata, warnings=["image_not_text_extracted"])


def parse_document(path: Path, *, kind: str, mime_type: str, filename: str) -> ParsedDocument:
    parser = {
        "txt": _parse_txt,
        "csv": _parse_csv,
        "xlsx": _parse_xlsx,
        "docx": _parse_docx,
        "pdf": _parse_pdf,
        "image": _parse_image,
    }.get(kind)
    if parser is None:
        guessed = infer_kind(filename, mime_type) or mimetypes.guess_type(filename)[0] or "unknown"
        raise ParseError("unsupported_type", f"Định dạng “{guessed}” chưa được hỗ trợ.", "Chỉ nhận PDF, DOCX, XLSX, CSV, TXT và ảnh.")
    return parser(path, filename)

