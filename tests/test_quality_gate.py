from __future__ import annotations

from writeflow.core.quality_gate import QUALITY_DIMENSIONS, QualityGate


DIMS = list(QUALITY_DIMENSIONS.keys())


def scores(values: list[float]) -> dict[str, float]:
    return dict(zip(DIMS, values))


def test_depth_gate_uses_four_shallow_check_dimensions():
    assert DIMS == ["概念克制", "句子必要性", "层次穿透", "方案具体性"]


def test_rejects_any_dimension_below_six():
    result = QualityGate().evaluate(scores([6, 5.9, 10, 10]))

    assert result.passed is False
    assert result.reason == "shallow_dimensions"
    assert "句子必要性" in result.failed_dimensions


def test_passes_only_when_all_dimensions_reach_six():
    result = QualityGate().evaluate(scores([6, 6, 6, 6]))

    assert result.passed is True
    assert result.reason == "depth_passed"


def test_high_total_score_no_longer_overrides_shallow_dimension():
    result = QualityGate().evaluate(scores([10, 10, 10, 5]))

    assert result.passed is False
    assert result.reason == "shallow_dimensions"
    assert "方案具体性" in result.failed_dimensions


def test_excellent_dimensions_no_longer_override_shallow_dimension():
    result = QualityGate().evaluate(scores([9, 5, 5, 5]))

    assert result.passed is False
    assert result.reason == "shallow_dimensions"
    assert result.recommendations


def test_unanswered_depth_question_blocks_passing_scores():
    result = QualityGate().evaluate(
        scores([6, 6, 6, 6]),
        depth_questions=[
            {
                "target": "case",
                "question": "深圳地形和交通节点的关系讲透了吗？",
                "why_it_matters": "这是案例新意的根。",
                "status": "not_deep_enough",
                "required_revision": "补清地形、节点和路权冲突。",
            }
        ],
    )

    assert result.passed is False
    assert result.reason == "unanswered_depth_questions"
    assert result.depth_questions[0]["target"] == "case"
