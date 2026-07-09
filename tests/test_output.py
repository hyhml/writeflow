from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime

from writeflow.output import (
    AUTO_OUTPUT,
    build_output_paths,
    save_article,
    save_scores,
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
    pass_reason: str = "excellent_dimensions"
    rounds: int = 1
    task_id: str = "task-1"


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


def test_build_explicit_output_path():
    paths = build_output_paths("任意主题", "custom/article.md")

    assert str(paths.article).replace("\\", "/") == "custom/article.md"
    assert str(paths.scores).replace("\\", "/") == "custom/article_scores.json"


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
