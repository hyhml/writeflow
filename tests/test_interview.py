from __future__ import annotations

import asyncio
import json

from writeflow.interview import (
    FIXED_INTERVIEW_QUESTIONS,
    interview_json_path_for,
    interview_markdown_path_for,
    parse_followup_questions,
    run_interactive_interview,
    save_interview_record,
)


def test_interview_asks_fixed_questions_and_followups():
    answers = iter(
        [
            "我看到的反常现象",
            "这个案例的差异",
            "真正的问题根源",
            "具体解决方案",
            "不可丢失细节",
            "补充回答一",
            "补充回答二",
        ]
    )
    output_lines: list[str] = []

    record = asyncio.run(
        run_interactive_interview(
            "测试主题",
            input_func=lambda prompt: next(answers),
            output_func=output_lines.append,
            followup_provider=lambda topic, observation: [
                "第一个追问？",
                "第二个追问？",
            ],
        )
    )

    assert record["has_observation"] is True
    assert len(record["fixed_answers"]) == len(FIXED_INTERVIEW_QUESTIONS)
    assert len(record["followup_answers"]) == 2
    assert "我看到的反常现象" in record["human_observation"]
    assert "补充回答一" in record["human_observation"]
    assert any("补充追问" in line for line in output_lines)


def test_interview_blank_answers_do_not_call_followup_provider():
    answers = iter(["", "", "", "", ""])
    called = False

    def followup_provider(topic, observation):
        nonlocal called
        called = True
        return ["不应该出现的问题？"]

    record = asyncio.run(
        run_interactive_interview(
            "测试主题",
            input_func=lambda prompt: next(answers),
            output_func=lambda text: None,
            followup_provider=followup_provider,
        )
    )

    assert called is False
    assert record["has_observation"] is False
    assert record["human_observation"] == ""


def test_parse_followup_questions_from_json_and_lines():
    assert parse_followup_questions('{"questions": ["问题一？", "问题二？"]}') == [
        "问题一？",
        "问题二？",
    ]
    assert parse_followup_questions("1. 问题一？\n2. 问题二？") == [
        "问题一？",
        "问题二？",
    ]


def test_save_interview_record_writes_json_and_markdown(tmp_path):
    article_path = tmp_path / "article.md"
    json_path = interview_json_path_for(article_path)
    markdown_path = interview_markdown_path_for(article_path)
    record = {
        "topic": "测试主题",
        "created_at": "2026-07-11T00:00:00Z",
        "has_observation": True,
        "preset_observation": "",
        "fixed_answers": [
            {
                "kind": "fixed",
                "index": 1,
                "question": "我在本地看到的反常现象是什么？",
                "answer": "反常现象",
            }
        ],
        "followup_answers": [],
        "human_observation": "反常现象",
    }

    saved_json, saved_md = save_interview_record(record, json_path, markdown_path)

    assert saved_json == json_path
    assert saved_md == markdown_path
    assert json.loads(json_path.read_text(encoding="utf-8"))["topic"] == "测试主题"
    assert "反常现象" in markdown_path.read_text(encoding="utf-8")
