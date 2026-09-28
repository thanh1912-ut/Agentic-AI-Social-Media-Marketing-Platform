"""Bounded subprocess adapter for the pinned facebook-cli Tier 0 runner."""

from __future__ import annotations

import asyncio
import json
import os
import signal
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Awaitable, Callable

from .web_crawler import CrawlError, canonicalize_url


ENGINE_VERSION = "facebook-cli@v0.3.0+8e251abf0bc6fd28acca9b9fa1cafbd07ccae39"
MAX_RUN_SECONDS = 300
MAX_STDOUT_BYTES = 16 * 1024 * 1024
MAX_STDERR_BYTES = 256 * 1024

FAILURE_CODES = {
    "page_identity_unverified": "Liên kết này chưa được xác minh là Fanpage.",
    "invalid_request": "Yêu cầu gửi tới facebook-cli runner không hợp lệ.",
    "login_required": "Facebook trả trang đăng nhập cho nguồn này.",
    "access_denied": "Facebook từ chối đọc nguồn công khai này.",
    "challenge": "Facebook trả bước kiểm tra bảo mật thay cho nội dung Page.",
    "rate_limited": "Facebook giới hạn yêu cầu; lượt này sẽ chờ trước khi thử lại.",
    "not_found": "Không tìm thấy Fanpage hoặc bài viết công khai.",
    "unsupported": "facebook-cli không hỗ trợ dạng liên kết này.",
    "network_error": "Không kết nối hoặc đọc được Facebook.",
    "response_too_large": "Facebook trả response vượt giới hạn an toàn.",
    "request_budget_reached": "Đã dùng hết ngân sách request của lượt crawl.",
    "collector_error": "facebook-cli không đọc được dữ liệu nguồn.",
}


@dataclass(frozen=True, slots=True)
class FacebookCliResult:
    page: dict[str, Any]
    posts: list[dict[str, Any]]
    coverage: dict[str, Any]
    engine_version: str


async def collect_public_facebook_page(
    page_url: str,
    *,
    run_id: str,
    post_limit: int,
    known_post_urls: list[str] | None = None,
    runner_path: str | Path | None = None,
    heartbeat: Callable[[], Awaitable[None]] | None = None,
) -> FacebookCliResult:
    executable = Path(runner_path or os.getenv("FACEBOOK_CLI_RUNNER_PATH", "")).expanduser()
    if not executable.is_absolute() or not executable.is_file() or not os.access(executable, os.X_OK):
        raise CrawlError("engine_unavailable", "facebook-cli runner chưa được build hoặc chưa cấu hình đường dẫn.")
    if not 1 <= post_limit <= 100:
        raise CrawlError("invalid_collection_settings", "Giới hạn bài phải trong khoảng 1 đến 100.")
    try:
        page_url = canonicalize_url(page_url)
        known = [canonicalize_url(value) for value in (known_post_urls or [])[:100]]
    except CrawlError:
        raise

    request = {
        "run_id": run_id,
        "page_url": page_url,
        "post_limit": post_limit,
        "known_post_urls": known,
        "max_http_requests": 20,
    }
    payload = json.dumps(request, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    env = {
        "PATH": f"{executable.parent}:/usr/bin:/bin:/usr/sbin:/sbin",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "TZ": "UTC",
    }

    try:
        process = await asyncio.create_subprocess_exec(
            str(executable),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            start_new_session=True,
        )
    except OSError as error:
        raise CrawlError("engine_unavailable", "Không khởi chạy được facebook-cli runner.") from error

    assert process.stdin is not None and process.stdout is not None and process.stderr is not None
    try:
        process.stdin.write(payload)
        await process.stdin.drain()
        process.stdin.close()
    except (BrokenPipeError, ConnectionResetError) as error:
        await _stop_process_group(process)
        raise CrawlError("runner_protocol_error", "facebook-cli runner dừng trước khi nhận được yêu cầu.") from error
    stdout_task = asyncio.create_task(_read_limited(process.stdout, MAX_STDOUT_BYTES, process))
    stderr_task = asyncio.create_task(_read_limited(process.stderr, MAX_STDERR_BYTES, process))
    wait_task = asyncio.create_task(process.wait())
    deadline = asyncio.get_running_loop().time() + MAX_RUN_SECONDS
    try:
        while not wait_task.done():
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise asyncio.TimeoutError
            done, _ = await asyncio.wait({wait_task}, timeout=min(5.0, remaining))
            if done:
                break
            if heartbeat is not None:
                try:
                    await heartbeat()
                except Exception as error:
                    await _stop_process_group(process)
                    await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
                    raise CrawlError(
                        "collector_coordination_lost",
                        "Worker mất quyền điều phối hoặc lease; runner đã được dừng.",
                    ) from error
        await wait_task
        stdout, stdout_overflow = await stdout_task
        _, stderr_overflow = await stderr_task
    except asyncio.TimeoutError as error:
        await _stop_process_group(process)
        for task in (stdout_task, stderr_task):
            if not task.done():
                task.cancel()
        raise CrawlError("runner_timeout", "facebook-cli vượt thời gian tối đa của một lượt.") from error
    except asyncio.CancelledError:
        await _stop_process_group(process)
        raise
    if stdout_overflow or stderr_overflow:
        raise CrawlError("runner_output_too_large", "facebook-cli vượt giới hạn output của một lượt.")

    page: dict[str, Any] | None = None
    posts: list[dict[str, Any]] = []
    summary: dict[str, Any] | None = None
    failure: dict[str, Any] | None = None
    try:
        for raw_line in stdout.splitlines():
            if not raw_line:
                continue
            row = json.loads(raw_line)
            if row.get("schema_version") != 1:
                raise ValueError("unsupported runner schema")
            kind = row.get("type")
            if kind == "page" and isinstance(row.get("page"), dict):
                page = row["page"]
            elif kind == "post" and isinstance(row.get("post"), dict):
                posts.append(row["post"])
            elif kind == "summary":
                summary = row
            elif kind == "error":
                failure = row
            else:
                raise ValueError("unexpected runner record")
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, AttributeError) as error:
        raise CrawlError("parser_error", "Không đọc được cấu trúc output của facebook-cli.") from error

    if failure is not None:
        code = str(failure.get("failure_kind") or "collector_error")
        raise CrawlError(code, FAILURE_CODES.get(code, "facebook-cli từ chối hoặc không đọc được nguồn."),
                         retryable=code in {"rate_limited", "network_error"})
    if process.returncode != 0 or page is None or summary is None:
        raise CrawlError("parser_error", "facebook-cli kết thúc mà không trả đủ Page và trạng thái lượt crawl.")

    unique: dict[str, dict[str, Any]] = {}
    for post in posts:
        try:
            post_url = canonicalize_url(str(post.get("url", "")))
        except CrawlError:
            continue
        post["url"] = post_url
        unique[post_url] = post
    posts = list(unique.values())[:post_limit]
    summary_version = str(summary.get("engine_version") or ENGINE_VERSION)
    if summary_version != ENGINE_VERSION:
        raise CrawlError("engine_version_mismatch", "Phiên bản facebook-cli runner không khớp phiên bản đã ghim.")

    dates: list[datetime] = []
    for post in posts:
        value = post.get("published_at")
        if not isinstance(value, str):
            continue
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            post["published_at"] = None
            continue
        if parsed.tzinfo is None:
            post["published_at"] = None
            continue
        dates.append(parsed)
    fields = ("text", "published_at", "reactions", "comments", "shares", "views")
    missing_fields = [
        field for field in fields
        if not posts or all(
            (post.get("text") == "" if field == "text" else
             post.get("published_at") is None if field == "published_at" else
             (post.get("counts") or {}).get(field) is None)
            for post in posts
        )
    ]
    coverage = {
        "coverage": "partial",
        "coverage_reason": "tier0_signed_out_feed_is_not_paginated",
        "engine": "facebook-cli",
        "engine_version": summary_version,
        "access_tier": 0,
        "requested_limit": post_limit,
        "returned_posts": len(posts),
        "history_complete": False,
        "posts_truncated": bool(summary.get("posts_truncated")),
        "http_requests": int(summary.get("http_requests") or 0),
        "request_budget": 20,
        "stop_reason": str(summary.get("stop_reason") or "unknown"),
        "oldest_post_at": min(dates).isoformat() if dates else None,
        "missing_fields": missing_fields,
        "page_name": page.get("name"),
        "page_id": page.get("id"),
        "page_kind": page.get("kind"),
    }
    return FacebookCliResult(page=page, posts=posts, coverage=coverage, engine_version=summary_version)


async def _read_limited(
    stream: asyncio.StreamReader, limit: int, process: asyncio.subprocess.Process,
) -> tuple[bytes, bool]:
    parts: list[bytes] = []
    size = 0
    while True:
        chunk = await stream.read(min(64 * 1024, limit + 1 - size))
        if not chunk:
            return b"".join(parts), False
        size += len(chunk)
        if size > limit:
            await _stop_process_group(process)
            return b"", True
        parts.append(chunk)


async def _stop_process_group(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        process.terminate()
    try:
        await asyncio.wait_for(process.wait(), timeout=2)
    except asyncio.TimeoutError:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            process.kill()
        await process.wait()
