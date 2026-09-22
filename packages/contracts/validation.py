"""Bounded structured-output parsing for model adapters."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from pydantic import BaseModel, ValidationError

ModelT = TypeVar("ModelT", bound=BaseModel)


def parse_with_one_repair(
    payload: object,
    model: type[ModelT],
    repair: Callable[[object, ValidationError], object] | None = None,
) -> tuple[ModelT, int]:
    """Validate once and optionally apply exactly one repair attempt.

    The caller receives the number of repair attempts so it can instrument
    quality/cost.  A second model call is never made by this helper.
    """

    try:
        return model.model_validate(payload), 0
    except ValidationError as first_error:
        if repair is None:
            raise
        repaired = repair(payload, first_error)
        return model.model_validate(repaired), 1
