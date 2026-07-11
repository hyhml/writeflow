"""Interactive human-observation interview helpers."""
from __future__ import annotations

import inspect
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

from writeflow.agents.claude_client import get_claude_client


FIXED_INTERVIEW_QUESTIONS = [
    "我在本地看到的反常现象是什么？",
    "这个地方/案例和常见讨论有什么不一样？",
    "我直觉上觉得真正的问题根源是什么？",
    "我想到的具体解决方案是什么？",
    "哪些细节一旦丢掉，文章就会变成陈词滥调？",
]


FOLLOWUP_SYSTEM_PROMPT = """你是 WriteFLow 的 Observation Interviewer。
你的任务不是替用户编造本地经验，而是根据用户已经回答的观察材料，提出 2-3 个能够让文章更具体、更不陈词滥调的追问。

追问必须优先补足：
1. 更具体的地点、群体、场景或冲突
2. 常见解释为什么不够
3. 谁获益、谁承担代价
4. 方案的执行阻力、代价或利益冲突

只输出 JSON，不要输出 Markdown。格式：
{"questions": ["追问1", "追问2", "追问3"]}"""


InputFunc = Callable[[str], str]
OutputFunc = Callable[[str], None]
FollowupProvider = Callable[[str, str], Any]


def interview_json_path_for(article_path: Path | str) -> Path:
    """Return the interview JSON sidecar path for an article path."""

    path = Path(article_path)
    return path.with_name(f"{path.stem}_interview.json")


def interview_markdown_path_for(article_path: Path | str) -> Path:
    """Return the interview Markdown sidecar path for an article path."""

    path = Path(article_path)
    return path.with_name(f"{path.stem}_interview.md")


async def run_interactive_interview(
    topic: str,
    *,
    preset_observation: str = "",
    input_func: InputFunc = input,
    output_func: OutputFunc = print,
    followup_provider: Optional[FollowupProvider] = None,
) -> dict[str, Any]:
    """Ask fixed questions, generate follow-ups, and return an interview record."""

    output_func("\n=== Observation Interview ===")
    output_func("先回答几个关于本地观察的问题。可以留空，但全部留空会停止生成。")
    if preset_observation.strip():
        output_func("\n已读取到预填观察材料，下面的回答会和它合并。")

    fixed_answers = _ask_questions(
        FIXED_INTERVIEW_QUESTIONS,
        input_func=input_func,
        output_func=output_func,
        kind="fixed",
    )
    initial_observation = build_human_observation(
        topic=topic,
        preset_observation=preset_observation,
        fixed_answers=fixed_answers,
        followup_answers=[],
    )

    followup_questions: list[str] = []
    if initial_observation.strip():
        if followup_provider is None:
            followup_questions = await generate_followup_questions(topic, initial_observation)
        else:
            provided = followup_provider(topic, initial_observation)
            if inspect.isawaitable(provided):
                provided = await provided
            followup_questions = _normalize_question_list(provided)

    followup_answers: list[dict[str, Any]] = []
    if followup_questions:
        output_func("\n=== 补充追问 ===")
        followup_answers = _ask_questions(
            followup_questions,
            input_func=input_func,
            output_func=output_func,
            kind="followup",
        )

    human_observation = build_human_observation(
        topic=topic,
        preset_observation=preset_observation,
        fixed_answers=fixed_answers,
        followup_answers=followup_answers,
    )
    record = {
        "topic": topic,
        "created_at": datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "preset_observation": preset_observation.strip(),
        "fixed_answers": fixed_answers,
        "followup_questions": followup_questions,
        "followup_answers": followup_answers,
        "human_observation": human_observation,
        "has_observation": has_interview_observation(
            preset_observation=preset_observation,
            fixed_answers=fixed_answers,
            followup_answers=followup_answers,
        ),
    }
    return record


async def generate_followup_questions(topic: str, initial_observation: str) -> list[str]:
    """Generate two or three follow-up questions from the configured model."""

    if not initial_observation.strip():
        return []

    client = get_claude_client()
    response = await client.generate(
        messages=[
            {
                "role": "user",
                "content": (
                    "请根据下面的主题和用户观察，提出 2-3 个继续追问用户的问题。\n\n"
                    f"主题：{topic}\n\n"
                    f"用户观察：\n{initial_observation}"
                ),
            }
        ],
        system_prompt=FOLLOWUP_SYSTEM_PROMPT,
        max_tokens=1024,
        temperature=0.2,
    )
    return parse_followup_questions(response.get("content", ""))


def parse_followup_questions(content: str, *, limit: int = 3) -> list[str]:
    """Parse follow-up questions from JSON or a simple line list."""

    json_match = re.search(r"\{.*\}|\[.*\]", content, re.DOTALL)
    if json_match:
        try:
            parsed = json.loads(json_match.group())
            if isinstance(parsed, dict):
                return _normalize_question_list(parsed.get("questions", []), limit=limit)
            return _normalize_question_list(parsed, limit=limit)
        except json.JSONDecodeError:
            pass

    lines = []
    for line in content.splitlines():
        cleaned = re.sub(r"^\s*(?:[-*]|\d+[.)、])\s*", "", line).strip()
        if cleaned:
            lines.append(cleaned)
    return _normalize_question_list(lines, limit=limit)


def build_human_observation(
    *,
    topic: str,
    preset_observation: str,
    fixed_answers: list[dict[str, Any]],
    followup_answers: list[dict[str, Any]],
) -> str:
    """Render answered interview material into one observation string."""

    sections = [f"主题：{topic}"]
    if preset_observation.strip():
        sections.append(f"【已有观察材料】\n{preset_observation.strip()}")

    fixed_lines = _render_answer_lines(fixed_answers)
    if fixed_lines:
        sections.append("【固定观察问题】\n" + fixed_lines)

    followup_lines = _render_answer_lines(followup_answers)
    if followup_lines:
        sections.append("【补充追问】\n" + followup_lines)

    if len(sections) == 1:
        return ""
    return "\n\n".join(sections).strip()


def has_interview_observation(
    *,
    preset_observation: str,
    fixed_answers: Iterable[dict[str, Any]],
    followup_answers: Iterable[dict[str, Any]],
) -> bool:
    """Return True when the interview captured any meaningful user material."""

    if preset_observation.strip():
        return True
    for item in [*fixed_answers, *followup_answers]:
        if str(item.get("answer", "")).strip():
            return True
    return False


def save_interview_record(
    record: dict[str, Any],
    json_path: Path | str,
    markdown_path: Path | str,
) -> tuple[Path, Path]:
    """Save structured and human-readable interview records."""

    json_file = Path(json_path)
    md_file = Path(markdown_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    md_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(
        json.dumps(record, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    md_file.write_text(render_interview_markdown(record), encoding="utf-8")
    return json_file, md_file


def render_interview_markdown(record: dict[str, Any]) -> str:
    """Render an interview record as Markdown."""

    lines = [
        f"# Observation Interview: {record.get('topic', '')}",
        "",
        f"- created_at: {record.get('created_at', '')}",
        f"- has_observation: {record.get('has_observation', False)}",
        "",
    ]
    preset = str(record.get("preset_observation", "")).strip()
    if preset:
        lines.extend(["## 已有观察材料", "", preset, ""])

    lines.extend(["## 固定观察问题", ""])
    for answer in record.get("fixed_answers", []):
        lines.extend(_render_markdown_answer(answer))

    followups = record.get("followup_answers", [])
    if followups:
        lines.extend(["## 补充追问", ""])
        for answer in followups:
            lines.extend(_render_markdown_answer(answer))

    observation = str(record.get("human_observation", "")).strip()
    if observation:
        lines.extend(["## 合并后的 human_observation", "", observation, ""])

    return "\n".join(lines).rstrip() + "\n"


def _ask_questions(
    questions: list[str],
    *,
    input_func: InputFunc,
    output_func: OutputFunc,
    kind: str,
) -> list[dict[str, Any]]:
    answers = []
    for index, question in enumerate(questions, 1):
        output_func(f"\n[{index}/{len(questions)}] {question}")
        answer = input_func("> ").strip()
        answers.append(
            {
                "kind": kind,
                "index": index,
                "question": question,
                "answer": answer,
            }
        )
    return answers


def _render_answer_lines(answers: list[dict[str, Any]]) -> str:
    lines = []
    for item in answers:
        answer = str(item.get("answer", "")).strip()
        if not answer:
            continue
        lines.append(f"- {item.get('question', '')}\n  {answer}")
    return "\n".join(lines)


def _render_markdown_answer(answer: dict[str, Any]) -> list[str]:
    response = str(answer.get("answer", "")).strip() or "（未回答）"
    return [f"### {answer.get('question', '')}", "", response, ""]


def _normalize_question_list(value: Any, *, limit: int = 3) -> list[str]:
    if isinstance(value, str):
        candidates = [value]
    elif isinstance(value, Iterable):
        candidates = [str(item).strip() for item in value]
    else:
        candidates = []

    questions = []
    seen = set()
    for item in candidates:
        question = item.strip()
        if not question or question in seen:
            continue
        seen.add(question)
        questions.append(question)
        if len(questions) >= limit:
            break
    return questions
