from __future__ import annotations

from writeflow.writeflow import TraceEventBuffer, WriteFlow


def test_record_trace_calls_trace_callback():
    received = []
    wf = object.__new__(WriteFlow)
    traces = TraceEventBuffer(received.append)

    wf._record_trace(
        traces,
        stage="researcher_materials",
        agent="researcher",
        input_summary={"topic": "测试主题"},
        output={"materials": ["素材"]},
    )

    assert len(traces) == 1
    assert len(received) == 1
    assert received[0].stage == "researcher_materials"
    assert received[0].output == {"materials": ["素材"]}


def test_record_trace_collects_human_intervention_from_callback():
    interventions = []
    wf = object.__new__(WriteFlow)
    traces = TraceEventBuffer(
        lambda _event: {"content": "请把地铁口这个场景写进去。"},
        human_interventions=interventions,
    )

    wf._record_trace(
        traces,
        stage="writer_draft",
        agent="writer",
        round_number=1,
        output={"content": "初稿"},
    )

    assert interventions == [
        {
            "content": "请把地铁口这个场景写进去。",
            "after_stage": "writer_draft",
            "after_agent": "writer",
            "round": 1,
            "attempt": 1,
            "created_at": interventions[0]["created_at"],
        }
    ]
