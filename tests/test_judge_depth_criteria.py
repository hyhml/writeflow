from __future__ import annotations

from writeflow.agents.judge import JUDGE_SYSTEM_PROMPT, JudgeAgent


def test_judge_prompt_contains_depth_questions():
    for question in [
        "有没有新判断？",
        "有没有概念堆砌？",
        "有没有一句话删掉后文章更强？",
        "有没有每段都只讲到第一层？",
        "解决方案是否只是口号？",
    ]:
        assert question in JUDGE_SYSTEM_PROMPT

    assert "批判锋芒" not in JUDGE_SYSTEM_PROMPT
    assert "理论深度" not in JUDGE_SYSTEM_PROMPT


def test_judge_prompt_builds_depth_review_request():
    agent = JudgeAgent.__new__(JudgeAgent)

    prompt = agent._build_evaluation_prompt(
        topic="测试主题",
        content="文章正文",
        criticisms=[],
        defenses="",
        materials=[],
    )

    assert "判浅" in prompt
    assert "新判断" in prompt
    assert "方案具体性" in prompt


def test_judge_parser_normalizes_depth_scores_and_passes():
    agent = JudgeAgent.__new__(JudgeAgent)
    raw = """
    {
      "quality_scores": {
        "新判断": 7,
        "概念克制": 6,
        "句子必要性": 6,
        "层次穿透": 7,
        "方案具体性": 6
      }
    }
    """

    result = agent._parse_evaluation(raw)

    assert result["passed"] is True
    assert result["pass_reason"] == "depth_passed"
    assert result["failed_dimensions"] == []


def test_judge_parser_rejects_shallow_dimension():
    agent = JudgeAgent.__new__(JudgeAgent)
    raw = """
    {
      "quality_scores": {
        "新判断": 8,
        "概念克制": 8,
        "句子必要性": 8,
        "层次穿透": 8,
        "方案具体性": 5
      }
    }
    """

    result = agent._parse_evaluation(raw)

    assert result["passed"] is False
    assert result["pass_reason"] == "shallow_dimensions"
    assert result["failed_dimensions"] == ["方案具体性"]
