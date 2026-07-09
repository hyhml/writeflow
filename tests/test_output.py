from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime

from writeflow.output import (
    AUTO_OUTPUT,
    build_output_paths,
    clean_final_article,
    save_article,
    save_scores,
    save_trace,
    serialize_scores,
    slugify_topic,
)


@dataclass
class DummyScores:
    a: float = 8
    b: float = 7

    def total(self) -> float:
        return self.a + self.b


@dataclass
class DummyResult:
    content: str = "正文"
    scores: DummyScores = field(default_factory=DummyScores)
    passed: bool = True
    pass_reason: str = "depth_passed"
    rounds: int = 1
    task_id: str = "task-1"
    trace_events: list = field(default_factory=list)


def test_slugify_topic_removes_path_separators_and_empty_values():
    assert slugify_topic("../测试 主题??") == "测试_主题"
    assert "/" not in slugify_topic("a/b")
    assert "\\" not in slugify_topic("a\\b")
    assert slugify_topic("???") == "article"


def test_build_auto_output_paths(tmp_path):
    now = datetime(2026, 7, 9, 10, 30, 1)

    paths = build_output_paths("中考 分流", AUTO_OUTPUT, base_dir=tmp_path, now=now)

    assert paths.article == tmp_path / "中考_分流_20260709_103001.md"
    assert paths.scores == tmp_path / "中考_分流_20260709_103001_scores.json"
    assert paths.trace == tmp_path / "中考_分流_20260709_103001_trace"


def test_build_explicit_output_path():
    paths = build_output_paths("任意主题", "custom/article.md")

    assert str(paths.article).replace("\\", "/") == "custom/article.md"
    assert str(paths.scores).replace("\\", "/") == "custom/article_scores.json"
    assert str(paths.trace).replace("\\", "/") == "custom/article_trace"


def test_save_article_and_scores(tmp_path):
    article_path = tmp_path / "outputs" / "article.md"
    scores_path = tmp_path / "outputs" / "article_scores.json"
    result = DummyResult()

    save_article(article_path, result.content)
    save_scores(scores_path, topic="主题", result=result, provider="minimax", model="MiniMax-M1")

    assert article_path.read_text(encoding="utf-8") == "正文"
    payload = json.loads(scores_path.read_text(encoding="utf-8"))
    assert payload["topic"] == "主题"
    assert payload["provider"] == "minimax"
    assert payload["pass"] is True
    assert payload["scores"]["total"] == 15


def test_serialize_scores_supports_plain_dict():
    assert serialize_scores({"a": 1, "b": 2}) == {"a": 1, "b": 2, "total": 3}


def test_clean_final_article_removes_model_process_text():
    raw = """<think>internal reasoning</think>
用户要求我作为编辑逐段处理。

# 正文标题

第一段正文。

【锋利度检测结果】
- 删除了某些表述
"""

    cleaned = clean_final_article(raw)

    assert cleaned.startswith("# 正文标题")
    assert "<think>" not in cleaned
    assert "用户要求我" not in cleaned
    assert "检测结果" not in cleaned


def test_save_trace_writes_agent_files(tmp_path):
    result = DummyResult(content="# 最终稿\n\n正文\n")
    result.trace_events = [
        {
            "stage": "researcher_materials",
            "agent": "researcher",
            "round": None,
            "input_summary": {},
            "output": {"materials": [{"content": "素材"}]},
            "created_at": "2026-07-09T10:00:00Z",
        },
        {
            "stage": "thesis_architect_brief",
            "agent": "thesis_architect",
            "round": None,
            "input_summary": {},
            "output": {
                "core_claim": "core claim",
                "conflict_with_common_view": "conflict",
                "common_sense_overturned": "overturned",
                "strongest_evidence": "evidence",
                "most_dangerous_counterargument": "counterargument",
            },
            "created_at": "2026-07-09T10:00:30Z",
        },
        {
            "stage": "writer_draft",
            "agent": "writer",
            "round": 1,
            "input_summary": {},
            "output": {"content": "# 初稿\n"},
            "created_at": "2026-07-09T10:01:00Z",
        },
        {
            "stage": "devil_advocate_criticisms",
            "agent": "devil_advocate",
            "round": 1,
            "input_summary": {},
            "output": {"criticisms": [{"question": "质疑"}]},
            "created_at": "2026-07-09T10:02:00Z",
        },
        {
            "stage": "writer_defense",
            "agent": "writer",
            "round": 1,
            "input_summary": {},
            "output": {"content": "辩护"},
            "created_at": "2026-07-09T10:03:00Z",
        },
        {
            "stage": "judge_result",
            "agent": "judge",
            "round": 1,
            "input_summary": {},
            "output": {"gate_result": {"passed": True}},
            "created_at": "2026-07-09T10:04:00Z",
        },
        {
            "stage": "editor_raw",
            "agent": "editor",
            "round": None,
            "input_summary": {},
            "output": {"raw_content": "<think>x</think>\n# 最终稿\n"},
            "created_at": "2026-07-09T10:05:00Z",
        },
    ]

    trace_dir = save_trace(tmp_path / "article_trace", topic="主题", result=result)

    assert (trace_dir / "00_manifest.json").exists()
    assert (trace_dir / "00_timeline.md").exists()
    assert (trace_dir / "01_researcher_materials.json").exists()
    assert (trace_dir / "02_thesis_architect_brief.json").exists()
    assert (trace_dir / "round_01_writer_draft.md").exists()
    assert (trace_dir / "round_01_devil_advocate_criticisms.json").exists()
    assert (trace_dir / "round_01_writer_defense.md").exists()
    assert (trace_dir / "round_01_judge_result.json").exists()
    assert (trace_dir / "final_editor_raw.md").exists()
    assert (trace_dir / "final_article.md").read_text(encoding="utf-8") == "# 最终稿\n\n正文\n"
