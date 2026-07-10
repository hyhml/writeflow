from __future__ import annotations

from writeflow.agents.judge import JUDGE_SYSTEM_PROMPT, JudgeAgent


def test_judge_prompt_contains_depth_questions():
    for question in [
        "有没有概念堆砌？",
        "有没有一句话删掉后文章更强？",
        "有没有每段都只讲到第一层？",
        "解决方案是否只是口号？",
    ]:
        assert question in JUDGE_SYSTEM_PROMPT

    assert "不要再给“新判断”打分" in JUDGE_SYSTEM_PROMPT
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
        thesis={"core_claim": "核心判断"},
        novelty_assets=[{"type": "case", "claim": "具体案例新意"}],
    )

    assert "判浅" in prompt
    assert "真实新意资产" in prompt
    assert "方案具体性" in prompt
    assert "深圳地形和交通节点的关系讲透了吗？" in prompt


def test_judge_parser_normalizes_depth_scores_and_passes():
    agent = JudgeAgent.__new__(JudgeAgent)
    raw = """
    {
      "quality_scores": {
        "概念克制": 6,
        "句子必要性": 6,
        "层次穿透": 7,
        "方案具体性": 6
      },
      "depth_questions": [
        {
          "target": "case",
          "question": "案例是否讲透？",
          "why_it_matters": "关系到案例新意。",
          "status": "answered",
          "required_revision": ""
        }
      ]
    }
    """

    result = agent._parse_evaluation(raw)

    assert result["passed"] is True
    assert result["pass_reason"] == "depth_passed"
    assert result["failed_dimensions"] == []
    assert result["depth_questions"][0]["status"] == "answered"


def test_judge_parser_rejects_shallow_dimension():
    agent = JudgeAgent.__new__(JudgeAgent)
    raw = """
    {
      "quality_scores": {
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


def test_judge_parser_rejects_unanswered_depth_question():
    agent = JudgeAgent.__new__(JudgeAgent)
    raw = """
    {
      "quality_scores": {
        "概念克制": 8,
        "句子必要性": 8,
        "层次穿透": 8,
        "方案具体性": 8
      },
      "depth_questions": [
        {
          "target": "solution",
          "question": "划转车道的执行阻力讲了吗？",
          "why_it_matters": "关系到方案是否只是口号。",
          "status": "missing",
          "required_revision": "补充执行阻力和代价承担者。"
        }
      ]
    }
    """

    result = agent._parse_evaluation(raw)

    assert result["passed"] is False
    assert result["pass_reason"] == "unanswered_depth_questions"
    assert "补充执行阻力" in result["recommendations"][0]
