from __future__ import annotations

import asyncio

import pytest

from writeflow import config
from writeflow import writeflow as wf_module


class MockObservationInterviewer:
    def __init__(self, *args, **kwargs):
        pass

    async def process(self, input_data):
        return {
            "missing_observation": False,
            "observation_brief": {
                "abnormal_phenomenon": "本地反常现象",
                "case_difference": "具体案例差异",
                "intuitive_root_cause": "真正问题根源",
                "concrete_solution": "具体方案",
                "must_preserve_details": ["不可丢失细节"],
            },
            "observation_questions": [],
            "must_preserve": ["不可丢失细节"],
            "source_status": "user_provided",
        }


class MockLocalVoiceCollector:
    def __init__(self, *args, **kwargs):
        pass

    async def process(self, input_data):
        return {
            "source_status": "from_context",
            "voices": [
                {
                    "speaker_type": "通勤者",
                    "location": "深圳",
                    "direct_quote": "这里节点很难走。",
                    "paraphrase": "",
                    "pain_point": "节点拥堵",
                    "local_specificity": "狭长地形",
                    "source_url": "https://example.com",
                    "confidence": 0.8,
                }
            ],
            "local_voice_brief": {
                "summary": "节点拥堵",
                "voices": [
                    {
                        "speaker_type": "通勤者",
                        "location": "深圳",
                        "direct_quote": "这里节点很难走。",
                        "pain_point": "节点拥堵",
                        "local_specificity": "狭长地形",
                    }
                ],
            },
        }


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
            "novelty_assets": [
                {
                    "type": "case",
                    "claim": "case novelty",
                    "why_different": "different",
                    "evidence_hint": "evidence",
                    "must_preserve": "detail",
                }
            ],
        }


class MockRealNoveltyGate:
    def __init__(self, *args, **kwargs):
        pass

    async def process(self, input_data):
        return {
            "passed": True,
            "pass_reason": "real_novelty_present",
            "novelty_assets": input_data["thesis"].get("novelty_assets", []),
            "missing_reason": "",
            "recommendations": [],
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
            },
            "depth_questions": [
                {
                    "target": "case",
                    "question": "案例是否讲透？",
                    "why_it_matters": "关系到案例新意。",
                    "status": "answered",
                    "required_revision": "",
                }
            ],
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
    monkeypatch.setattr(wf_module, "ObservationInterviewerAgent", MockObservationInterviewer)
    monkeypatch.setattr(wf_module, "LocalVoiceCollectorAgent", MockLocalVoiceCollector)
    monkeypatch.setattr(wf_module, "ResearcherAgent", MockResearcher)
    monkeypatch.setattr(wf_module, "ThesisArchitectAgent", MockThesisArchitect)
    monkeypatch.setattr(wf_module, "RealNoveltyGateAgent", MockRealNoveltyGate)
    monkeypatch.setattr(wf_module, "WriterAgent", MockWriter)
    monkeypatch.setattr(wf_module, "DevilAdvocateAgent", MockDevilAdvocate)
    monkeypatch.setattr(wf_module, "JudgeAgent", MockJudge)
    monkeypatch.setattr(wf_module, "EditorAgent", MockEditor)

    result = asyncio.run(async_write_once())

    stages = [event.stage for event in result.trace_events]
    agents = [event.agent for event in result.trace_events]

    assert stages == [
        "observation_interviewer",
        "local_voice_collector",
        "researcher_materials",
        "thesis_architect_brief",
        "real_novelty_gate",
        "writer_draft",
        "judge_precheck",
        "devil_advocate_criticisms",
        "writer_revision",
        "judge_final",
        "editor_raw",
        "final_article",
    ]
    assert "observation_interviewer" in agents
    assert "local_voice_collector" in agents
    assert "researcher" in agents
    assert "thesis_architect" in agents
    assert "real_novelty_gate" in agents
    assert "writer" in agents
    assert "devil_advocate" in agents
    assert "judge" in agents
    assert "editor" in agents
    assert result.content.startswith("# 最终标题")
    assert "<think>" not in result.content
    assert "用户要求我" not in result.content
    assert "检测结果" not in result.content
    assert MockWriter.inputs[0]["thesis"]["core_claim"] == "core claim"
    assert MockWriter.inputs[0]["observation_brief"]["abnormal_phenomenon"] == "本地反常现象"
    assert MockWriter.inputs[0]["novelty_assets"][0]["claim"] == "case novelty"
    assert MockWriter.inputs[1]["mode"] == "revision"
    assert not any(input_data.get("mode") == "defense" for input_data in MockWriter.inputs)


async def async_write_once():
    wf = wf_module.WriteFlow(max_rounds=1, min_rounds=1)
    return await wf.write("测试主题")


async def async_write_once_with_progress(events):
    wf = wf_module.WriteFlow(max_rounds=1, min_rounds=1)
    return await wf.write("测试主题", progress_callback=lambda event: events.append(event.to_dict()))


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
                scores["方案具体性"] = 4.9
            return {
                "quality_scores": scores,
                "depth_questions": [],
                "key_issues": ["解决方案仍然像口号。"],
                "recommendations": ["补入具体行动主体和代价承担者。"],
            }

    monkeypatch.setattr(wf_module, "ObservationInterviewerAgent", MockObservationInterviewer)
    monkeypatch.setattr(wf_module, "LocalVoiceCollectorAgent", MockLocalVoiceCollector)
    monkeypatch.setattr(wf_module, "ResearcherAgent", MockResearcher)
    monkeypatch.setattr(wf_module, "ThesisArchitectAgent", MockThesisArchitect)
    monkeypatch.setattr(wf_module, "RealNoveltyGateAgent", MockRealNoveltyGate)
    monkeypatch.setattr(wf_module, "WriterAgent", SequencedWriter)
    monkeypatch.setattr(wf_module, "DevilAdvocateAgent", CountingDevil)
    monkeypatch.setattr(wf_module, "JudgeAgent", SequencedJudge)
    monkeypatch.setattr(wf_module, "EditorAgent", MockEditor)

    result = asyncio.run(async_write_with_two_rounds())
    stages = [event.stage for event in result.trace_events]

    assert stages.index("judge_precheck") < stages.index("devil_advocate_criticisms")
    assert stages[:4] == [
        "observation_interviewer",
        "local_voice_collector",
        "researcher_materials",
        "thesis_architect_brief",
    ]
    assert stages[4:7] == [
        "real_novelty_gate",
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


def test_real_novelty_gate_failure_stops_before_writer(monkeypatch):
    class FailingNoveltyGate:
        def __init__(self, *args, **kwargs):
            pass

        async def process(self, input_data):
            return {
                "passed": False,
                "pass_reason": "no_real_novelty",
                "novelty_assets": [],
                "missing_reason": "no_real_novelty",
                "recommendations": ["重建 case/structure/solution 资产。"],
            }

    class CountingWriter(MockWriter):
        calls = 0

        async def process(self, input_data):
            CountingWriter.calls += 1
            return await super().process(input_data)

    monkeypatch.setattr(wf_module, "ObservationInterviewerAgent", MockObservationInterviewer)
    monkeypatch.setattr(wf_module, "LocalVoiceCollectorAgent", MockLocalVoiceCollector)
    monkeypatch.setattr(wf_module, "ResearcherAgent", MockResearcher)
    monkeypatch.setattr(wf_module, "ThesisArchitectAgent", MockThesisArchitect)
    monkeypatch.setattr(wf_module, "RealNoveltyGateAgent", FailingNoveltyGate)
    monkeypatch.setattr(wf_module, "WriterAgent", CountingWriter)
    monkeypatch.setattr(wf_module, "DevilAdvocateAgent", MockDevilAdvocate)
    monkeypatch.setattr(wf_module, "JudgeAgent", MockJudge)
    monkeypatch.setattr(wf_module, "EditorAgent", MockEditor)

    result = asyncio.run(async_write_once())
    stages = [event.stage for event in result.trace_events]

    assert result.passed is False
    assert result.pass_reason == "no_real_novelty"
    assert stages.count("thesis_architect_brief") == 2
    assert stages.count("real_novelty_gate") == 2
    assert "writer_draft" not in stages
    assert CountingWriter.calls == 0


def test_progress_callback_reports_novelty_retry_and_stop(monkeypatch):
    class FailingNoveltyGate:
        def __init__(self, *args, **kwargs):
            pass

        async def process(self, input_data):
            return {
                "passed": False,
                "pass_reason": "no_real_novelty",
                "novelty_assets": [],
                "missing_reason": "no_real_novelty",
                "recommendations": ["重建 case/structure/solution 资产。"],
            }

    monkeypatch.setattr(wf_module, "ObservationInterviewerAgent", MockObservationInterviewer)
    monkeypatch.setattr(wf_module, "LocalVoiceCollectorAgent", MockLocalVoiceCollector)
    monkeypatch.setattr(wf_module, "ResearcherAgent", MockResearcher)
    monkeypatch.setattr(wf_module, "ThesisArchitectAgent", MockThesisArchitect)
    monkeypatch.setattr(wf_module, "RealNoveltyGateAgent", FailingNoveltyGate)
    monkeypatch.setattr(wf_module, "WriterAgent", MockWriter)
    monkeypatch.setattr(wf_module, "DevilAdvocateAgent", MockDevilAdvocate)
    monkeypatch.setattr(wf_module, "JudgeAgent", MockJudge)
    monkeypatch.setattr(wf_module, "EditorAgent", MockEditor)

    events = []
    result = asyncio.run(async_write_once_with_progress(events))

    assert result.pass_reason == "no_real_novelty"
    novelty_failed = [
        event
        for event in events
        if event["step"] == "real_novelty_gate" and event["status"] == "failed"
    ]
    assert [event["attempt"] for event in novelty_failed] == [1, 2]
    assert any("不进入 Writer" in event["message"] for event in events)


def test_novelty_gate_retry_can_pass_and_enter_writer(monkeypatch):
    class RetryThenPassNoveltyGate:
        calls = 0

        def __init__(self, *args, **kwargs):
            pass

        async def process(self, input_data):
            RetryThenPassNoveltyGate.calls += 1
            if RetryThenPassNoveltyGate.calls == 1:
                return {
                    "passed": False,
                    "pass_reason": "no_real_novelty",
                    "novelty_assets": [],
                    "missing_reason": "no_real_novelty",
                    "recommendations": ["重建新意资产。"],
                }
            return {
                "passed": True,
                "pass_reason": "real_novelty_present",
                "novelty_assets": [
                    {
                        "type": "case",
                        "claim": "retry case novelty",
                        "why_different": "different",
                        "evidence_hint": "evidence",
                        "must_preserve": "detail",
                    }
                ],
                "missing_reason": "",
                "recommendations": [],
            }

    class CountingWriter(MockWriter):
        calls = 0

        async def process(self, input_data):
            CountingWriter.calls += 1
            return await super().process(input_data)

    RetryThenPassNoveltyGate.calls = 0
    CountingWriter.calls = 0
    monkeypatch.setattr(wf_module, "ObservationInterviewerAgent", MockObservationInterviewer)
    monkeypatch.setattr(wf_module, "LocalVoiceCollectorAgent", MockLocalVoiceCollector)
    monkeypatch.setattr(wf_module, "ResearcherAgent", MockResearcher)
    monkeypatch.setattr(wf_module, "ThesisArchitectAgent", MockThesisArchitect)
    monkeypatch.setattr(wf_module, "RealNoveltyGateAgent", RetryThenPassNoveltyGate)
    monkeypatch.setattr(wf_module, "WriterAgent", CountingWriter)
    monkeypatch.setattr(wf_module, "DevilAdvocateAgent", MockDevilAdvocate)
    monkeypatch.setattr(wf_module, "JudgeAgent", MockJudge)
    monkeypatch.setattr(wf_module, "EditorAgent", MockEditor)

    result = asyncio.run(async_write_once())
    stages = [event.stage for event in result.trace_events]

    assert result.passed is True
    assert RetryThenPassNoveltyGate.calls == 2
    assert CountingWriter.calls > 0
    assert stages.count("real_novelty_gate") == 2
    assert "writer_draft" in stages


def test_editor_is_not_called_when_final_depth_judge_fails(monkeypatch):
    class AlwaysFailJudge:
        def __init__(self, *args, **kwargs):
            pass

        async def process(self, input_data):
            scores = {
                name: 8 for name in wf_module.QualityScores.__dataclass_fields__.keys()
            }
            scores["层次穿透"] = 4.9
            return {
                "quality_scores": scores,
                "depth_questions": [],
                "key_issues": ["层次穿透不足。"],
                "recommendations": ["重写机制解释。"],
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

    monkeypatch.setattr(wf_module, "ObservationInterviewerAgent", MockObservationInterviewer)
    monkeypatch.setattr(wf_module, "LocalVoiceCollectorAgent", MockLocalVoiceCollector)
    monkeypatch.setattr(wf_module, "ResearcherAgent", MockResearcher)
    monkeypatch.setattr(wf_module, "ThesisArchitectAgent", MockThesisArchitect)
    monkeypatch.setattr(wf_module, "RealNoveltyGateAgent", MockRealNoveltyGate)
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
