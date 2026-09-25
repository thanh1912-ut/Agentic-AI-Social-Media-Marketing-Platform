"""Exercise a queued market-research job across a local worker restart.

Run `enqueue` while the Celery worker is stopped, start the worker again, then
run `verify --job-id ...`. This writes synthetic rows and is restricted to a
loopback PostgreSQL/Redis acceptance database with no live-provider secrets.
"""

from __future__ import annotations

import argparse
import asyncio
import ipaddress
import json
import time
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
from redis import Redis
from sqlalchemy import select
from sqlalchemy.engine import make_url

from database.models import (
    Job,
    MarketEvidence,
    MarketObservation,
    MarketReport,
    ResearchCycle,
    ResearchSource,
)
from services.api.config import settings
from services.api.db import SessionLocal
from services.api.main import app


def _is_loopback(host: str | None) -> bool:
    if host is None:
        return False
    if host.casefold() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _require_isolated_target(*, require_empty_queues: bool) -> Redis:
    database = make_url(settings.database_url)
    redis_url = urlsplit(settings.redis_url)
    markers = ("test", "smoke", "acceptance", "restart")
    if settings.app_env.casefold() in {"prod", "production"}:
        raise RuntimeError("Refusing to write smoke data while APP_ENV is production.")
    if database.get_backend_name() != "postgresql" or not _is_loopback(database.host):
        raise RuntimeError("DATABASE_URL must target a loopback PostgreSQL instance.")
    if not database.database or not any(
        marker in database.database.casefold() for marker in markers
    ):
        raise RuntimeError(
            "PostgreSQL database name must include test, smoke, acceptance, or restart."
        )
    if redis_url.scheme not in {"redis", "rediss"} or not _is_loopback(
        redis_url.hostname
    ):
        raise RuntimeError("REDIS_URL must target a loopback Redis instance.")
    if settings.inline_jobs:
        raise RuntimeError("Set INLINE_JOBS=0 so the smoke tests the Celery queue.")
    if (
        settings.deepseek_api_key
        or settings.meta_configured
        or settings.meta_public_content_access_token
    ):
        raise RuntimeError(
            "Unset DeepSeek and Meta credentials; this smoke must not call external providers."
        )

    client = Redis.from_url(
        settings.redis_url, socket_connect_timeout=2, socket_timeout=2
    )
    try:
        client.ping()
        depths = {queue: int(client.llen(queue)) for queue in ("agent", "default")}
    except Exception:
        client.close()
        raise
    if require_empty_queues and any(depths.values()):
        client.close()
        raise RuntimeError(
            f"Acceptance queues must be empty before the smoke starts; depths={depths}."
        )
    return client


async def _enqueue(client: Redis) -> int:
    run_id = uuid4().hex
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        timeout=20,
    ) as api:
        registration = await api.post(
            "/api/v1/auth/register",
            json={
                "email": f"worker-restart-{run_id[:16]}@example.com",
                "password": f"Worker-restart-{run_id[:12]}-Acceptance!",
                "full_name": "Worker Restart Acceptance",
                "company_name": "Isolated Worker Restart Workspace",
            },
        )
        if registration.status_code != 201:
            raise RuntimeError(
                f"Account setup failed: HTTP {registration.status_code}."
            )
        state = registration.json()
        workspace_id = state["active_workspace_id"]
        headers = {"Authorization": f"Bearer {state['access_token']}"}
        api.cookies.clear()

        group_response = await api.post(
            f"/api/v1/workspaces/{workspace_id}/market-research/groups",
            headers=headers,
            json={
                "name": f"Worker restart {run_id[:12]}",
                "industry": "Retail",
                "region": "VN",
                "locale": "vi-VN",
                "keywords": ["coffee"],
            },
        )
        if group_response.status_code != 201:
            raise RuntimeError(
                f"Group setup failed: HTTP {group_response.status_code}."
            )
        group_id = group_response.json()["id"]

        source_response = await api.post(
            f"/api/v1/workspaces/{workspace_id}/market-research/sources",
            headers=headers,
            json={
                "group_id": group_id,
                "source_type": "facebook_group",
                "name": "Manual-only smoke source",
                "url": f"https://www.facebook.com/groups/worker-restart-{run_id}",
            },
        )
        if source_response.status_code != 201:
            raise RuntimeError(
                f"Source setup failed: HTTP {source_response.status_code}."
            )
        source_id = source_response.json()["id"]

        imported = await api.post(
            f"/api/v1/workspaces/{workspace_id}/market-research/sources/{source_id}/import",
            headers=headers,
            json={
                "rows": [
                    {
                        "url": f"https://www.facebook.com/groups/worker-restart-{run_id}/posts/1001",
                        "title": "Synthetic coffee demand sample",
                        "text": "Synthetic acceptance fixture: customers ask about breakfast coffee combo and delivery area.",
                        "metrics": {
                            "reactions": 23,
                            "comments": 4,
                            "shares": 2,
                            "interactions": 29,
                            "views": 1500,
                        },
                        "comments": ["Synthetic question about delivery area."],
                    }
                ]
            },
        )
        if imported.status_code != 201 or imported.json().get("imported") != 1:
            raise RuntimeError(f"Manual import failed: HTTP {imported.status_code}.")

        accepted = await api.post(
            f"/api/v1/workspaces/{workspace_id}/market-research/groups/{group_id}/crawl",
            headers=headers,
        )
        if accepted.status_code != 202:
            raise RuntimeError(f"Job enqueue failed: HTTP {accepted.status_code}.")
        job_id = accepted.json()["job_id"]
        if accepted.json()["job"]["status"] != "queued":
            raise RuntimeError(
                "Job was not durably queued; ensure the worker is stopped before enqueue."
            )
        queue_depth = int(client.llen("agent"))
        if queue_depth != 1:
            raise RuntimeError(
                f"Expected one pending message on Redis queue 'agent', found {queue_depth}; "
                "ensure the worker is stopped and the acceptance Redis is otherwise unused."
            )
        print(
            json.dumps(
                {
                    "job_id": job_id,
                    "job_status": "queued",
                    "redis_agent_queue_depth": queue_depth,
                    "manual_import_count": 1,
                    "source_mode": "manual_import_only",
                    "fixture_data": True,
                    "external_meta_or_deepseek_requests": False,
                },
                ensure_ascii=False,
            )
        )
        return 0


async def _verify(job_id: str, timeout_seconds: int, client: Redis) -> int:
    deadline = time.monotonic() + timeout_seconds
    terminal = {"succeeded", "failed", "cancelled"}
    job_status = None
    while time.monotonic() < deadline:
        async with SessionLocal() as db:
            job = await db.get(Job, job_id)
            job_status = job.status if job else None
        if job_status in terminal:
            break
        await asyncio.sleep(1)
    if job_status != "succeeded":
        raise RuntimeError(
            f"Job did not succeed before timeout; final status={job_status!r}."
        )

    async with SessionLocal() as db:
        job = await db.get(Job, job_id)
        cycle = await db.scalar(
            select(ResearchCycle).where(ResearchCycle.job_id == job_id)
        )
        if job is None or cycle is None:
            raise RuntimeError("Job or its durable research cycle is missing.")
        report = await db.scalar(
            select(MarketReport).where(MarketReport.cycle_id == cycle.id)
        )
        evidence = list(
            (
                await db.scalars(
                    select(MarketEvidence).where(
                        MarketEvidence.group_id == cycle.group_id
                    )
                )
            ).all()
        )
        evidence_ids = [row.id for row in evidence]
        observations = (
            list(
                (
                    await db.scalars(
                        select(MarketObservation).where(
                            MarketObservation.evidence_id.in_(evidence_ids)
                        )
                    )
                ).all()
            )
            if evidence_ids
            else []
        )
        source = await db.scalar(
            select(ResearchSource).where(
                ResearchSource.group_id == cycle.group_id,
                ResearchSource.source_type == "facebook_group",
            )
        )
        analysis_status = (job.result or {}).get("analysis_status")
        if (
            cycle.status != "succeeded"
            or report is None
            or len(evidence) != 1
            or len(observations) != 1
        ):
            raise RuntimeError(
                "Expected a succeeded cycle, stored report, one evidence row, and one observation."
            )
        if analysis_status != "deepseek_not_configured":
            raise RuntimeError(
                f"Expected the explicit no-provider status; received {analysis_status!r}."
            )
        if source is None or source.status != "manual_import_only":
            raise RuntimeError(
                "The Facebook group source did not remain manual-import-only."
            )
        queue_depths = {
            queue: int(client.llen(queue)) for queue in ("agent", "default")
        }
        if any(queue_depths.values()):
            raise RuntimeError(
                f"Expected drained acceptance queues after completion; depths={queue_depths}."
            )

    print(
        json.dumps(
            {
                "job_id": job_id,
                "job_status": job_status,
                "cycle_status": cycle.status,
                "report_stored": True,
                "evidence_count": len(evidence),
                "observation_count": len(observations),
                "analysis_status": analysis_status,
                "source_status": source.status,
                "redis_queue_depths": queue_depths,
                "external_meta_or_deepseek_requests": False,
            },
            ensure_ascii=False,
        )
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("enqueue", "verify"))
    parser.add_argument("--job-id", help="Job ID printed by the enqueue action.")
    parser.add_argument("--timeout-seconds", type=int, default=120)
    args = parser.parse_args()
    if args.timeout_seconds < 1:
        parser.error("--timeout-seconds must be positive")
    if args.action == "verify" and not args.job_id:
        parser.error("verify requires --job-id")
    if args.action == "enqueue" and args.job_id:
        parser.error("--job-id is only used with verify")

    client: Redis | None = None
    try:
        client = _require_isolated_target(require_empty_queues=args.action == "enqueue")
        if args.action == "enqueue":
            return asyncio.run(_enqueue(client))
        return asyncio.run(_verify(args.job_id, args.timeout_seconds, client))
    except RuntimeError as error:
        parser.error(str(error))
    except Exception as error:
        parser.error(
            f"Smoke failed ({type(error).__name__}); inspect the local service logs."
        )
    finally:
        if client is not None:
            client.close()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
