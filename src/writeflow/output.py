"""Output path and serialization helpers for WriteFLow."""
from __future__ import annotations

import json
import re
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, NamedTuple, Optional


AUTO_OUTPUT = "__auto__"


class OutputPaths(NamedTuple):
    """Article, score, trace, and live status output paths."""

    article: Optional[Path]
    scores: Optional[Path]
    trace: Optional[Path]
    status: Optional[Path]
    status_log: Optional[Path]


def project_root() -> Path:
    """Return the repository root when running from an installed package."""

    return Path(__file__).resolve().parents[2]


def slugify_topic(text: str, max_len: int = 40) -> str:
    """Convert a writing topic into a filesystem-safe filename stem."""

    normalized = re.sub(r"\s+", "_", text.strip())
    slug = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", normalized, flags=re.UNICODE)
    slug = re.sub(r"_+", "_", slug).strip("._ ")
    if len(slug) > max_len:
        slug = slug[:max_len].strip("._ ")
    return slug or "article"


def score_path_for(article_path: Path) -> Path:
    """Return the sidecar JSON path for an article file."""

    return article_path.with_name(f"{article_path.stem}_scores.json")


def trace_dir_for(article_path: Path) -> Path:
    """Return the trace output directory for an article file."""

    return article_path.with_name(f"{article_path.stem}_trace")


def status_path_for(article_path: Path) -> Path:
    """Return the latest live-status JSON path for an article file."""

    return article_path.with_name(f"{article_path.stem}_status.json")


def status_log_path_for(article_path: Path) -> Path:
    """Return the live-status JSONL path for an article file."""

    return article_path.with_name(f"{article_path.stem}_status.jsonl")


def build_output_paths(
    topic: str,
    output_arg: Optional[str],
    *,
    base_dir: Optional[Path | str] = None,
    now: Optional[datetime] = None,
) -> OutputPaths:
    """Resolve article and score paths from the CLI --output argument."""

    if output_arg is None:
        return OutputPaths(
            article=None,
            scores=None,
            trace=None,
            status=None,
            status_log=None,
        )

    if output_arg == AUTO_OUTPUT:
        timestamp = (now or datetime.now()).strftime("%Y%m%d_%H%M%S")
        output_dir = Path(base_dir) if base_dir is not None else project_root() / "outputs"
        article_path = output_dir / f"{slugify_topic(topic)}_{timestamp}.md"
    else:
        article_path = Path(output_arg)

    return OutputPaths(
        article=article_path,
        scores=score_path_for(article_path),
        trace=trace_dir_for(article_path),
        status=status_path_for(article_path),
        status_log=status_log_path_for(article_path),
    )


def clean_final_article(content: str) -> str:
    """Remove model process text and keep only the publishable article body."""

    cleaned = re.sub(r"<think>.*?</think>", "", content, flags=re.IGNORECASE | re.DOTALL)
    cleaned = re.sub(
        r"<thinking>.*?</thinking>",
        "",
        cleaned,
        flags=re.IGNORECASE | re.DOTALL,
    )

    first_heading = re.search(r"(?m)^#\s+", cleaned)
    if first_heading:
        cleaned = cleaned[first_heading.start():]

    cutoff_markers = [
        "\u3010\u950b\u5229\u5ea6\u68c0\u6d4b\u7ed3\u679c\u3011",
        "\u3010\u9510\u5229\u5ea6\u68c0\u6d4b\u7ed3\u679c\u3011",
        "\u3010\u950b\u5229\u5ea6\u68c0\u6d4b\u3011",
        "\u3010\u7f16\u8f91\u8bf4\u660e\u3011",
        "\u3010\u4fee\u6539\u8bf4\u660e\u3011",
        "\u3010\u81ea\u68c0\u7ed3\u679c\u3011",
    ]
    cut_positions = [cleaned.find(marker) for marker in cutoff_markers]
    cut_positions = [position for position in cut_positions if position >= 0]
    if cut_positions:
        cleaned = cleaned[:min(cut_positions)]

    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip() + ("\n" if cleaned.strip() else "")


def save_article(path: Path | str, content: str) -> Path:
    """Write article content to disk and return the resolved Path object."""

    article_path = Path(path)
    article_path.parent.mkdir(parents=True, exist_ok=True)
    article_path.write_text(content, encoding="utf-8")
    return article_path


def _json_safe(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        return _json_safe(value.to_dict())
    if is_dataclass(value):
        return _json_safe(asdict(value))
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value


def serialize_scores(scores: Any) -> dict[str, Any]:
    """Convert supported score containers into a JSON-serializable dict."""

    if hasattr(scores, "to_dict"):
        data = dict(scores.to_dict())
    elif is_dataclass(scores):
        data = asdict(scores)
    elif isinstance(scores, dict):
        data = dict(scores)
    elif hasattr(scores, "scores") and isinstance(scores.scores, dict):
        data = dict(scores.scores)
    else:
        data = {}

    total = getattr(scores, "total", None)
    if callable(total):
        data["total"] = total()
    elif isinstance(total, (int, float)):
        data["total"] = total
    elif data and "total" not in data:
        numeric_values = [value for value in data.values() if isinstance(value, (int, float))]
        data["total"] = sum(numeric_values)

    return data


def build_score_record(
    *,
    topic: str,
    result: Any,
    provider: Optional[str] = None,
    model: Optional[str] = None,
) -> dict[str, Any]:
    """Build the sidecar score JSON payload for a WriteResult-like object."""

    record = {
        "topic": topic,
        "pass": bool(getattr(result, "passed", False)),
        "pass_reason": getattr(result, "pass_reason", ""),
        "rounds": getattr(result, "rounds", 0),
        "task_id": getattr(result, "task_id", ""),
        "scores": serialize_scores(getattr(result, "scores", {})),
    }
    if provider:
        record["provider"] = provider
    if model:
        record["model"] = model
    return record


def save_scores(
    path: Path | str,
    *,
    topic: str,
    result: Any,
    provider: Optional[str] = None,
    model: Optional[str] = None,
) -> Path:
    """Write the sidecar score JSON file."""

    score_path = Path(path)
    score_path.parent.mkdir(parents=True, exist_ok=True)
    payload = build_score_record(topic=topic, result=result, provider=provider, model=model)
    score_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return score_path


def save_trace(
    path: Path | str,
    *,
    topic: str,
    result: Any,
    provider: Optional[str] = None,
    model: Optional[str] = None,
) -> Path:
    """Write trace files for a WriteResult-like object."""

    trace_path = Path(path)
    trace_path.mkdir(parents=True, exist_ok=True)

    trace_events = [
        _json_safe(event)
        for event in getattr(result, "trace_events", [])
    ]
    manifest = {
        "topic": topic,
        "task_id": getattr(result, "task_id", ""),
        "provider": provider,
        "model": model,
        "passed": bool(getattr(result, "passed", False)),
        "pass_reason": getattr(result, "pass_reason", ""),
        "rounds": getattr(result, "rounds", 0),
        "trace_event_count": len(trace_events),
    }
    (trace_path / "00_manifest.json").write_text(
        json.dumps(_json_safe(manifest), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    timeline_lines = [f"# Trace timeline: {topic}", ""]
    for index, event in enumerate(trace_events, 1):
        stage = event.get("stage", "unknown")
        agent = event.get("agent", "unknown")
        round_number = event.get("round")
        timestamp = event.get("created_at", "")
        suffix = f" round {round_number}" if round_number is not None else ""
        decision = ""
        output = event.get("output") or {}
        if isinstance(output, dict) and output.get("decision"):
            decision = f" - {output['decision']}"
        attempt = event.get("attempt")
        if attempt:
            decision += f" (attempt {attempt})"
        timeline_lines.append(
            f"{index}. `{stage}` by `{agent}`{suffix} - {timestamp}{decision}"
        )
    (trace_path / "00_timeline.md").write_text(
        "\n".join(timeline_lines).rstrip() + "\n",
        encoding="utf-8",
    )

    stage_counts: dict[str, int] = {}
    for event in trace_events:
        _write_trace_event(trace_path, event, stage_counts)

    final_content = getattr(result, "content", "")
    if final_content:
        (trace_path / "final_article.md").write_text(final_content, encoding="utf-8")

    return trace_path


def _write_trace_event(
    trace_path: Path,
    event: dict[str, Any],
    stage_counts: Optional[dict[str, int]] = None,
) -> None:
    stage = event.get("stage", "")
    output = event.get("output") or {}
    round_number = int(event.get("round") or 0)
    counts = stage_counts if stage_counts is not None else {}
    counts[stage] = counts.get(stage, 0) + 1
    stage_count = counts[stage]

    if stage == "observation_interviewer":
        _write_json(trace_path / "01_observation_interviewer.json", output)
    elif stage == "local_voice_collector":
        _write_json(trace_path / "02_local_voice_collector.json", output)
    elif stage == "researcher_materials":
        _write_json(trace_path / "03_researcher_materials.json", output)
    elif stage == "thesis_architect_brief":
        filename = (
            "04_thesis_architect_brief.json"
            if stage_count == 1
            else f"04_thesis_architect_brief_retry_{stage_count - 1:02d}.json"
        )
        _write_json(trace_path / filename, output)
    elif stage == "real_novelty_gate":
        filename = (
            "05_real_novelty_gate.json"
            if stage_count == 1
            else f"05_real_novelty_gate_retry_{stage_count - 1:02d}.json"
        )
        _write_json(trace_path / filename, output)
    elif stage == "writer_draft":
        _write_markdown(
            trace_path / f"round_{round_number:02d}_writer_draft.md",
            output.get("content", ""),
        )
    elif stage == "devil_advocate_criticisms":
        _write_json(
            trace_path / f"round_{round_number:02d}_devil_advocate_criticisms.json",
            output,
        )
    elif stage == "writer_revision":
        _write_markdown(
            trace_path / f"round_{round_number:02d}_writer_revision.md",
            output.get("content", ""),
        )
    elif stage == "judge_precheck":
        _write_json(trace_path / f"round_{round_number:02d}_judge_precheck.json", output)
    elif stage == "judge_final":
        _write_json(trace_path / f"round_{round_number:02d}_judge_final.json", output)
    elif stage == "writer_defense":
        _write_markdown(
            trace_path / f"round_{round_number:02d}_writer_defense.md",
            output.get("content", ""),
        )
    elif stage == "judge_result":
        _write_json(trace_path / f"round_{round_number:02d}_judge_result.json", output)
    elif stage == "editor_raw":
        _write_markdown(trace_path / "final_editor_raw.md", output.get("raw_content", ""))


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(_json_safe(payload), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _write_markdown(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
