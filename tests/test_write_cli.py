from __future__ import annotations

import asyncio
import importlib.util
from dataclasses import dataclass, field
import sys
from pathlib import Path

from writeflow import config

ROOT = Path(__file__).resolve().parents[1]


def load_write_module():
    spec = importlib.util.spec_from_file_location("write_entry", ROOT / "write.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_write_py_exits_cleanly_without_api_key(monkeypatch, capsys):
    monkeypatch.setenv("WRITEFLOW_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-your-deepseek-key")
    monkeypatch.delenv("WRITEFLOW_API_KEY", raising=False)
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(sys, "argv", ["write.py", "测试主题"])
    config.reset_settings_cache()
    monkeypatch.setattr(config, "_dotenv_loaded", True)

    module = load_write_module()
    exit_code = asyncio.run(module.main())
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "API Key" in output


@dataclass
class DummyScores:
    a: float = 8
    b: float = 8

    def total(self):
        return self.a + self.b

    def to_dict(self):
        return {"a": self.a, "b": self.b}


@dataclass
class DummyResult:
    content: str = "# 最终稿\n\n正文\n"
    scores: DummyScores = field(default_factory=DummyScores)
    passed: bool = True
    pass_reason: str = "depth_passed"
    rounds: int = 1
    task_id: str = "task-1"
    trace_events: list = field(
        default_factory=lambda: [
            {
                "stage": "writer_draft",
                "agent": "writer",
                "round": 1,
                "input_summary": {},
                "output": {"content": "# 初稿\n"},
                "created_at": "2026-07-09T10:00:00Z",
            }
        ]
    )


class DummyWriteFlow:
    async def write(self, topic):
        return DummyResult()


def test_write_py_saves_article_scores_and_trace(monkeypatch, tmp_path):
    output_path = tmp_path / "article.md"
    monkeypatch.setenv("WRITEFLOW_PROVIDER", "minimax")
    monkeypatch.setenv("MINIMAX_API_KEY", "fake-key")
    monkeypatch.delenv("WRITEFLOW_API_KEY", raising=False)
    monkeypatch.setattr(sys, "argv", ["write.py", "测试主题", "-o", str(output_path)])
    config.reset_settings_cache()
    monkeypatch.setattr(config, "_dotenv_loaded", True)

    module = load_write_module()
    monkeypatch.setattr(module, "WriteFlow", lambda: DummyWriteFlow())

    exit_code = asyncio.run(module.main())

    assert exit_code == 0
    assert output_path.read_text(encoding="utf-8") == "# 最终稿\n\n正文\n"
    assert (tmp_path / "article_scores.json").exists()
    trace_dir = tmp_path / "article_trace"
    assert (trace_dir / "00_manifest.json").exists()
    assert (trace_dir / "00_timeline.md").exists()
    assert (trace_dir / "round_01_writer_draft.md").exists()
    assert (trace_dir / "final_article.md").exists()
