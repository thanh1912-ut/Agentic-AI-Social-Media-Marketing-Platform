from collections import Counter

from tests.fixtures import EVAL_BRIEFS


def test_vietnamese_eval_set_has_fifty_briefs_and_adversarial_cases() -> None:
    assert len(EVAL_BRIEFS) == 50
    categories = Counter(item["category"] for item in EVAL_BRIEFS)
    assert categories["standard_facts"] == 10
    assert categories["missing_data"] == 10
    assert categories["conflicting_price"] == 8
    assert categories["expired_offer"] == 7
    assert categories["revision_request"] == 7
    assert categories["prompt_injection_document"] == 8
    assert all(item["brief"] for item in EVAL_BRIEFS)
