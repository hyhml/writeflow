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
    """Article and score output paths."""

    article: Optional[Path]
    scores: Optional[Path]


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


def build_output_paths(
    topic: str,
    output_arg: Optional[str],
    *,
    base_dir: Optional[Path | str] = None,
    now: Optional[datetime] = None,
) -> OutputPaths:
    """Resolve article and score paths from the CLI --output argument."""

    if output_arg is None:
        return OutputPaths(article=None, scores=None)

    if output_arg == AUTO_OUTPUT:
        timestamp = (now or datetime.now()).strftime("%Y%m%d_%H%M%S")
        output_dir = Path(base_dir) if base_dir is not None else project_root() / "outputs"
        article_path = output_dir / f"{slugify_topic(topic)}_{timestamp}.md"
    else:
        article_path = Path(output_arg)

    return OutputPaths(article=article_path, scores=score_path_for(article_path))


def save_article(path: Path | str, content: str) -> Path:
    """Write article content to disk and return the resolved Path object."""

    article_path = Path(path)
    article_path.parent.mkdir(parents=True, exist_ok=True)
    article_path.write_text(content, encoding="utf-8")
    return article_path


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
