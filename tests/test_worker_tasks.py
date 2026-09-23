from dataclasses import dataclass

import asyncio

import pytest

from packages.contracts import BrandProfile, CampaignBrief, GeneratedPost
from services.agents.brand_agent import BrandAgent
from services.agents.content_agent import ContentAgent
from services.worker.ai_tasks import run_brand_profile_task, run_content_task
from services.worker import tasks


@dataclass
class Model:
    response: object

    def generate(self, *, system_prompt, input_payload, response_model):
        return self.response, None


def test_worker_task_returns_snapshot_and_versioned_payload() -> None:
    profile = BrandProfile(brand_id="brand-1", business="Bếp Mộc", requires_confirmation=True)
    brand_result = run_brand_profile_task(
        job_id="job-1",
        input_snapshot_id="snap-1",
        agent=BrandAgent(Model(profile)),
        brand_id="brand-1",
        business_hint="Bếp Mộc",
        context=[],
    )
    assert brand_result.task_name == "brand_profile"
    assert brand_result.input_snapshot_id == "snap-1"

    confirmed = profile.model_copy(update={"requires_confirmation": False})
    post = GeneratedPost(base_version="model", version=1, channel="facebook", caption="Bữa cơm Việt.")
    content_result = run_content_task(
        job_id="job-2",
        input_snapshot_id="snap-2",
        agent=ContentAgent(Model(post)),
        profile=confirmed,
        brief=CampaignBrief(objective="Nhận biết", audience="Gia đình", channel="facebook"),
        base_version="post-v1",
        next_version=2,
        context=[],
    )
    assert content_result.payload["base_version"] == "post-v1"
    assert content_result.payload["version"] == 2


def test_runtime_brand_profile_uses_configured_deepseek_adapter(monkeypatch) -> None:
    class FactoryObserved(RuntimeError):
        pass

    def observe_factory():
        raise FactoryObserved("deepseek adapter factory reached")

    monkeypatch.setattr(tasks, "configured_structured_model", observe_factory)
    with pytest.raises(FactoryObserved, match="factory reached"):
        asyncio.run(
            tasks._run_brand_profile(
                job_id="job-1",
                company_id="workspace-1",
                created_by="user-1",
                document_ids=[],
                all_document_ids=[],
                failed_documents=[],
                image_ids=[],
                ingestion_warnings=[],
                index=None,
                agent=None,
            )
        )
