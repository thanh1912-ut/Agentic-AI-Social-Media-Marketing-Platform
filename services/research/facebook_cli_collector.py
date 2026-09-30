"""Bounded subprocess adapter for the pinned facebook-cli Tier 0 runner."""

from __future__ import annotations

import asyncio
import json
import os
import re
import signal
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Awaitable, Callable
from urllib.parse import urlsplit, urlunsplit

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
    "group_not_public": "Không xác minh được nhóm Facebook là công khai.",
}


@dataclass(frozen=True, slots=True)
class FacebookCliResult:
    page: dict[str, Any]
    posts: list[dict[str, Any]]
    coverage: dict[str, Any]
    engine_version: str


@dataclass(frozen=True, slots=True)
class FacebookCliGroupResult:
    group: dict[str, Any]
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
    include_comments: bool = False,
) -> FacebookCliResult:
    return await _collect_public_facebook_source(
        source_type="competitor_facebook_page", source_url=page_url,
        run_id=run_id, post_limit=post_limit, known_post_urls=known_post_urls,
        runner_path=runner_path, heartbeat=heartbeat, include_comments=include_comments,
    )


async def collect_public_facebook_group(
    group_url: str,
    *,
    run_id: str,
    runner_path: str | Path | None = None,
    heartbeat: Callable[[], Awaitable[None]] | None = None,
) -> FacebookCliGroupResult:
    return await _collect_public_facebook_source(
        source_type="facebook_group", source_url=group_url,
        run_id=run_id, post_limit=0, known_post_urls=[],
        runner_path=runner_path, heartbeat=heartbeat,
    )


async def _collect_public_facebook_source(
    *,
    source_type: str,
    source_url: str,
    run_id: str,
    post_limit: int,
    known_post_urls: list[str] | None,
    runner_path: str | Path | None,
    heartbeat: Callable[[], Awaitable[None]] | None,
    include_comments: bool = False,
) -> FacebookCliResult | FacebookCliGroupResult:
    executable = Path(runner_path or os.getenv("FACEBOOK_CLI_RUNNER_PATH", "")).expanduser()
    if not executable.is_absolute() or not executable.is_file() or not os.access(executable, os.X_OK):
        raise CrawlError("engine_unavailable", "facebook-cli runner chưa được build hoặc chưa cấu hình đường dẫn.")
    is_group = source_type == "facebook_group"
    if source_type not in {"competitor_facebook_page", "facebook_group"}:
        raise CrawlError("invalid_collection_settings", "Loại nguồn facebook-cli không được hỗ trợ.")
    if (not is_group and not 1 <= post_limit <= 100) or (is_group and post_limit != 0):
        raise CrawlError("invalid_collection_settings", "Giới hạn bài phải trong khoảng 1 đến 100.")
    try:
        source_url = _canonicalize_group_url(source_url) if is_group else canonicalize_url(source_url)
        known = [] if is_group else [canonicalize_url(value) for value in (known_post_urls or [])[:100]]
    except CrawlError:
        raise

    request = {
        "source_type": source_type,
        "run_id": run_id,
        "page_url": source_url,
        "post_limit": post_limit,
        "known_post_urls": known,
        "max_http_requests": 20,
        "include_comments": include_comments and not is_group,
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

    metadata: dict[str, Any] | None = None
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
            expected_record = "group" if is_group else "page"
            if kind == expected_record and isinstance(row.get(expected_record), dict):
                metadata = row[expected_record]
            elif kind == "post" and isinstance(row.get("post"), dict):
                if is_group:
                    raise ValueError("Tier 0 group metadata run returned discussion content")
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
    if process.returncode != 0 or metadata is None or summary is None:
        entity_label = "nhóm" if is_group else "Page"
        raise CrawlError("parser_error", f"facebook-cli kết thúc mà không trả đủ metadata {entity_label} và trạng thái lượt crawl.")

    if is_group:
        group = {
            "id": metadata.get("id"),
            "name": metadata.get("name"),
            "url": metadata.get("url"),
            "privacy": metadata.get("privacy"),
            "public": metadata.get("public"),
            "provenance": metadata.get("provenance") if isinstance(metadata.get("provenance"), dict) else {},
        }
        if (
            not isinstance(group["id"], str) or not group["id"]
            or not isinstance(group["name"], str) or not group["name"].strip()
            or not isinstance(group["url"], str) or group["public"] is not True
            or not isinstance(group["privacy"], str) or not group["privacy"].casefold().startswith("public")
        ):
            raise CrawlError("group_not_public", FAILURE_CODES["group_not_public"])
        try:
            group["url"] = _canonicalize_group_url(group["url"])
        except CrawlError as error:
            raise CrawlError("parser_error", "facebook-cli trả URL metadata nhóm ngoài định dạng cho phép.") from error
        summary_version = str(summary.get("engine_version") or ENGINE_VERSION)
        if summary_version != ENGINE_VERSION:
            raise CrawlError("engine_version_mismatch", "Phiên bản facebook-cli runner không khớp phiên bản đã ghim.")
        coverage = {
            "coverage": "partial",
            "coverage_reason": "tier0_group_shell_only",
            "engine": "facebook-cli",
            "engine_version": summary_version,
            "access_tier": 0,
            "history_complete": False,
            "discussion_posts_collected": False,
            "returned_posts": 0,
            "http_requests": int(summary.get("http_requests") or 0),
            "stop_reason": "group_discussions_not_requested_tier0",
            "group_id": group["id"],
            "group_name": group["name"],
            "group_privacy": group["privacy"],
            "missing_fields": ["discussion_posts", "comments"],
        }
        return FacebookCliGroupResult(group=group, coverage=coverage, engine_version=summary_version)

    total_comments = 0
    unique: dict[str, dict[str, Any]] = {}
    for post in posts:
        try:
            post_url = canonicalize_url(str(post.get("url", "")))
        except CrawlError:
            continue
        post["url"] = post_url
        records = post.pop("comment_records", [])
        if include_comments:
            if post.get("author_id") != metadata.get("id") and post.get("delegate_page_id") != metadata.get("id"):
                raise CrawlError("parser_error", "Bình luận không gắn với bài của Page đã xác minh.")
            post["comment_records"] = _safe_comments(records)
            total_comments += len(post["comment_records"])
            if total_comments > 500:
                raise CrawlError("parser_error", "Bình luận vượt ngân sách batch.")
        post["comment_coverage"] = safe_comment_coverage(post.get("comment_coverage"))
        if include_comments:
            received = len(post["comment_records"])
            if (post["comment_coverage"]["returned_count"] != received
                    or (received and post["comment_coverage"]["mode"] != "tier0_embedded")):
                raise CrawlError("parser_error", "Độ đầy đủ bình luận không khớp dữ liệu runner trả về.")
        if not include_comments:
            post["comment_coverage"] = safe_comment_coverage(None)
        post["reaction_breakdown"] = safe_reaction_breakdown(post.get("reaction_breakdown"))
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
        "page_name": metadata.get("name"),
        "page_id": metadata.get("id"),
        "page_kind": metadata.get("kind"),
        "comment_records_received": sum(len(p.get("comment_records", [])) for p in posts),
        "comments_requested": include_comments,
        "comment_history_complete": False,
    }
    return FacebookCliResult(page=metadata, posts=posts, coverage=coverage, engine_version=summary_version)


def _canonicalize_group_url(value: str) -> str:
    canonical = canonicalize_url(value)
    parsed = urlsplit(canonical)
    allowed_hosts = {"facebook.com", "www.facebook.com", "m.facebook.com"}
    if (
        parsed.scheme != "https" or (parsed.hostname or "").casefold() not in allowed_hosts
        or parsed.query or parsed.fragment or parsed.username or parsed.password
    ):
        raise CrawlError("invalid_facebook_group_url", "Nguồn nhóm cần là link HTTPS facebook.com/groups/{id-hoặc-slug}.")
    segments = [segment for segment in parsed.path.split("/") if segment]
    if len(segments) != 2 or segments[0].casefold() != "groups" or not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", segments[1]):
        raise CrawlError("invalid_facebook_group_url", "Chỉ nhận trang chủ công khai dạng facebook.com/groups/{id-hoặc-slug}.")
    return urlunsplit(("https", parsed.netloc, f"/groups/{segments[1]}", "", ""))


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


REACTION_TYPES = {"LIKE", "LOVE", "CARE", "HAHA", "WOW", "SAD", "ANGRY"}


def safe_reaction_breakdown(value: object) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {key: count for key, count in value.items()
            if key in REACTION_TYPES and type(count) is int and 0 <= count <= 2**63 - 1}


def safe_comment_coverage(value: object) -> dict[str, Any]:
    value = value if isinstance(value, dict) else {}
    mode = value.get("mode") if value.get("mode") in {"tier0_embedded", "not_requested", "unavailable"} else "not_requested"
    received = value.get("returned_count")
    reported = value.get("provider_reported_count")
    return {"mode": mode, "returned_count": received if type(received) is int and 0 <= received <= 100 else 0,
            "provider_reported_count": reported if type(reported) is int and 0 <= reported <= 2**63-1 else None,
            "history_complete": False, "next_cursor_present": value.get("next_cursor_present") is True,
            "replies_status": "not_read_tier0", "stop_reason": value.get("stop_reason") if value.get("stop_reason") in {
                "signed_out_embedded_comments", "comment_batch_limit_reached", "not_requested",
                "access_denied", "login_required", "challenge", "rate_limited", "request_budget_reached",
                "page_identity_unverified", "network_error", "parser_error", "response_too_large",
                "no_posts_returned", "not_found", "invalid_request", "timeout"
            } else "not_requested"}


def _safe_comments(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list) or len(value) > 100:
        raise CrawlError("parser_error", "Danh sách bình luận từ runner không hợp lệ.")
    records, seen = [], set()
    for c in value:
        if not isinstance(c, dict):
            raise CrawlError("parser_error", "Bản ghi bình luận không hợp lệ.")
        identity, alias, text = c.get("id"), c.get("author_alias"), c.get("text")
        if (not isinstance(identity, str) or not re.fullmatch(r"[A-Za-z0-9_+=/.-]{1,100}", identity)
                or not isinstance(alias, str) or not re.fullmatch(r"user_name[0-9]{2,3}", alias)
                or not isinstance(text, str) or len(text) > 20_000 or type(c.get("text_truncated")) is not bool):
            raise CrawlError("parser_error", "Định danh/nội dung bình luận không hợp lệ.")
        if identity in seen:
            continue
        seen.add(identity)
        record = {"id": identity, "author_alias": alias, "text": text,
                  "author_identity_known": c.get("author_identity_known") is True,
                  "text_truncated": c["text_truncated"], "published_at": None}
        for key in ("likes", "reactions", "reply_count"):
            n = c.get(key)
            record[key] = n if type(n) is int and 0 <= n <= 2**63-1 else None
        record["reaction_breakdown"] = safe_reaction_breakdown(c.get("reaction_breakdown"))
        raw = c.get("reactions_raw")
        record["reactions_raw"] = (raw.strip() if isinstance(raw, str)
            and re.fullmatch(r"[0-9][0-9 .,KkMmBb+]{0,31}", raw.strip()) else None)
        record["reactions_precision"] = "unknown"
        if record["reactions_raw"] is not None:
            if "+" in record["reactions_raw"]:
                record["reactions_precision"] = "lower_bound"
            elif re.search(r"[KkMmBb]", record["reactions_raw"]):
                record["reactions_precision"] = "approximate"
            else:
                record["reactions_precision"] = "exact"
        if record["likes"] != record["reaction_breakdown"].get("LIKE"):
            record["likes"] = None
        date = c.get("published_at")
        if isinstance(date, str):
            try:
                parsed = datetime.fromisoformat(date.replace("Z", "+00:00"))
                if parsed.tzinfo is not None:
                    record["published_at"] = parsed
            except ValueError:
                pass
        records.append(record)
    return records
