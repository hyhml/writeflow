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
        observation_brief={
            "abnormal_phenomenon": "本地出现反常交通冲突",
            "case_difference": "这个案例和普通讨论不同",
        },
        local_voice_brief={
            "voices": [
                {
                    "speaker_type": "通勤者",
                    "location": "深圳",
                    "direct_quote": "这里通勤节点很难走。",
                    "pain_point": "节点拥堵",
                    "local_specificity": "狭长地形",
                }
            ]
        },
        novelty_assets=[
            {
                "type": "case",
                "claim": "深圳狭长地形使交通节点矛盾更尖锐",
                "why_different": "不是泛泛批判算法",
                "evidence_hint": "节点和禁摩路段",
                "must_preserve": "狭长地形",
            }
        ],
        depth_questions=[
            {
                "target": "case",
                "question": "深圳地形和交通节点的关系讲透了吗？",
                "status": "not_deep_enough",
                "required_revision": "补清地形和节点。",
            }
        ],
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


def test_writer_prompt_includes_observation_voice_and_novelty_assets():
    prompt = build_prompt()

    assert "本地出现反常交通冲突" in prompt
    assert "这里通勤节点很难走" in prompt
    assert "深圳狭长地形使交通节点矛盾更尖锐" in prompt
    assert "深圳地形和交通节点的关系讲透了吗？" in prompt


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
            "depth_questions": [
                {
                    "target": "solution",
                    "question": "方案阻力讲了吗？",
                    "status": "missing",
                    "required_revision": "补充执行阻力。",
                }
            ],
        },
        criticisms=[{"question": "缺少具体例子。"}],
        novelty_assets=[
            {
                "type": "solution",
                "claim": "划转一条车道给非机动车",
                "why_different": "不是微更新",
                "evidence_hint": "路权重分配",
                "must_preserve": "车道划转",
            }
        ],
        depth_questions=[
            {
                "target": "solution",
                "question": "方案阻力讲了吗？",
                "status": "missing",
                "required_revision": "补充执行阻力。",
            }
        ],
    )

    assert "直接修订" in prompt
    assert "直接输出修订后的完整文章" in prompt
    assert "不要输出修改说明或辩护清单" in prompt
    assert "层次穿透" in prompt
    assert "缺少具体例子" in prompt
    assert "方案阻力讲了吗？" in prompt
    assert "划转一条车道给非机动车" in prompt
