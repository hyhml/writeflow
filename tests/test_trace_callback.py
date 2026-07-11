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
