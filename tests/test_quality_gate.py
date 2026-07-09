from __future__ import annotations

from writeflow.core.quality_gate import QUALITY_DIMENSIONS, QualityGate


DIMS = list(QUALITY_DIMENSIONS.keys())


def scores(values: list[float]) -> dict[str, float]:
    return dict(zip(DIMS, values))


def test_rejects_any_failed_dimension():
    result = QualityGate().evaluate(scores([3.5, 8, 8, 8, 8, 8, 8]))

    assert result.passed is False
    assert result.reason == "failed_dimensions"
    assert DIMS[0] in result.failed_dimensions


def test_passes_when_two_dimensions_are_excellent():
    result = QualityGate().evaluate(scores([8, 8, 5, 5, 5, 5, 5]))

    assert result.passed is True
    assert result.reason == "excellent_dimensions"


def test_passes_by_total_score_even_with_one_excellent_dimension():
    result = QualityGate().evaluate(scores([9, 7.9, 7.9, 7.9, 7.9, 7.9, 7.9]))

    assert result.passed is True
    assert result.reason == "total_score"


def test_passes_when_all_dimensions_are_developed():
    result = QualityGate().evaluate(scores([6, 6, 6, 6, 6, 6, 6]))

    assert result.passed is True
    assert result.reason == "all_developed"


def test_returns_recommendations_when_not_meeting_threshold():
    result = QualityGate().evaluate(scores([5, 5, 5, 5, 5, 5, 5]))

    assert result.passed is False
    assert result.reason == "not_meets_threshold"
    assert result.recommendations
