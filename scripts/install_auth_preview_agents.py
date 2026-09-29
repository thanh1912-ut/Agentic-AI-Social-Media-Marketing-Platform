#!/usr/bin/env python3
"""Install persistent per-user LaunchAgents for the isolated auth preview."""

from __future__ import annotations

import argparse
import os
import plistlib
import subprocess
import sys
import time
from pathlib import Path


HOME = Path.home()
RUNTIME = Path(
    os.environ.get(
        "AGENTIC_MARKETING_RUNTIME_ROOT", HOME / ".local/share/agentic-marketing"
    )
).expanduser()
PREVIEW = RUNTIME / "auth-preview"
WORKTREE = Path(__file__).resolve().parents[1]
LAUNCH_AGENTS = HOME / "Library/LaunchAgents"
LOGS = PREVIEW / "logs"
PYTHON_API = PREVIEW / "venvs/api-py311/bin/python"
PYTHON_DOCLING = PREVIEW / "venvs/docling-py314/bin/python"
RUNNER = WORKTREE / "scripts/local_preview_runtime.py"
NODE = HOME / ".local/bin/node"
WEB_SERVER = WORKTREE / "apps/web/.next/standalone/apps/web/server.js"


def launch_agent_specs() -> dict[str, dict[str, object]]:
    return {
        "com.agentic-marketing.auth-preview-api": {
            "ProgramArguments": [str(PYTHON_API), str(RUNNER), "api"],
            "WorkingDirectory": str(WORKTREE),
            "EnvironmentVariables": {
                "HOME": str(HOME),
                "PATH": "/opt/homebrew/bin:/usr/bin:/bin",
                "LANG": "C",
                "LC_ALL": "C",
            },
        },
        "com.agentic-marketing.auth-preview-worker": {
            "ProgramArguments": [str(PYTHON_API), str(RUNNER), "worker"],
            "WorkingDirectory": str(WORKTREE),
            "EnvironmentVariables": {
                "HOME": str(HOME),
                "PATH": "/opt/homebrew/bin:/usr/bin:/bin",
                "LANG": "C",
                "LC_ALL": "C",
            },
        },
        "com.agentic-marketing.auth-preview-beat": {
            "ProgramArguments": [str(PYTHON_API), str(RUNNER), "beat"],
            "WorkingDirectory": str(WORKTREE),
            "EnvironmentVariables": {
                "HOME": str(HOME),
                "PATH": "/opt/homebrew/bin:/usr/bin:/bin",
                "LANG": "C",
                "LC_ALL": "C",
            },
        },
        "com.agentic-marketing.auth-preview-ingestion": {
            "ProgramArguments": [str(PYTHON_DOCLING), str(RUNNER), "worker-ingestion"],
            "WorkingDirectory": str(WORKTREE),
            "EnvironmentVariables": {
                "HOME": str(HOME),
                "PATH": "/opt/homebrew/bin:/usr/bin:/bin",
                "LANG": "C",
                "LC_ALL": "C",
            },
        },
        "com.agentic-marketing.auth-preview-web": {
            "ProgramArguments": [str(NODE), str(WEB_SERVER)],
            "WorkingDirectory": str(WEB_SERVER.parent),
            "EnvironmentVariables": {
                "HOME": str(HOME),
                "PATH": "/opt/homebrew/bin:/usr/bin:/bin",
                "LANG": "C",
                "LC_ALL": "C",
                "NODE_ENV": "production",
                "HOSTNAME": "127.0.0.1",
                "PORT": "13104",
            },
        },
    }


def _launchctl(
    *arguments: str, ignore_error: bool = False
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["/bin/launchctl", *arguments],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode and not ignore_error:
        details = (result.stderr or result.stdout).strip().splitlines()
        reason = (
            " / ".join(details[:2])[:300] if details else "no diagnostic from launchctl"
        )
        raise RuntimeError(
            f"launchctl {arguments[0]} failed for the auth preview: {reason}"
        )
    return result


def _domain() -> str:
    return f"gui/{os.getuid()}"


def _service_is_loaded(label: str) -> bool:
    result = _launchctl("print", f"{_domain()}/{label}", ignore_error=True)
    return result.returncode == 0


def _bootstrap_with_retry(label: str, path: Path) -> None:
    last_error = "no diagnostic from launchctl"
    for _attempt in range(5):
        result = _launchctl("bootstrap", _domain(), str(path), ignore_error=True)
        if result.returncode == 0 or _service_is_loaded(label):
            return
        details = (result.stderr or result.stdout).strip().splitlines()
        if details:
            last_error = " / ".join(details[:2])[:300]
        time.sleep(1)
    raise RuntimeError(f"launchctl bootstrap failed for {label}: {last_error}")


def install() -> None:
    required = (PYTHON_API, PYTHON_DOCLING, RUNNER, NODE, WEB_SERVER)
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise RuntimeError(
            "Preview runtime is incomplete; prepare persistent environments and frontend build first"
        )
    for name in ("app.env", "auth-preview.env", "deepseek-docling.env"):
        path = RUNTIME / "secrets" / name
        if not path.is_file():
            raise RuntimeError(f"Required local configuration file is missing: {name}")
        path.chmod(0o600)

    LAUNCH_AGENTS.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    (PREVIEW / "beat").mkdir(parents=True, exist_ok=True)
    for label, config in launch_agent_specs().items():
        path = LAUNCH_AGENTS / f"{label}.plist"
        _launchctl("bootout", f"{_domain()}/{label}", ignore_error=True)
        for _attempt in range(10):
            if not _service_is_loaded(label):
                break
            time.sleep(0.2)
        payload = {
            "Label": label,
            "RunAtLoad": True,
            "KeepAlive": True,
            "StandardOutPath": str(LOGS / f"{label}.log"),
            "StandardErrorPath": str(LOGS / f"{label}.error.log"),
            **config,
        }
        temporary = path.with_suffix(".plist.tmp")
        temporary.write_bytes(plistlib.dumps(payload))
        temporary.chmod(0o600)
        temporary.replace(path)
        _bootstrap_with_retry(label, path)
    print(
        "Auth preview API, workers, and frontend are installed as persistent user services."
    )


def stop() -> None:
    for label in launch_agent_specs():
        _launchctl("bootout", f"{_domain()}/{label}", ignore_error=True)
    print(
        "Auth preview application services are stopped; PostgreSQL/Redis remain available."
    )


def restart() -> None:
    for label in launch_agent_specs():
        _launchctl("kickstart", "-k", f"{_domain()}/{label}")
    print("Auth preview application services were restarted.")


def status() -> None:
    for label in launch_agent_specs():
        result = _launchctl("print", f"{_domain()}/{label}", ignore_error=True)
        if result.returncode:
            state = "not loaded"
        else:
            state = next(
                (
                    line.partition("=")[2].strip()
                    for line in result.stdout.splitlines()
                    if line.strip().startswith("state =")
                ),
                "loaded",
            )
        print(f"{label.rsplit('.', 1)[-1]}: {state}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("install", "restart", "stop", "status"))
    args = parser.parse_args()
    try:
        {"install": install, "restart": restart, "stop": stop, "status": status}[
            args.action
        ]()
    except (OSError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
