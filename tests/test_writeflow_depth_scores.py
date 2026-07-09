from __future__ import annotations

from writeflow import writeflow as wf_module


def test_writeflow_parses_new_depth_score_fields():
    flow = wf_module.WriteFlow.__new__(wf_module.WriteFlow)

    scores = flow._parse_scores_from_result(
        {
            "quality_scores": {
                "新判断": "7",
                "概念克制": 6,
                "句子必要性": 8,
                "层次穿透": 6.5,
                "方案具体性": 6,
            }
        }
    )

    assert scores.to_dict() == {
        "新判断": 7.0,
        "概念克制": 6.0,
        "句子必要性": 8.0,
        "层次穿透": 6.5,
        "方案具体性": 6.0,
    }


def test_writeflow_ignores_old_seven_dimension_score_fields():
    flow = wf_module.WriteFlow.__new__(wf_module.WriteFlow)

    scores = flow._parse_scores_from_result(
        {
            "quality_scores": {
                "批判锋芒": 10,
                "理论深度": 10,
                "洞察力度": 10,
                "论证严谨性": 10,
                "社会关联度": 10,
                "文字穿透力": 10,
                "学术规范性": 10,
            }
        }
    )

    assert scores.total() == 0
    assert set(scores.to_dict()) == {"新判断", "概念克制", "句子必要性", "层次穿透", "方案具体性"}
