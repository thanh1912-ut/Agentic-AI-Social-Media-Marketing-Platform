#!/usr/bin/env python3
"""Build, activate, inspect, or roll back only the local web preview LaunchAgent."""

from __future__ import annotations

import argparse
import json
import os
import plistlib
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


LABEL = "com.agentic-marketing.auth-preview-web"
API_READY_URL = "http://127.0.0.1:8001/readyz"
PREVIEW_URL = "http://127.0.0.1:13104/login"
FONT_URL = "http://127.0.0.1:13104/fonts/be-vietnam-pro/BeVietnamPro-Regular.ttf"
DEFAULT_RELEASE_ROOT = Path.home() / ".local/share/agentic-marketing/frontend-releases"


def timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def request_status(url: str, timeout: float = 2.0) -> tuple[int, bytes]:
    request = urllib.request.Request(url, headers={"User-Agent": "agentic-marketing-preview-health/1"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.status, response.read(256 * 1024)


def api_is_ready() -> bool:
    try:
        status, body = request_status(API_READY_URL)
        payload = json.loads(body)
        return status == 200 and payload.get("status") == "ready"
    except (OSError, urllib.error.URLError, ValueError, json.JSONDecodeError):
        return False


def preview_is_ready() -> bool:
    return login_is_ready() and font_is_ready()


def login_is_ready() -> bool:
    try:
        status, _ = request_status(PREVIEW_URL)
        return status == 200
    except (OSError, urllib.error.URLError):
        return False


def font_is_ready() -> bool:
    try:
        status, font_body = request_status(FONT_URL)
        return status == 200 and len(font_body) > 100_000
    except (OSError, urllib.error.URLError):
        return False


def launch_domain() -> str:
    return f"gui/{os.getuid()}"


def launchctl(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["launchctl", *arguments],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )


def is_loaded() -> bool:
    result = launchctl("print", f"{launch_domain()}/{LABEL}")
    return result.returncode == 0


def bootout_if_loaded() -> None:
    if is_loaded():
        result = launchctl("bootout", f"{launch_domain()}/{LABEL}")
        if result.returncode != 0:
            raise RuntimeError("Không dừng được đúng LaunchAgent frontend để cập nhật.")


def bootstrap(plist_path: Path) -> None:
    result = launchctl("bootstrap", launch_domain(), str(plist_path))
    if result.returncode != 0:
        raise RuntimeError("Không nạp lại được LaunchAgent frontend.")


def wait_for_preview(seconds: int = 30) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if preview_is_ready():
            return True
        time.sleep(1)
    return False


def plist_path() -> Path:
    return Path.home() / "Library/LaunchAgents" / f"{LABEL}.plist"


def read_plist(path: Path) -> dict:
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy LaunchAgent {LABEL}.")
    data = plistlib.loads(path.read_bytes())
    if data.get("Label") != LABEL:
        raise RuntimeError("LaunchAgent có label khác; dừng để tránh thay dịch vụ khác.")
    return data


def write_plist_atomically(path: Path, data: dict) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_bytes(plistlib.dumps(data, fmt=plistlib.FMT_XML, sort_keys=False))
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def current_git_info(app_root: Path) -> tuple[str, str]:
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=app_root, text=True).strip()
    branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=app_root, text=True).strip()
    return sha, branch


def prepare_release(app_root: Path, release_root: Path) -> tuple[Path, dict]:
    node = shutil.which("node")
    if not node:
        raise RuntimeError("Không tìm thấy Node.js trong PATH.")
    prepare_script = app_root / "scripts/prepare-standalone.mjs"
    prepared = subprocess.run([node, str(prepare_script)], cwd=app_root, check=False, capture_output=True, text=True)
    if prepared.returncode != 0:
        raise RuntimeError("Không chuẩn bị được static/public assets cho standalone release.")

    standalone = app_root / ".next/standalone"
    server = standalone / "apps/web/server.js"
    font = standalone / "apps/web/public/fonts/be-vietnam-pro/BeVietnamPro-Regular.ttf"
    if not server.is_file() or not font.is_file():
        raise RuntimeError("Build standalone thiếu server hoặc font local; chưa thay preview.")

    sha, branch = current_git_info(app_root.parents[1])
    release_id = f"{branch.replace('/', '-')}-{sha[:12]}-{timestamp()}"
    release = release_root / "releases" / release_id
    release.mkdir(parents=True, exist_ok=False)
    target = release / "standalone"
    shutil.copytree(standalone, target, symlinks=True)
    manifest = {
        "release_id": release_id,
        "git_sha": sha,
        "branch": branch,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "use_mocks": False,
        "api_origin": "http://127.0.0.1:8001",
        "server": str(target / "apps/web/server.js"),
    }
    (release / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return release, manifest


def activate(app_root: Path, release_root: Path) -> None:
    if not api_is_ready():
        raise RuntimeError("API :8001 chưa sẵn sàng; giữ nguyên frontend đang chạy.")
    path = plist_path()
    old_plist = read_plist(path)
    old_arguments = old_plist.get("ProgramArguments", [])
    if len(old_arguments) < 2:
        raise RuntimeError("LaunchAgent frontend chưa có ProgramArguments hợp lệ.")

    release, manifest = prepare_release(app_root, release_root)
    server_path = Path(manifest["server"])
    backup_dir = release_root / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / f"{LABEL}-{timestamp()}.plist"
    shutil.copy2(path, backup)

    candidate = dict(old_plist)
    candidate["ProgramArguments"] = [old_arguments[0], str(server_path)]
    candidate["WorkingDirectory"] = str(server_path.parent)
    environment = dict(candidate.get("EnvironmentVariables", {}))
    environment.update({
        "HOSTNAME": "127.0.0.1",
        "PORT": "13104",
        "NODE_ENV": "production",
        "NEXT_PUBLIC_USE_MOCKS": "0",
        "NEXT_PUBLIC_API_BASE_URL": "http://127.0.0.1:8001",
        "NEXT_PUBLIC_ENVIRONMENT_LABEL": "API thật",
    })
    candidate["EnvironmentVariables"] = environment
    state_path = release_root / "current.json"
    state = {
        "label": LABEL,
        "release": str(release),
        "previous_plist_backup": str(backup),
        "previous_server": old_arguments[1],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    write_plist_atomically(path, candidate)
    try:
        bootout_if_loaded()
        bootstrap(path)
        if not wait_for_preview():
            raise RuntimeError("Frontend mới không vượt qua kiểm tra /login và font.")
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n")
    except Exception as error:
        # Restore only this frontend LaunchAgent and its previous entrypoint.
        write_plist_atomically(path, old_plist)
        bootout_if_loaded()
        bootstrap(path)
        wait_for_preview()
        raise RuntimeError(f"Kích hoạt không thành công; đã khôi phục frontend cũ. {error}") from error

    print(f"Activated {manifest['release_id']} on http://127.0.0.1:13104")
    print(f"Release: {release}")
    print("API, database, workers, schedules and secret files were not changed.")


def rollback(release_root: Path) -> None:
    state_path = release_root / "current.json"
    if not state_path.is_file():
        raise RuntimeError("Không tìm thấy trạng thái release để rollback.")
    state = json.loads(state_path.read_text())
    if state.get("label") != LABEL:
        raise RuntimeError("Trạng thái release không thuộc frontend preview mục tiêu.")
    backup = Path(state["previous_plist_backup"])
    old_plist = read_plist(backup)
    path = plist_path()
    write_plist_atomically(path, old_plist)
    bootout_if_loaded()
    bootstrap(path)
    if not wait_for_preview():
        raise RuntimeError("Đã nạp lại cấu hình cũ nhưng chưa xác nhận được /login/font.")
    state["rolled_back_at"] = datetime.now(timezone.utc).isoformat()
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n")
    print(f"Restored previous frontend on http://127.0.0.1:13104 ({state['previous_server']})")


def status(release_root: Path) -> None:
    state_path = release_root / "current.json"
    release = "chưa có release do script này quản lý"
    if state_path.is_file():
        try:
            release = json.loads(state_path.read_text()).get("release", release)
        except (OSError, json.JSONDecodeError):
            release = "không đọc được metadata release"
    print(f"LaunchAgent loaded: {'yes' if is_loaded() else 'no'}")
    print(f"API ready: {'yes' if api_is_ready() else 'no'}")
    print(f"Frontend /login ready: {'yes' if login_is_ready() else 'no'}")
    print(f"Local font ready: {'yes' if font_is_ready() else 'no'}")
    print(f"Release metadata: {release}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("status", "activate", "rollback"))
    parser.add_argument("--release-root", type=Path, default=DEFAULT_RELEASE_ROOT)
    parser.add_argument("--app-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        if args.command == "status":
            status(args.release_root)
        elif args.command == "activate":
            activate(args.app_root, args.release_root)
        else:
            rollback(args.release_root)
    except (OSError, RuntimeError, subprocess.SubprocessError, json.JSONDecodeError) as error:
        print(f"Preview operation failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
