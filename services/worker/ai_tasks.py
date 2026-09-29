"""M3 task handlers callable from the M2 worker framework.

These functions deliberately return a payload and instrumentation only.  M2
still owns job status, retries, authorization, persistence and transactions.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from services.agents.content_agent import ContentAgent
from packages.contracts import BrandProfile, CampaignBrief, GeneratedPost, GenerationMetadata


@dataclass(frozen=True)
class AiTaskResult:
    task_name: str
    job_id: str
    input_snapshot_id: str
    payload: dict[str, Any]
    repair_attempts: int
    metadata: GenerationMetadata | None


def run_content_task(
    *,
    job_id: str,
    input_snapshot_id: str,
    agent: ContentAgent,
    profile: BrandProfile,
    brief: CampaignBrief,
    base_version: str,
    next_version: int,
    context: Sequence[Mapping[str, str]],
    content_requirements: Mapping[str, Any] | None = None,
    channel: str | None = None,
    operation: str = "generate",
    repair=None,
) -> AiTaskResult:
    post, metadata, repairs = agent.generate(
        profile=profile,
        brief=brief,
        base_version=base_version,
        next_version=next_version,
        context=context,
        content_requirements=content_requirements,
        channel=channel,
        operation=operation,
        repair=repair,
    )
    return AiTaskResult(
        task_name="content_generation",
        job_id=job_id,
        input_snapshot_id=input_snapshot_id,
        payload=post.model_dump(mode="json"),
        repair_attempts=repairs,
        metadata=metadata,
    )
