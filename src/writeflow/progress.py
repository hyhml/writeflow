"""Live progress events and status-file helpers for WriteFLow."""
from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, TextIO


PROGRESS_STEPS = [
    ("observation_interviewer", "Observation Interviewer"),
    ("local_voice_collector", "Local Voice Collector"),
    ("researcher", "Researcher"),
    ("thesis_architect", "Thesis Architect"),
    ("real_novelty_gate", "Real Novelty Gate"),
    ("writer_draft", "Writer Draft"),
    ("judge_precheck", "Depth Judge Precheck"),
    ("devil_advocate", "Devil Advocate"),
    ("writer_revision", "Writer Revision"),
    ("judge_final", "Depth Judge Final"),
    ("editor", "Editor"),
]


STEP_INDEX = {step: index + 1 for index, (step, _label) in enumerate(PROGRESS_STEPS)}
TOTAL_STEPS = len(PROGRESS_STEPS)


@dataclass
class ProgressEvent:
    """One live progress event emitted by the workflow."""

    step: str
    label: str
    status: str
    attempt: int = 1
    message: str = ""
    round_number: Optional[int] = None
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = (
                datetime.now(timezone.utc)
                .isoformat(timespec="seconds")
                .replace("+00:00", "Z")
            )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["round"] = data.pop("round_number")
        data["step_index"] = STEP_INDEX.get(self.step)
        data["total_steps"] = TOTAL_STEPS
        return data


class ProgressReporter:
    """Print live progress and persist latest/all events to JSON files."""

    def __init__(
        self,
        *,
        live: bool = False,
        status_path: Optional[Path | str] = None,
        status_log_path: Optional[Path | str] = None,
        stream: Optional[TextIO] = None,
    ):
        self.live = live
        self.status_path = Path(status_path) if status_path else None
        self.status_log_path = Path(status_log_path) if status_log_path else None
        self.stream = stream or sys.stdout
        self.events: list[dict[str, Any]] = []

    def __call__(self, event: ProgressEvent | dict[str, Any]) -> None:
        data = event.to_dict() if hasattr(event, "to_dict") else dict(event)
        self.events.append(data)

        if self.live:
            print(format_progress_event(data), file=self.stream, flush=True)

        if self.status_path:
            self.status_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "current": data,
                "events": self.events,
                "event_count": len(self.events),
                "updated_at": data.get("created_at", ""),
            }
            self.status_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        if self.status_log_path:
            self.status_log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.status_log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(data, ensure_ascii=False) + "\n")


def format_progress_event(event: dict[str, Any]) -> str:
    """Format one event as a compact terminal status line."""

    index = event.get("step_index") or "?"
    total = event.get("total_steps") or TOTAL_STEPS
    label = str(event.get("label", event.get("step", "")))
    status = str(event.get("status", ""))
    message = str(event.get("message", "") or "")
    attempt = int(event.get("attempt") or 1)
    round_number = event.get("round")
    suffix_parts = []
    if attempt > 1:
        suffix_parts.append(f"attempt {attempt}")
    if round_number is not None:
        suffix_parts.append(f"round {round_number}")
    suffix = f" ({', '.join(suffix_parts)})" if suffix_parts else ""
    icon = {
        "started": "⏳",
        "completed": "✅",
        "failed": "❌",
        "skipped": "⏭",
    }.get(status, "•")
    status_label = {
        "started": "正在运行",
        "completed": "完成",
        "failed": "失败",
        "skipped": "跳过",
    }.get(status, status)
    detail = f" - {message}" if message else ""
    return f"[{index}/{total}] {label:<26} {icon} {status_label}{suffix}{detail}"
