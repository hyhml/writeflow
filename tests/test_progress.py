from __future__ import annotations

import io
import json

from writeflow.progress import ProgressEvent, ProgressReporter, format_progress_event


def test_format_progress_event_includes_step_and_message():
    event = ProgressEvent(
        step="real_novelty_gate",
        label="Real Novelty Gate",
        status="failed",
        attempt=2,
        message="no_real_novelty",
    ).to_dict()

    line = format_progress_event(event)

    assert "[5/11]" in line
    assert "Real Novelty Gate" in line
    assert "失败" in line
    assert "attempt 2" in line
    assert "no_real_novelty" in line


def test_progress_reporter_prints_and_writes_status_files(tmp_path):
    stream = io.StringIO()
    status_path = tmp_path / "article_status.json"
    status_log_path = tmp_path / "article_status.jsonl"
    reporter = ProgressReporter(
        live=True,
        status_path=status_path,
        status_log_path=status_log_path,
        stream=stream,
    )

    reporter(
        ProgressEvent(
            step="researcher",
            label="Researcher",
            status="started",
            message="整理参考素材",
        )
    )
    reporter(
        ProgressEvent(
            step="researcher",
            label="Researcher",
            status="completed",
            message="3 materials",
        )
    )

    assert "Researcher" in stream.getvalue()
    payload = json.loads(status_path.read_text(encoding="utf-8"))
    assert payload["event_count"] == 2
    assert payload["current"]["status"] == "completed"
    log_lines = status_log_path.read_text(encoding="utf-8").splitlines()
    assert len(log_lines) == 2
    assert json.loads(log_lines[0])["status"] == "started"
