"""Durable Meta work. Publish sends are never retried after the send boundary."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import (
    AuditEvent, CampaignPost, Job, JobStep, MediaAsset, MetaPageConnection, MetaPagePost,
    MetaPublication, MetaSyncState, PostApproval, PostMetricSnapshot, PostVersion, utcnow,
)
from services.api.config import settings
from services.api.content_integrity import content_sha256
from services.api.db import SessionLocal
from services.api.meta_client import (
    MetaGraphClient, MetaGraphOutcomeUnknown, MetaGraphReadError,
    MetaGraphRejected, MetaGraphTokenExpired, MetaPostMetrics,
)
from services.api.meta_tokens import TokenEncryptionUnavailable, decrypt_page_token
from services.api.storage import storage
from .async_runtime import run_worker_coroutine
from .celery_app import celery_app


def _safe_error(code: str, message: str) -> dict[str, object]:
    return {"code": code, "message": message, "retryable": False}


async def _finish_job(db: AsyncSession, job: Job, *, succeeded: bool, error: dict | None = None) -> None:
    job.status = "succeeded" if succeeded else "failed"
    job.progress = 100
    job.error = error
    job.finished_at = utcnow()
    job.lease_until = None
    step = await db.scalar(select(JobStep).where(JobStep.job_id == job.id))
    if step:
        step.status = "succeeded" if succeeded else "failed"
        step.progress = 100
        step.finished_at = utcnow()
        step.error = error


async def _claim(job_id: str, kind: str) -> bool:
    async with SessionLocal() as db:
        job = await db.scalar(select(Job).where(Job.id == job_id, Job.kind == kind).with_for_update())
        if job is None or job.status != "queued":
            return False
        job.status = "running"
        job.started_at = utcnow()
        job.lease_until = utcnow() + timedelta(minutes=settings.job_lease_minutes)
        job.attempts += 1
        step = await db.scalar(select(JobStep).where(JobStep.job_id == job.id))
        if step:
            step.status = "running"
            step.started_at = utcnow()
        await db.commit()
        return True


async def _publish_preflight(db: AsyncSession, row: MetaPublication) -> tuple[str, bytes | None, str | None, str]:
    if row.connection_id:
        connection = await db.scalar(select(MetaPageConnection).where(
            MetaPageConnection.company_id == row.company_id, MetaPageConnection.id == row.connection_id,
            MetaPageConnection.page_id == row.page_id, MetaPageConnection.active.is_(True),
            MetaPageConnection.status == "verified", MetaPageConnection.verified_at.is_not(None),
        ).with_for_update())
        if connection is None:
            raise ValueError("connection_changed")
        try:
            page_token = decrypt_page_token(connection.encrypted_token)
        except TokenEncryptionUnavailable as error:
            raise ValueError("connection_changed") from error
    else:
        if not settings.meta_configured or row.company_id != settings.meta_workspace_id or row.page_id != settings.meta_page_id:
            raise ValueError("connection_changed")
        page_token = settings.meta_page_access_token
    post = await db.scalar(select(CampaignPost).where(
        CampaignPost.id == row.post_id, CampaignPost.company_id == row.company_id
    ).with_for_update())
    version = await db.scalar(select(PostVersion).where(
        PostVersion.company_id == row.company_id, PostVersion.post_id == row.post_id,
        PostVersion.version == row.post_version,
    ))
    approval = await db.scalar(select(PostApproval).where(
        PostApproval.company_id == row.company_id, PostApproval.post_id == row.post_id,
        PostApproval.version == row.post_version,
    ).order_by(PostApproval.decided_at.desc(), PostApproval.id.desc()))
    if (
        post is None or version is None or approval is None or approval.decision != "approved"
        or post.status != "scheduled" or post.current_version != row.post_version
        or post.requires_reapproval or post.channel != "facebook_page"
        or content_sha256(version.content_json) != row.approved_content_sha256
        or content_sha256(post.current_json) != row.approved_content_sha256
        or approval.content_sha256 != row.approved_content_sha256
    ):
        raise ValueError("approval_changed")
    caption = version.content_json.get("caption")
    if not isinstance(caption, str) or not caption.strip():
        raise ValueError("caption_missing")
    hashtags = version.content_json.get("hashtags")
    tags = [tag.strip() for tag in hashtags if isinstance(tag, str) and tag.strip()] if isinstance(hashtags, list) else []
    message = caption.strip() + ("\n\n" + " ".join(tags) if tags else "")
    media = version.content_json.get("media") or []
    if post.format == "text" and not media:
        return message, None, None, page_token
    if post.format != "image" or not isinstance(media, list) or len(media) != 1 or not isinstance(media[0], dict):
        raise ValueError("media_unsupported")
    item = media[0]
    if item.get("source") != "uploaded" or not isinstance(item.get("asset_id"), str):
        raise ValueError("media_unsupported")
    asset = await db.scalar(select(MediaAsset).where(
        MediaAsset.id == item["asset_id"], MediaAsset.company_id == row.company_id
    ))
    if asset is None or asset.mime_type not in {"image/jpeg", "image/png"}:
        raise ValueError("media_unsupported")
    if item.get("sha256") != asset.content_sha256:
        raise ValueError("media_changed")
    try:
        image_bytes = await storage.read(asset.storage_key)
    except Exception as exc:
        raise ValueError("media_unavailable") from exc
    if hashlib.sha256(image_bytes).hexdigest() != asset.content_sha256:
        raise ValueError("media_changed")
    return message, image_bytes, asset.mime_type, page_token


async def _finish_publish(job_id: str, status: str, *, external_post_id: str | None = None,
                          error_code: str | None = None, error_message: str | None = None) -> None:
    async with SessionLocal() as db:
        job = await db.scalar(select(Job).where(Job.id == job_id).with_for_update())
        if job is None or job.status != "running":
            return
        row = await db.scalar(select(MetaPublication).where(MetaPublication.job_id == job_id).with_for_update())
        if row is None or row.status != "sending":
            return
        post = await db.scalar(select(CampaignPost).where(
            CampaignPost.company_id == row.company_id, CampaignPost.id == row.post_id
        ).with_for_update())
        row.status = status
        row.updated_at = utcnow()
        row.error_json = {"code": error_code, "message": error_message} if error_code and error_message else None
        if status == "published":
            row.external_post_id = external_post_id
            row.published_at = utcnow()
            if post and post.current_version == row.post_version and post.status == "scheduled":
                post.status = "published"
                post.updated_at = utcnow()
        elif status in {"failed", "needs_reconnect"}:
            row.active_key = None
            if post and post.current_version == row.post_version and post.status == "scheduled":
                post.status = "approved"
                post.updated_at = utcnow()
        # outcome_unknown keeps the active key and post locked until an owner reconciles.
        await _finish_job(db, job, succeeded=status == "published",
                          error=_safe_error(error_code, error_message) if error_code and error_message else None)
        db.add(AuditEvent(company_id=row.company_id, actor_user_id=job.created_by,
                          action=f"meta.publish.{status}", entity_type="meta_publication", entity_id=row.id,
                          metadata_json={"page_id": row.page_id, "post_id": row.post_id,
                                         "external_post_id": external_post_id}))
        if status == "needs_reconnect":
            connection = await db.scalar(select(MetaPageConnection).where(
                MetaPageConnection.company_id == row.company_id, MetaPageConnection.id == row.connection_id,
            ).with_for_update()) if row.connection_id else None
            if connection:
                connection.status = "needs_reconnect"
                connection.last_error_code = error_code or "token_invalid"
                connection.verified_at = None
            state = await db.scalar(select(MetaSyncState).where(
                MetaSyncState.company_id == row.company_id, MetaSyncState.page_id == row.page_id
            ))
            if state:
                state.verified_at = None
        await db.commit()


async def _run_publish(job_id: str) -> None:
    async with SessionLocal() as db:
        row = await db.scalar(select(MetaPublication).where(MetaPublication.job_id == job_id).with_for_update())
        if row is None or row.status != "queued":
            return
        try:
            message, image_bytes, mime_type, page_token = await _publish_preflight(db, row)
        except (ValueError, OSError):
            # No request to Meta was made; releasing the post is safe.
            row.status = "failed"
            row.active_key = None
            row.error_json = {"code": "meta_preflight_failed", "message": "Bài hoặc ảnh không còn khớp phiên bản đã duyệt."}
            post = await db.get(CampaignPost, row.post_id)
            if post and post.current_version == row.post_version and post.status == "scheduled":
                post.status = "approved"
            job = await db.get(Job, job_id)
            if job:
                await _finish_job(db, job, succeeded=False,
                                  error=_safe_error("meta_preflight_failed", row.error_json["message"]))
            await db.commit()
            return
        # This commit is the no-retry boundary. A crash after it is ambiguous.
        row.status = "sending"
        row.sent_at = utcnow()
        row.updated_at = utcnow()
        await db.commit()
    try:
        async with MetaGraphClient(row.page_id, page_token,
                                   settings.meta_graph_version) as client:
            if image_bytes is None:
                result = await client.publish_text(message)
            else:
                result = await client.publish_photo(message, image_bytes, mime_type or "")
    except MetaGraphTokenExpired:
        await _finish_publish(job_id, "needs_reconnect", error_code="meta_token_invalid",
                              error_message="Token Fanpage không còn hợp lệ; hãy cấu hình lại trên backend.")
    except MetaGraphRejected:
        await _finish_publish(job_id, "failed", error_code="meta_publish_rejected",
                              error_message="Meta từ chối bài đăng. Kiểm tra quyền Page và nội dung.")
    except (MetaGraphOutcomeUnknown, Exception):
        await _finish_publish(job_id, "outcome_unknown", error_code="meta_outcome_unknown",
                              error_message="Chưa rõ bài đã đăng hay chưa. Hãy kiểm tra Fanpage trước khi đối soát.")
    else:
        await _finish_publish(job_id, "published", external_post_id=result.external_post_id)


async def _upsert_page_post(db: AsyncSession, company_id: str, page_id: str, item: object,
                            linked_post_id: str | None) -> None:
    now = utcnow()
    external_id = item.external_post_id
    row = await db.scalar(select(MetaPagePost).where(
        MetaPagePost.company_id == company_id, MetaPagePost.page_id == page_id,
        MetaPagePost.external_post_id == external_id,
    ))
    if row is None:
        row = MetaPagePost(company_id=company_id, page_id=page_id,
                           external_post_id=external_id, last_synced_at=now)
        db.add(row)
    row.linked_post_id = linked_post_id or row.linked_post_id
    row.message = getattr(item, "message", row.message)
    row.permalink = getattr(item, "permalink_url", row.permalink)
    row.published_at = getattr(item, "created_time", row.published_at)
    row.reactions = item.reactions
    row.comments = item.comments
    row.shares = item.shares
    row.last_synced_at = now
    row.updated_at = now


async def _sync_published_metrics(db: AsyncSession, job: Job, client: MetaGraphClient, page_id: str) -> int:
    rows = (await db.scalars(select(MetaPublication).where(
        MetaPublication.company_id == job.company_id,
        MetaPublication.page_id == page_id,
        MetaPublication.status == "published",
        MetaPublication.external_post_id.is_not(None),
    ).order_by(MetaPublication.published_at.desc()).limit(100))).all()
    count = 0
    for row in rows:
        try:
            metric = await client.read_post_metrics(row.external_post_id or "")
        except MetaGraphTokenExpired:
            raise
        except (MetaGraphRejected, MetaGraphReadError, ValueError):
            continue  # Deleted/inaccessible posts do not become invented zeroes.
        now = utcnow()
        counts = (metric.reactions, metric.comments, metric.shares)
        engagements = sum(counts) if all(value is not None for value in counts) else None
        published = metric.created_time or row.published_at or now
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        age_hours = max(0, int((now - published).total_seconds() // 3600))
        db.add(PostMetricSnapshot(
            company_id=job.company_id, post_id=row.post_id, source_id=f"meta:{page_id}",
            measured_at=now, post_age_hours=age_hours, reach=None, views=None,
            engagements=engagements, clicks=None, spend=None, attributed_revenue=None,
            attribution_valid=False, imported_by=job.created_by,
        ))
        if metric.permalink_url:
            row.permalink = metric.permalink_url
        await _upsert_page_post(db, job.company_id, page_id, metric, row.post_id)
        count += 1
    return count


async def _run_sync(job_id: str) -> None:
    async with SessionLocal() as db:
        job = await db.get(Job, job_id)
        if job is None:
            return
        job_result = job.result or {}
        page_id = str(job_result.get("page_id") or "")
        connection_id = job_result.get("connection_id")
        page_token = ""
        if connection_id:
            connection = await db.scalar(select(MetaPageConnection).where(
                MetaPageConnection.company_id == job.company_id, MetaPageConnection.id == connection_id,
                MetaPageConnection.page_id == page_id, MetaPageConnection.active.is_(True),
                MetaPageConnection.status == "verified", MetaPageConnection.verified_at.is_not(None),
            ))
            if connection:
                try:
                    page_token = decrypt_page_token(connection.encrypted_token)
                except TokenEncryptionUnavailable:
                    page_token = ""
        elif settings.meta_configured and settings.meta_workspace_id == job.company_id and page_id == settings.meta_page_id:
            page_token = settings.meta_page_access_token
        state = await db.scalar(select(MetaSyncState).where(
            MetaSyncState.company_id == job.company_id, MetaSyncState.page_id == page_id,
        ))
        if state is None or state.running_job_id != job_id or not page_token:
            await _finish_job(db, job, succeeded=False,
                              error=_safe_error("meta_connection_changed", "Cấu hình Fanpage đã thay đổi."))
            await db.commit()
            return
        imported = 0
        refreshed = 0
        try:
            async with MetaGraphClient(page_id, page_token,
                                       settings.meta_graph_version) as client:
                # Always refresh the newest Page posts, then continue the old-post cursor.
                first = await client.list_page_posts(limit=100)
                cursor = state.next_cursor if state.has_more and state.next_cursor else first.next_cursor
                publications = (await db.scalars(select(MetaPublication).where(
                    MetaPublication.company_id == job.company_id,
                    MetaPublication.page_id == page_id,
                    MetaPublication.status == "published",
                    MetaPublication.external_post_id.is_not(None),
                ))).all()
                linked = {row.external_post_id: row.post_id for row in publications}
                for item in first.posts:
                    await _upsert_page_post(db, job.company_id, page_id,
                                            item, linked.get(item.external_post_id))
                    imported += 1
                seen = set()
                for _ in range(4):  # Up to 500 Page posts per user-initiated job.
                    if not cursor or cursor in seen:
                        break
                    seen.add(cursor)
                    page = await client.list_page_posts(limit=100, after=cursor)
                    for item in page.posts:
                        await _upsert_page_post(db, job.company_id, page_id,
                                                item, linked.get(item.external_post_id))
                        imported += 1
                    cursor = page.next_cursor
                    state.next_cursor = cursor
                    state.has_more = bool(cursor)
                    await db.commit()  # Backfill progress survives a later read failure.
                if not seen:
                    state.next_cursor = first.next_cursor
                    state.has_more = bool(first.next_cursor)
                refreshed = await _sync_published_metrics(db, job, client, page_id)
        except MetaGraphTokenExpired:
            state.verified_at = None
            error = _safe_error("meta_token_invalid", "Token Fanpage không còn hợp lệ; hãy cấu hình lại trên backend.")
        except (MetaGraphRejected, MetaGraphReadError, ValueError):
            error = _safe_error("meta_sync_failed", "Không đọc được bài và số liệu Fanpage từ Meta.")
        except Exception:
            error = _safe_error("meta_sync_failed", "Đồng bộ Fanpage bị gián đoạn. Có thể thử lại.")
        else:
            error = None
        state.running_job_id = None
        state.last_sync_at = utcnow() if error is None else state.last_sync_at
        state.updated_at = utcnow()
        job.result = {"page_id": page_id, "posts_seen": imported,
                      "published_metrics_refreshed": refreshed, "has_more_history": state.has_more}
        await _finish_job(db, job, succeeded=error is None, error=error)
        db.add(AuditEvent(company_id=job.company_id, actor_user_id=job.created_by,
                          action="meta.metrics.sync.complete" if error is None else "meta.metrics.sync.failed",
                          entity_type="meta_page", entity_id=None,
                          metadata_json={"page_id": page_id, "posts_seen": imported,
                                         "published_metrics_refreshed": refreshed}))
        await db.commit()


async def meta_job_async(job_id: str, kind: str) -> None:
    if kind not in {"meta_publish", "meta_metrics_sync"} or not await _claim(job_id, kind):
        return
    if kind == "meta_publish":
        await _run_publish(job_id)
    else:
        await _run_sync(job_id)


@celery_app.task(name="services.worker.meta_tasks.meta_job")
def meta_job(job_id: str, kind: str) -> None:
    run_worker_coroutine(meta_job_async(job_id, kind))
