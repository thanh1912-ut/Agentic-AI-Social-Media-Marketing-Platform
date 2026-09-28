from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from services.research import facebook_cli_collector as collector
from services.research.web_crawler import CrawlError


def _runner(tmp_path: Path, script_body: str) -> Path:
    executable = tmp_path / "facebook-cli-runner"
    executable.write_text("#!/usr/bin/env python3\n" + script_body, encoding="utf-8")
    executable.chmod(0o755)
    return executable


def _row(kind: str, **data: object) -> str:
    return json.dumps({"schema_version": 1, "type": kind, **data}, ensure_ascii=False)


def test_collector_runs_without_inheriting_facebook_cookies_and_keeps_partial_coverage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = tmp_path / "child-env.txt"
    monkeypatch.setenv("FB_COOKIES", "must-not-be-inherited")
    monkeypatch.setattr(collector, "canonicalize_url", lambda value: value)
    page = {
        "id": "page-1", "name": "Page thật", "url": "https://www.facebook.com/rival",
        "kind": "page", "followers": None,
    }
    post = {
        "id": "123456", "url": "https://www.facebook.com/rival/posts/123456",
        "text": "Bài tiếng Việt", "published_at": "not-a-date",
        "counts": {"reactions": None, "comments": 0, "shares": None, "views": None},
        "counts_raw": {"comments": "0"},
    }
    rows = "\n".join([
        _row("page", page=page),
        _row("post", post=post),
        _row("summary", engine_version=collector.ENGINE_VERSION, http_requests=3,
             posts_truncated=False, history_complete=False, stop_reason="tier0_feed_limited"),
    ])
    executable = _runner(tmp_path, f"""
import json, os, pathlib, sys
request = json.load(sys.stdin)
pathlib.Path({str(marker)!r}).write_text(json.dumps({{"run_id": request.get("run_id"), "cookies": os.getenv("FB_COOKIES")}}))
sys.stdout.write({rows!r} + "\\n")
""")

    result = asyncio.run(collector.collect_public_facebook_page(
        "https://www.facebook.com/rival", run_id="run-123", post_limit=50,
        runner_path=executable,
    ))

    assert json.loads(marker.read_text()) == {"run_id": "run-123", "cookies": None}
    assert result.page["id"] == "page-1"
    assert result.posts[0]["published_at"] is None
    assert result.coverage["access_tier"] == 0
    assert result.coverage["history_complete"] is False
    assert result.coverage["returned_posts"] == 1
    assert result.coverage["oldest_post_at"] is None
    assert result.coverage["missing_fields"] == ["published_at", "reactions", "shares", "views"]


def test_collector_maps_facebook_access_failure_without_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(collector, "canonicalize_url", lambda value: value)
    executable = _runner(tmp_path, """
import json, sys
print(json.dumps({"schema_version": 1, "type": "error", "failure_kind": "login_required", "error_code": 4}))
sys.exit(4)
""")

    with pytest.raises(CrawlError) as error:
        asyncio.run(collector.collect_public_facebook_page(
            "https://www.facebook.com/rival", run_id="run-456", post_limit=10,
            runner_path=executable,
        ))

    assert error.value.code == "login_required"
    assert not error.value.retryable


def test_collector_rejects_wrong_upstream_pin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(collector, "canonicalize_url", lambda value: value)
    executable = _runner(tmp_path, """
import json
print(json.dumps({"schema_version": 1, "type": "page", "page": {"id": "page-1", "name": "Rival", "url": "https://www.facebook.com/rival", "kind": "page"}}))
print(json.dumps({"schema_version": 1, "type": "summary", "engine_version": "facebook-cli@latest"}))
""")

    with pytest.raises(CrawlError) as error:
        asyncio.run(collector.collect_public_facebook_page(
            "https://www.facebook.com/rival", run_id="run-789", post_limit=10,
            runner_path=executable,
        ))

    assert error.value.code == "engine_version_mismatch"
