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
        if input_data.get("mode") == "revision":
            return {"content": "# 修订标题\n\n这是修订后的正文。"}
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
        "judge_precheck",
        "devil_advocate_criticisms",
        "writer_revision",
        "judge_final",
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
    assert MockWriter.inputs[1]["mode"] == "revision"
    assert not any(input_data.get("mode") == "defense" for input_data in MockWriter.inputs)


async def async_write_once():
    wf = wf_module.WriteFlow(max_rounds=1, min_rounds=1)
    return await wf.write("测试主题")


def test_precheck_failure_skips_devil_and_sends_feedback_to_next_draft(monkeypatch):
    class SequencedWriter(MockWriter):
        inputs = []

        async def process(self, input_data):
            SequencedWriter.inputs.append(input_data)
            if input_data.get("mode") == "revision":
                return {"content": "# 修订稿\n\n修订后的正文。"}
            return {"content": f"# 第{input_data.get('round')}轮初稿\n\n正文。"}

    class CountingDevil:
        calls = 0

        def __init__(self, *args, **kwargs):
            pass

        async def process(self, input_data):
            CountingDevil.calls += 1
            return {"criticisms": [{"question": "需要更具体的例子。"}]}

    class SequencedJudge:
        calls = 0

        def __init__(self, *args, **kwargs):
            pass

        async def process(self, input_data):
            SequencedJudge.calls += 1
            scores = {
                name: 8 for name in wf_module.QualityScores.__dataclass_fields__.keys()
            }
            if SequencedJudge.calls == 1:
                scores["方案具体性"] = 5
            return {
                "quality_scores": scores,
                "key_issues": ["解决方案仍然像口号。"],
                "recommendations": ["补入具体行动主体和代价承担者。"],
            }

    monkeypatch.setattr(wf_module, "ResearcherAgent", MockResearcher)
    monkeypatch.setattr(wf_module, "ThesisArchitectAgent", MockThesisArchitect)
    monkeypatch.setattr(wf_module, "WriterAgent", SequencedWriter)
    monkeypatch.setattr(wf_module, "DevilAdvocateAgent", CountingDevil)
    monkeypatch.setattr(wf_module, "JudgeAgent", SequencedJudge)
    monkeypatch.setattr(wf_module, "EditorAgent", MockEditor)

    result = asyncio.run(async_write_with_two_rounds())
    stages = [event.stage for event in result.trace_events]

    assert stages.index("judge_precheck") < stages.index("devil_advocate_criticisms")
    assert stages[:4] == [
        "researcher_materials",
        "thesis_architect_brief",
        "writer_draft",
        "judge_precheck",
    ]
    assert stages.count("writer_draft") == 2
    assert stages.count("devil_advocate_criticisms") == 1
    assert CountingDevil.calls == 1
    assert SequencedWriter.inputs[1]["mode"] == "write"
    assert SequencedWriter.inputs[1]["rewrite_feedback"]["failed_dimensions"] == [
        "方案具体性"
    ]
    assert SequencedWriter.inputs[2]["mode"] == "revision"
    assert SequencedJudge.calls == 3
    assert result.passed is True


async def async_write_with_two_rounds():
    wf = wf_module.WriteFlow(max_rounds=2, min_rounds=1)
    return await wf.write("测试主题")


def test_editor_is_not_called_when_final_depth_judge_fails(monkeypatch):
    class AlwaysFailJudge:
        def __init__(self, *args, **kwargs):
            pass

        async def process(self, input_data):
            scores = {
                name: 8 for name in wf_module.QualityScores.__dataclass_fields__.keys()
            }
            scores["新判断"] = 5
            return {
                "quality_scores": scores,
                "key_issues": ["没有新判断。"],
                "recommendations": ["重写核心判断。"],
            }

    class CountingDevil:
        calls = 0

        def __init__(self, *args, **kwargs):
            pass

        async def process(self, input_data):
            CountingDevil.calls += 1
            return {"criticisms": [{"question": "不会被调用"}]}

    class CountingEditor(MockEditor):
        calls = 0

        async def process(self, input_data):
            CountingEditor.calls += 1
            return await super().process(input_data)

    monkeypatch.setattr(wf_module, "ResearcherAgent", MockResearcher)
    monkeypatch.setattr(wf_module, "ThesisArchitectAgent", MockThesisArchitect)
    monkeypatch.setattr(wf_module, "WriterAgent", MockWriter)
    monkeypatch.setattr(wf_module, "DevilAdvocateAgent", CountingDevil)
    monkeypatch.setattr(wf_module, "JudgeAgent", AlwaysFailJudge)
    monkeypatch.setattr(wf_module, "EditorAgent", CountingEditor)

    result = asyncio.run(async_write_once())
    stages = [event.stage for event in result.trace_events]

    assert result.passed is False
    assert result.pass_reason == "shallow_dimensions"
    assert "devil_advocate_criticisms" not in stages
    assert "editor_raw" not in stages
    assert CountingDevil.calls == 0
    assert CountingEditor.calls == 0
