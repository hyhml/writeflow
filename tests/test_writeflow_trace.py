from __future__ import annotations

import asyncio

import pytest

from writeflow import config
from writeflow import writeflow as wf_module


class MockResearcher:
    def __init__(self, *args, **kwargs):
        pass

    async def process(self, input_data):
        return {"materials": [{"content": "素材", "source": "mock"}]}


class MockThesisArchitect:
    def __init__(self, *args, **kwargs):
        pass

    async def process(self, input_data):
        return {
            "core_claim": "core claim",
            "conflict_with_common_view": "conflict",
            "common_sense_overturned": "overturned common sense",
            "strongest_evidence": "strongest evidence",
            "most_dangerous_counterargument": "dangerous counterargument",
        }


class MockWriter:
    inputs = []

    def __init__(self, *args, **kwargs):
        pass

    async def process(self, input_data):
        MockWriter.inputs.append(input_data)
        if input_data.get("mode") == "defense":
            return {"content": "这是辩护内容"}
        return {"content": "# 初稿标题\n\n这是初稿。"}


class MockDevilAdvocate:
    def __init__(self, *args, **kwargs):
        pass

    async def process(self, input_data):
        return {"criticisms": [{"question": "这个论证需要更具体。"}]}


class MockJudge:
    def __init__(self, *args, **kwargs):
        pass

    async def process(self, input_data):
        return {
            "quality_scores": {
                name: 8 for name in wf_module.QualityScores.__dataclass_fields__.keys()
            }
        }


class MockEditor:
    def __init__(self, *args, **kwargs):
        pass

    async def process(self, input_data):
        return {
            "content": """<think>这里是模型思考过程</think>
用户要求我作为编辑逐段处理。

# 最终标题

这是清洗后的最终正文。

【锋利度检测结果】
- 我删除了一些表达
""",
            "usage": {},
        }


@pytest.fixture(autouse=True)
def clean_settings(monkeypatch):
    monkeypatch.setenv("WRITEFLOW_PROVIDER", "minimax")
    monkeypatch.setenv("MINIMAX_API_KEY", "fake-key")
    config.reset_settings_cache()
    monkeypatch.setattr(config, "_dotenv_loaded", True)
    yield
    config.reset_settings_cache()


def test_writeflow_records_agent_trace_and_cleans_final_article(monkeypatch):
    MockWriter.inputs = []
    monkeypatch.setattr(wf_module, "ResearcherAgent", MockResearcher)
    monkeypatch.setattr(wf_module, "ThesisArchitectAgent", MockThesisArchitect)
    monkeypatch.setattr(wf_module, "WriterAgent", MockWriter)
    monkeypatch.setattr(wf_module, "DevilAdvocateAgent", MockDevilAdvocate)
    monkeypatch.setattr(wf_module, "JudgeAgent", MockJudge)
    monkeypatch.setattr(wf_module, "EditorAgent", MockEditor)

    result = asyncio.run(async_write_once())

    stages = [event.stage for event in result.trace_events]
    agents = [event.agent for event in result.trace_events]

    assert stages == [
        "researcher_materials",
        "thesis_architect_brief",
        "writer_draft",
        "devil_advocate_criticisms",
        "writer_defense",
        "judge_result",
        "editor_raw",
        "final_article",
    ]
    assert "researcher" in agents
    assert "thesis_architect" in agents
    assert "writer" in agents
    assert "devil_advocate" in agents
    assert "judge" in agents
    assert "editor" in agents
    assert result.content.startswith("# 最终标题")
    assert "<think>" not in result.content
    assert "用户要求我" not in result.content
    assert "检测结果" not in result.content
    assert MockWriter.inputs[0]["thesis"]["core_claim"] == "core claim"


async def async_write_once():
    wf = wf_module.WriteFlow(max_rounds=1, min_rounds=1)
    return await wf.write("测试主题")
