"""Analytics calculations that never invent missing data.

This module intentionally contains no LLM calls.  Insight/recommendation
agents consume its report and evidence IDs; they do not recalculate KPIs in
natural language.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from packages.contracts import AnalyticsEvidence, AnalyticsReport, MetricObservation


@dataclass(frozen=True)
class PostMetricInput:
    post_id: str
    page_id: str
    group: str
    measured_at: datetime
    post_age_hours: int
    reach: int | None = None
    views: int | None = None
    followers: int | None = None
    engagements: int | None = None
    clicks: int | None = None
    spend: float | None = None
    attributed_revenue: float | None = None
    attribution_valid: bool = False


def rate(numerator: float | int | None, denominator: float | int | None) -> float | None:
    """Return unavailable for missing or zero denominators, never zero."""

    if numerator is None or denominator is None or denominator == 0:
        return None
    return float(numerator) / float(denominator)


def _period(rows: list[PostMetricInput]) -> tuple[datetime, datetime]:
    if not rows:
        now = datetime.now(timezone.utc)
        return now, now
    return min(row.measured_at for row in rows), max(row.measured_at for row in rows)


def _coverage(values: list[float | int | None], total: int) -> float:
    return (sum(value is not None for value in values) / total) if total else 0.0


def _observation(
    metric: str,
    values: list[float | int | None],
    rows: list[PostMetricInput],
    *,
    numerator: float | None = None,
    denominator: float | None = None,
) -> MetricObservation:
    available = [value for value in values if value is not None]
    start, end = _period(rows)
    value = (sum(available) / len(available)) if available else None
    reason = None if value is not None else "insufficient_data"
    return MetricObservation(
        metric=metric,
        value=value,
        numerator=numerator,
        denominator=denominator,
        sample_size=len(rows),
        coverage=_coverage(values, len(rows)),
        measured_from=start,
        measured_to=end,
        unavailable_reason=reason,
    )


def _ratio_observation(
    metric: str,
    numerators: list[float | int | None],
    denominators: list[float | int | None],
    rows: list[PostMetricInput],
) -> MetricObservation:
    pairs = [(n, d) for n, d in zip(numerators, denominators) if n is not None and d not in (None, 0)]
    numerator = sum(pair[0] for pair in pairs) if pairs else None
    denominator = sum(pair[1] for pair in pairs) if pairs else None
    value = rate(numerator, denominator)
    start, end = _period(rows)
    return MetricObservation(
        metric=metric,
        value=value,
        numerator=numerator,
        denominator=denominator,
        sample_size=len(rows),
        coverage=(len(pairs) / len(rows)) if rows else 0.0,
        measured_from=start,
        measured_to=end,
        unavailable_reason=None if value is not None else "insufficient_data_or_zero_denominator",
    )


def _evidence_id(page_id: str, metric: str, rows: list[PostMetricInput]) -> str:
    material = "|".join(sorted(row.post_id for row in rows))
    digest = hashlib.sha256(f"{page_id}|{metric}|{material}".encode()).hexdigest()[:12]
    return f"ev:{digest}"


def build_analytics_report(
    rows: list[PostMetricInput],
    *,
    report_id: str,
    page_id: str,
    min_post_age_hours: int | None = None,
    max_post_age_hours: int | None = None,
) -> AnalyticsReport:
    """Aggregate like-for-like posts into a report with traceable evidence.

    Rows from another page are rejected.  The caller must provide one page per
    report, matching the backend's metric definition and cohort window.
    """

    if any(row.page_id != page_id for row in rows):
        raise ValueError("analytics report cannot mix pages")
    if min_post_age_hours is not None and min_post_age_hours < 0:
        raise ValueError("min_post_age_hours must be non-negative")
    if max_post_age_hours is not None and max_post_age_hours < 0:
        raise ValueError("max_post_age_hours must be non-negative")
    if min_post_age_hours is not None and max_post_age_hours is not None and min_post_age_hours > max_post_age_hours:
        raise ValueError("min_post_age_hours cannot exceed max_post_age_hours")

    filtered = [
        row
        for row in rows
        if (min_post_age_hours is None or row.post_age_hours >= min_post_age_hours)
        and (max_post_age_hours is None or row.post_age_hours <= max_post_age_hours)
    ]
    observations = [
        _observation("reach", [row.reach for row in filtered], filtered),
        _observation("views", [row.views for row in filtered], filtered),
        _ratio_observation("engagement_rate_by_reach", [row.engagements for row in filtered], [row.reach for row in filtered], filtered),
        _ratio_observation("click_rate_by_reach", [row.clicks for row in filtered], [row.reach for row in filtered], filtered),
    ]

    # CPA/ROAS are only emitted with cost and valid attribution.  A missing
    # value is represented as unavailable, never as a misleading zero.
    valid_attribution = [row for row in filtered if row.attribution_valid]
    spend = [row.spend for row in valid_attribution]
    revenue = [row.attributed_revenue for row in valid_attribution]
    cpa_denominator = sum(row.clicks for row in valid_attribution if row.clicks is not None)
    total_spend = sum(value for value in spend if value is not None) if all(value is not None for value in spend) and spend else None
    total_revenue = sum(value for value in revenue if value is not None) if all(value is not None for value in revenue) and revenue else None
    start, end = _period(filtered)
    observations.extend(
        [
            MetricObservation(
                metric="cpa",
                value=rate(total_spend, cpa_denominator),
                numerator=total_spend,
                denominator=cpa_denominator or None,
                sample_size=len(filtered),
                coverage=(len(valid_attribution) / len(filtered)) if filtered else 0.0,
                measured_from=start,
                measured_to=end,
                unavailable_reason=None if rate(total_spend, cpa_denominator) is not None else "missing_cost_or_valid_attribution",
            ),
            MetricObservation(
                metric="roas",
                value=rate(total_revenue, total_spend),
                numerator=total_revenue,
                denominator=total_spend,
                sample_size=len(filtered),
                coverage=(len(valid_attribution) / len(filtered)) if filtered else 0.0,
                measured_from=start,
                measured_to=end,
                unavailable_reason=None if rate(total_revenue, total_spend) is not None else "missing_cost_or_valid_attribution",
            ),
        ]
    )

    evidence = [
        AnalyticsEvidence(
            evidence_id=_evidence_id(page_id, observation.metric, filtered),
            description=f"{observation.metric}: n={observation.sample_size}, coverage={observation.coverage:.0%}",
            post_ids=[row.post_id for row in filtered],
            metric_names=[observation.metric],
        )
        for observation in observations
    ]
    notes = [
        "Metrics are descriptive and do not establish causality.",
        "Lifetime snapshots are not summed; each input row is treated as one comparable measurement.",
    ]
    if len(filtered) < 5:
        notes.append("Fewer than 5 posts: use this report for description or exploratory testing only.")
    return AnalyticsReport(
        report_id=report_id,
        page_id=page_id,
        period_start=start,
        period_end=end,
        observations=observations,
        evidence=evidence,
        notes=notes,
    )


@dataclass(frozen=True)
class GroupComparison:
    metric: str
    groups: dict[str, float | None]
    status: Literal["descriptive_only", "exploratory"]
    reason: str


def compare_groups(
    rows: list[PostMetricInput],
    *,
    metric: Literal["reach", "views", "engagement_rate_by_reach", "click_rate_by_reach"] = "reach",
    min_posts_for_comparison: int = 5,
) -> GroupComparison:
    """Compare cohorts descriptively and suppress winner claims for small n."""

    if min_posts_for_comparison < 1:
        raise ValueError("min_posts_for_comparison must be positive")
    grouped: dict[str, list[PostMetricInput]] = defaultdict(list)
    for row in rows:
        grouped[row.group].append(row)
    values: dict[str, float | None] = {}
    for group, group_rows in grouped.items():
        if metric == "reach":
            values[group] = _observation(metric, [row.reach for row in group_rows], group_rows).value
        elif metric == "views":
            values[group] = _observation(metric, [row.views for row in group_rows], group_rows).value
        elif metric == "engagement_rate_by_reach":
            values[group] = _ratio_observation(metric, [row.engagements for row in group_rows], [row.reach for row in group_rows], group_rows).value
        else:
            values[group] = _ratio_observation(metric, [row.clicks for row in group_rows], [row.reach for row in group_rows], group_rows).value
    small_group = any(len(group_rows) < min_posts_for_comparison for group_rows in grouped.values())
    return GroupComparison(
        metric=metric,
        groups=values,
        status="descriptive_only" if small_group else "exploratory",
        reason=(
            f"At least one group has fewer than {min_posts_for_comparison} posts; do not claim a better group."
            if small_group
            else "Group difference is descriptive and should be validated by an experiment."
        ),
    )
