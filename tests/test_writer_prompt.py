from __future__ import annotations

from writeflow.agents.writer import WriterAgent


def build_prompt() -> str:
    agent = WriterAgent.__new__(WriterAgent)
    return agent._build_writing_prompt(
        topic="测试主题",
        thesis={
            "core_claim": "核心判断：问题的关键不是资源不足，而是代价被系统性转嫁。",
            "conflict_with_common_view": "普通观点认为这是管理效率问题。",
            "common_sense_overturned": "看似中立的治理方案并不中立。",
            "strongest_evidence": "具体制度安排和个案。",
            "most_dangerous_counterargument": "可能忽视执行层面的复杂性。",
        },
        materials=[{"material_type": "case", "content": "一个具体案例", "source": "mock"}],
        previous_rounds=[],
    )


def test_writer_prompt_requires_central_argument_progression():
    prompt = build_prompt()

    assert "core_claim" in prompt
    assert "核心判断：问题的关键不是资源不足，而是代价被系统性转嫁。" in prompt
    assert "一个主轴推进" in prompt
    assert "每个小节都服务于证明或检验这个核心判断" in prompt


def test_writer_prompt_contains_five_depth_questions():
    prompt = build_prompt()

    assert "这个现象背后的机制是什么？" in prompt
    assert "谁从中获益？" in prompt
    assert "谁承担代价？" in prompt
    assert "为什么常见解释是错的？" in prompt
    assert "这个判断能不能被具体例子证明？" in prompt


def test_writer_prompt_rejects_shallow_topic_survey():
    prompt = build_prompt()

    assert "不是写一篇主题综述" in prompt
    assert "禁止写成“主题综述式”文章" in prompt
    assert "不要为了显得全面而铺开多个浅层段落" in prompt
    assert "宁可少写层面" in prompt


def test_writer_revision_prompt_outputs_article_not_defense():
    agent = WriterAgent.__new__(WriterAgent)

    prompt = agent._build_revision_prompt(
        topic="测试主题",
        content="# 初稿\n\n正文。",
        thesis={"core_claim": "核心判断"},
        materials=[],
        judge_feedback={
            "failed_dimensions": ["层次穿透"],
            "recommendations": ["补强机制和代价承担者。"],
        },
        criticisms=[{"question": "缺少具体例子。"}],
    )

    assert "直接修订" in prompt
    assert "直接输出修订后的完整文章" in prompt
    assert "不要输出修改说明或辩护清单" in prompt
    assert "层次穿透" in prompt
    assert "缺少具体例子" in prompt
