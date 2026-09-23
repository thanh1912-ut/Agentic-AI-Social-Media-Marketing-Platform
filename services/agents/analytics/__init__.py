"""Deterministic metric calculations and evidence-backed reporting."""

from .metrics import (
    PostMetricInput,
    build_analytics_report,
    compare_groups,
    rate,
)

__all__ = ["PostMetricInput", "build_analytics_report", "compare_groups", "rate"]
