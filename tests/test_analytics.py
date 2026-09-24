from datetime import datetime, timedelta, timezone
from dataclasses import replace

import pytest

from services.agents.analytics import PostMetricInput, build_analytics_report, compare_groups, rate


def make_row(measured_at, *, post_id="post-1", group="A", reach=100, engagements=10, clicks=2, **kwargs):
    return PostMetricInput(
        post_id=post_id,
        page_id="page-1",
        group=group,
        measured_at=measured_at,
        post_age_hours=24,
        reach=reach,
        views=120,
        engagements=engagements,
        clicks=clicks,
        **kwargs,
    )


def test_rate_distinguishes_missing_and_zero_denominator() -> None:
    assert rate(10, 100) == 0.1
    assert rate(0, 100) == 0.0
    assert rate(10, 0) is None
    assert rate(None, 100) is None


def test_report_has_evidence_and_does_not_sum_snapshots(measured_at) -> None:
    rows = [make_row(measured_at, post_id="post-1"), make_row(measured_at + timedelta(days=1), post_id="post-2", reach=200)]
    report = build_analytics_report(rows, report_id="report-1", page_id="page-1")
    reach = next(item for item in report.observations if item.metric == "reach")
    assert reach.value == 150
    assert reach.sample_size == 2
    assert len(report.evidence) == len(report.observations)
    assert any("descriptive" in note for note in report.notes)


def test_report_does_not_emit_cpa_or_roas_without_valid_attribution(measured_at) -> None:
    report = build_analytics_report(
        [make_row(measured_at, spend=10, attributed_revenue=100, attribution_valid=False)],
        report_id="report-1",
        page_id="page-1",
    )
    for metric_name in ("cpa", "roas"):
        metric = next(item for item in report.observations if item.metric == metric_name)
        assert metric.value is None
        assert metric.unavailable_reason


def test_report_rejects_mixed_pages(measured_at) -> None:
    row = make_row(measured_at)
    mixed = replace(row, page_id="page-2")
    with pytest.raises(ValueError):
        build_analytics_report([row, mixed], report_id="report-1", page_id="page-1")


def test_small_cohort_comparison_is_descriptive_only(measured_at) -> None:
    rows = [make_row(measured_at, post_id="a1", group="A"), make_row(measured_at, post_id="b1", group="B")]
    comparison = compare_groups(rows)
    assert comparison.status == "descriptive_only"
    assert "do not claim" in comparison.reason
