"""Built-in web UI for running and observing WriteFLow tasks."""
from __future__ import annotations

import asyncio
import json
import threading
import traceback
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

from writeflow import __version__
from writeflow.config import get_settings, validate_runtime_settings
from writeflow.interview import (
    FIXED_INTERVIEW_QUESTIONS,
    build_human_observation,
    generate_followup_questions,
    has_interview_observation,
)
from writeflow.output import (
    AUTO_OUTPUT,
    build_output_paths,
    save_article,
    save_scores,
    save_trace,
)
from writeflow.progress import PROGRESS_STEPS, ProgressEvent
from writeflow.writeflow import TraceEvent, WriteFlow


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def json_safe(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        return json_safe(value.to_dict())
    if is_dataclass(value):
        return json_safe(asdict(value))
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value


@dataclass
class WebTask:
    task_id: str
    topic: str
    status: str = "queued"
    human_observation: str = ""
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    events: list[dict[str, Any]] = field(default_factory=list)
    trace_events: list[dict[str, Any]] = field(default_factory=list)
    result: Optional[dict[str, Any]] = None
    error: str = ""
    traceback: str = ""
    article_path: str = ""
    scores_path: str = ""
    trace_path: str = ""

    def add_event(self, event: ProgressEvent | dict[str, Any]) -> None:
        data = event.to_dict() if hasattr(event, "to_dict") else dict(event)
        self.events.append(json_safe(data))
        self.updated_at = utc_now()

    def add_trace_event(self, event: TraceEvent | dict[str, Any]) -> None:
        data = event.to_dict() if hasattr(event, "to_dict") else dict(event)
        self.trace_events.append(json_safe(data))
        self.updated_at = utc_now()

    def to_public_dict(self, *, include_observation: bool = False) -> dict[str, Any]:
        data = {
            "task_id": self.task_id,
            "topic": self.topic,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "events": self.events,
            "trace_events": self.trace_events,
            "current": self.events[-1] if self.events else None,
            "event_count": len(self.events),
            "result": self.result,
            "error": self.error,
            "article_path": self.article_path,
            "scores_path": self.scores_path,
            "trace_path": self.trace_path,
        }
        if include_observation:
            data["human_observation"] = self.human_observation
        return data


class WebTaskManager:
    """In-memory task store and background runner."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tasks: dict[str, WebTask] = {}

    def list_tasks(self) -> list[dict[str, Any]]:
        with self._lock:
            tasks = list(self._tasks.values())
        return [task.to_public_dict() for task in sorted(tasks, key=lambda item: item.created_at)]

    def get_task(self, task_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            task = self._tasks.get(task_id)
            return task.to_public_dict(include_observation=True) if task else None

    def start_task(self, payload: dict[str, Any]) -> dict[str, Any]:
        topic = str(payload.get("topic", "")).strip()
        if not topic:
            raise ValueError("topic is required")

        human_observation = build_observation_from_payload(payload)
        output_paths = build_output_paths(topic, AUTO_OUTPUT)
        task_id = f"web-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
        task = WebTask(
            task_id=task_id,
            topic=topic,
            human_observation=human_observation,
            article_path=str(output_paths.article or ""),
            scores_path=str(output_paths.scores or ""),
            trace_path=str(output_paths.trace or ""),
        )
        with self._lock:
            self._tasks[task_id] = task

        thread = threading.Thread(
            target=self._run_task_in_thread,
            args=(task_id, output_paths),
            daemon=True,
        )
        thread.start()
        return task.to_public_dict(include_observation=True)

    def _mutate_task(self, task_id: str, **changes: Any) -> Optional[WebTask]:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return None
            for key, value in changes.items():
                setattr(task, key, value)
            task.updated_at = utc_now()
            return task

    def _append_event(self, task_id: str, event: ProgressEvent | dict[str, Any]) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task:
                task.add_event(event)

    def _append_trace_event(self, task_id: str, event: TraceEvent | dict[str, Any]) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task:
                task.add_trace_event(event)

    def _run_task_in_thread(self, task_id: str, output_paths: Any) -> None:
        asyncio.run(self._run_task(task_id, output_paths))

    async def _run_task(self, task_id: str, output_paths: Any) -> None:
        task = self._mutate_task(task_id, status="running")
        if task is None:
            return

        try:
            settings = get_settings()
            issues = validate_runtime_settings(settings)
            if issues:
                raise ValueError("; ".join(issues))

            wf = WriteFlow()
            result = await wf.write(
                task.topic,
                context={"human_observation": task.human_observation},
                progress_callback=lambda event: self._append_event(task_id, event),
                trace_callback=lambda event: self._append_trace_event(task_id, event),
            )

            if output_paths.article and output_paths.scores and output_paths.trace:
                save_article(output_paths.article, result.content)
                save_scores(
                    output_paths.scores,
                    topic=task.topic,
                    result=result,
                    provider=settings.provider,
                    model=settings.model,
                )
                save_trace(
                    output_paths.trace,
                    topic=task.topic,
                    result=result,
                    provider=settings.provider,
                    model=settings.model,
                )

            result_payload = {
                "content": result.content,
                "scores": result.scores.to_dict(),
                "score_total": result.scores.total(),
                "passed": result.passed,
                "pass_reason": result.pass_reason,
                "rounds": result.rounds,
                "task_id": result.task_id,
                "trace_events": [json_safe(event) for event in result.trace_events],
            }
            self._mutate_task(task_id, status="completed", result=result_payload)
        except Exception as exc:  # pragma: no cover - keeps background task observable.
            self._mutate_task(
                task_id,
                status="failed",
                error=str(exc),
                traceback=traceback.format_exc(),
            )


def build_observation_from_payload(payload: dict[str, Any]) -> str:
    """Build one human_observation string from web form payload."""

    direct = str(payload.get("human_observation", "") or "").strip()
    if direct:
        return direct

    topic = str(payload.get("topic", "") or "").strip()
    preset = str(payload.get("preset_observation", "") or "").strip()
    fixed_answers = normalize_answers(payload.get("fixed_answers", []), kind="fixed")
    followup_answers = normalize_answers(payload.get("followup_answers", []), kind="followup")

    return build_human_observation(
        topic=topic,
        preset_observation=preset,
        fixed_answers=fixed_answers,
        followup_answers=followup_answers,
    )


def normalize_answers(value: Any, *, kind: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []

    normalized = []
    for index, item in enumerate(value, 1):
        if not isinstance(item, dict):
            continue
        question = str(item.get("question", "")).strip()
        answer = str(item.get("answer", "")).strip()
        if not question and not answer:
            continue
        normalized.append(
            {
                "kind": kind,
                "index": int(item.get("index") or index),
                "question": question,
                "answer": answer,
            }
        )
    return normalized


async def build_followups_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    topic = str(payload.get("topic", "") or "").strip()
    preset = str(payload.get("preset_observation", "") or "").strip()
    fixed_answers = normalize_answers(payload.get("fixed_answers", []), kind="fixed")
    if not has_interview_observation(
        preset_observation=preset,
        fixed_answers=fixed_answers,
        followup_answers=[],
    ):
        return {"questions": [], "human_observation": ""}

    observation = build_human_observation(
        topic=topic,
        preset_observation=preset,
        fixed_answers=fixed_answers,
        followup_answers=[],
    )
    questions = await generate_followup_questions(topic, observation)
    return {"questions": questions, "human_observation": observation}


class WriteFlowWebHandler(BaseHTTPRequestHandler):
    server_version = "WriteFlowWeb/0.1"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        if path == "/":
            self._send_html(INDEX_HTML)
            return
        if path == "/api/config":
            self._send_json(get_config_payload())
            return
        if path == "/api/steps":
            self._send_json({"steps": step_payload()})
            return
        if path == "/api/tasks":
            self._send_json({"tasks": self.server.manager.list_tasks()})
            return
        if path.startswith("/api/tasks/"):
            task_id = path.rsplit("/", 1)[-1]
            task = self.server.manager.get_task(task_id)
            if not task:
                self._send_json({"error": "task not found"}, status=HTTPStatus.NOT_FOUND)
                return
            self._send_json(task)
            return
        self._send_json({"error": "not found"}, status=HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        try:
            payload = self._read_json()
            if path == "/api/tasks":
                self._send_json(self.server.manager.start_task(payload), status=HTTPStatus.CREATED)
                return
            if path == "/api/interview/followups":
                self._send_json(asyncio.run(build_followups_from_payload(payload)))
                return
            self._send_json({"error": "not found"}, status=HTTPStatus.NOT_FOUND)
        except ValueError as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
        except Exception as exc:  # pragma: no cover - keeps API failures visible.
            self._send_json(
                {"error": str(exc), "traceback": traceback.format_exc()},
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("JSON body must be an object")
        return data

    def _send_html(self, html: str, *, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, data: Any, *, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(json_safe(data), ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def get_config_payload() -> dict[str, Any]:
    try:
        settings = get_settings()
        issues = validate_runtime_settings(settings)
        return {
            "ok": not issues,
            "issues": issues,
            "provider": settings.provider,
            "model": settings.model,
            "base_url": settings.base_url,
            "version": __version__,
        }
    except Exception as exc:
        return {"ok": False, "issues": [str(exc)], "version": __version__}


def step_payload() -> list[dict[str, Any]]:
    return [
        {"step": step, "label": label, "index": index}
        for index, (step, label) in enumerate(PROGRESS_STEPS, 1)
    ]


class WriteFlowWebServer(ThreadingHTTPServer):
    manager: WebTaskManager


def create_server(host: str = "127.0.0.1", port: int = 8765) -> WriteFlowWebServer:
    server = WriteFlowWebServer((host, port), WriteFlowWebHandler)
    server.manager = WebTaskManager()
    return server


def serve(host: str = "127.0.0.1", port: int = 8765) -> None:
    server = create_server(host, port)
    print(f"WriteFLow Web UI: http://{host}:{server.server_port}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    finally:
        server.server_close()


INDEX_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>WriteFLow Web</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f5f6f8;
      --panel: #ffffff;
      --line: #d8dde6;
      --text: #17202a;
      --muted: #637083;
      --accent: #176b87;
      --accent-2: #8b5e34;
      --danger: #b42318;
      --ok: #146c43;
      --warn: #9a6700;
      --shadow: 0 1px 2px rgba(16, 24, 40, .08);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font: 14px/1.5 ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--text);
      background: var(--bg);
      letter-spacing: 0;
    }
    button, input, textarea { font: inherit; }
    button {
      border: 1px solid var(--line);
      background: var(--panel);
      color: var(--text);
      min-height: 36px;
      border-radius: 6px;
      padding: 7px 12px;
      cursor: pointer;
    }
    button.primary {
      border-color: var(--accent);
      background: var(--accent);
      color: white;
    }
    button:disabled { opacity: .55; cursor: not-allowed; }
    .app {
      min-height: 100vh;
      display: grid;
      grid-template-columns: minmax(320px, 390px) 1fr;
    }
    aside {
      background: var(--panel);
      border-right: 1px solid var(--line);
      padding: 18px;
      overflow: auto;
      max-height: 100vh;
    }
    main {
      min-width: 0;
      padding: 18px;
      overflow: auto;
      max-height: 100vh;
    }
    h1 { font-size: 22px; margin: 0 0 4px; }
    h2 { font-size: 15px; margin: 0 0 10px; }
    label { display: block; font-weight: 600; margin: 14px 0 6px; }
    input, textarea {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 9px 10px;
      background: white;
      color: var(--text);
    }
    textarea { min-height: 88px; resize: vertical; }
    .topbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 14px;
    }
    .statusline { color: var(--muted); font-size: 13px; }
    .config {
      border: 1px solid var(--line);
      background: #fbfcfe;
      padding: 10px;
      border-radius: 6px;
      margin: 14px 0;
      color: var(--muted);
    }
    .config.bad { color: var(--danger); border-color: #f2b8b5; background: #fff7f6; }
    .section {
      border-top: 1px solid var(--line);
      padding-top: 14px;
      margin-top: 16px;
    }
    .question {
      border: 1px solid var(--line);
      background: #fbfcfe;
      border-radius: 6px;
      padding: 10px;
      margin-bottom: 8px;
    }
    .question label { margin-top: 0; font-weight: 600; }
    .toolbar {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
      margin-top: 12px;
    }
    .layout {
      display: grid;
      grid-template-columns: minmax(320px, .85fr) minmax(360px, 1.15fr);
      gap: 16px;
      align-items: start;
    }
    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
      padding: 14px;
      min-width: 0;
    }
    .steps {
      display: grid;
      gap: 7px;
    }
    .step {
      display: grid;
      grid-template-columns: 26px 1fr auto;
      align-items: center;
      gap: 8px;
      min-height: 34px;
      padding: 6px 8px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fbfcfe;
    }
    .step .num {
      width: 24px;
      height: 24px;
      display: grid;
      place-items: center;
      border-radius: 50%;
      background: #e9eef4;
      color: var(--muted);
      font-size: 12px;
      font-variant-numeric: tabular-nums;
    }
    .step.running { border-color: var(--accent); }
    .step.completed .num { background: #dcefe6; color: var(--ok); }
    .step.failed .num { background: #fde2df; color: var(--danger); }
    .step.skipped .num { background: #fff1cd; color: var(--warn); }
    .pill {
      border-radius: 999px;
      padding: 2px 8px;
      background: #eef2f7;
      color: var(--muted);
      font-size: 12px;
      white-space: nowrap;
    }
    .event-list {
      display: grid;
      gap: 8px;
      max-height: 360px;
      overflow: auto;
    }
    .event {
      border-left: 3px solid var(--line);
      padding: 6px 8px;
      background: #fbfcfe;
    }
    .event.started { border-left-color: var(--accent); }
    .event.completed { border-left-color: var(--ok); }
    .event.failed { border-left-color: var(--danger); }
    .event.skipped { border-left-color: var(--warn); }
    .event strong { display: block; }
    .event small { color: var(--muted); }
    .tabs {
      display: flex;
      gap: 6px;
      border-bottom: 1px solid var(--line);
      margin: -2px -2px 12px;
      padding: 0 2px;
    }
    .tab {
      border: 0;
      border-bottom: 2px solid transparent;
      border-radius: 0;
      min-height: 34px;
      background: transparent;
      padding: 7px 9px;
      color: var(--muted);
    }
    .tab.active { color: var(--accent); border-bottom-color: var(--accent); }
    pre {
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      margin: 0;
      background: #fbfcfe;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 12px;
      max-height: 62vh;
      overflow: auto;
    }
    .score-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px;
      margin-bottom: 12px;
    }
    .score {
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 8px;
      background: #fbfcfe;
    }
    .score b { display: block; font-size: 18px; }
    .muted { color: var(--muted); }
    .error { color: var(--danger); }
    @media (max-width: 920px) {
      .app { grid-template-columns: 1fr; }
      aside { max-height: none; border-right: 0; border-bottom: 1px solid var(--line); }
      main { max-height: none; }
      .layout { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class="app">
    <aside>
      <h1>WriteFLow</h1>
      <div class="statusline">多 Agent 深度稿件工作台</div>
      <div id="config" class="config">正在读取配置...</div>

      <label for="topic">主题</label>
      <input id="topic" placeholder="例如：深圳电动车治理">

      <label for="preset">已有观察或写作要求</label>
      <textarea id="preset" placeholder="可以写你已有的本地观察、核心直觉、想避免的空话。"></textarea>

      <div class="section">
        <h2>Observation Interview</h2>
        <div id="fixedQuestions"></div>
        <div class="toolbar">
          <button id="followupBtn" type="button">生成追问</button>
          <button id="clearBtn" type="button">清空</button>
        </div>
        <div id="followupBox"></div>
      </div>

      <div class="section">
        <div class="toolbar">
          <button id="startBtn" class="primary" type="button">开始写作</button>
        </div>
        <p class="muted">任务会保存到仓库的 outputs/ 目录；页面会轮询显示进度、trace 和最终稿。</p>
      </div>
    </aside>

    <main>
      <div class="topbar">
        <div>
          <h2 id="taskTitle">尚未开始任务</h2>
          <div id="taskMeta" class="statusline">填写主题和观察材料后开始。</div>
        </div>
        <button id="refreshBtn" type="button">刷新</button>
      </div>

      <div class="layout">
        <section class="panel">
          <h2>工作规划</h2>
          <div id="steps" class="steps"></div>
        </section>

        <section class="panel">
          <div class="tabs">
            <button class="tab active" data-tab="events" type="button">进度</button>
            <button class="tab" data-tab="trace" type="button">中间输出</button>
            <button class="tab" data-tab="result" type="button">最终稿</button>
          </div>
          <div id="tab-events">
            <div id="events" class="event-list"></div>
          </div>
          <div id="tab-trace" hidden>
            <pre id="trace">暂无中间输出。</pre>
          </div>
          <div id="tab-result" hidden>
            <div id="scores"></div>
            <pre id="result">暂无最终稿。</pre>
          </div>
        </section>
      </div>
    </main>
  </div>

  <script>
    const fixedQuestions = __FIXED_QUESTIONS__;
    const state = { steps: [], taskId: "", task: null, timer: null };

    const $ = (id) => document.getElementById(id);

    function answerItems(container) {
      return [...container.querySelectorAll("[data-question]")].map((node, index) => ({
        kind: node.dataset.kind,
        index: index + 1,
        question: node.dataset.question,
        answer: node.querySelector("textarea").value.trim()
      }));
    }

    function renderQuestions(target, questions, kind) {
      target.innerHTML = questions.map((question, index) => `
        <div class="question" data-kind="${kind}" data-question="${escapeAttr(question)}">
          <label>${index + 1}. ${escapeHtml(question)}</label>
          <textarea rows="3"></textarea>
        </div>
      `).join("");
    }

    function escapeHtml(value) {
      return String(value).replace(/[&<>"']/g, (ch) => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
      }[ch]));
    }

    function escapeAttr(value) {
      return escapeHtml(value).replace(/`/g, "&#96;");
    }

    async function api(path, options = {}) {
      const res = await fetch(path, {
        ...options,
        headers: {"Content-Type": "application/json", ...(options.headers || {})}
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
      return data;
    }

    async function loadConfig() {
      const config = await api("/api/config");
      const box = $("config");
      box.classList.toggle("bad", !config.ok);
      box.innerHTML = config.ok
        ? `配置可用：${escapeHtml(config.provider)} / ${escapeHtml(config.model)}`
        : `配置未完成：${escapeHtml((config.issues || []).join("；"))}`;
    }

    async function loadSteps() {
      const data = await api("/api/steps");
      state.steps = data.steps;
      renderSteps();
    }

    function renderSteps() {
      const currentByStep = {};
      if (state.task) {
        for (const event of state.task.events || []) currentByStep[event.step] = event;
      }
      $("steps").innerHTML = state.steps.map((step) => {
        const event = currentByStep[step.step] || {};
        const status = event.status || "waiting";
        const label = event.message ? `${event.status}: ${event.message}` : status;
        return `
          <div class="step ${escapeAttr(status)}">
            <span class="num">${step.index}</span>
            <span>${escapeHtml(step.label)}</span>
            <span class="pill">${escapeHtml(label)}</span>
          </div>
        `;
      }).join("");
    }

    function renderTask(task) {
      state.task = task;
      $("taskTitle").textContent = task.topic || "尚未开始任务";
      $("taskMeta").textContent = task.task_id
        ? `${task.status} · ${task.event_count || 0} events · ${task.article_path || ""}`
        : "填写主题和观察材料后开始。";
      renderSteps();
      renderEvents(task.events || []);
      renderTrace(task.trace_events || (task.result && task.result.trace_events) || []);
      renderResult(task);
      if (task.status === "completed" || task.status === "failed") stopPolling();
    }

    function renderEvents(events) {
      $("events").innerHTML = events.length ? events.slice().reverse().map((event) => `
        <div class="event ${escapeAttr(event.status)}">
          <strong>${escapeHtml(event.label || event.step)} <span class="muted">${escapeHtml(event.status)}</span></strong>
          <div>${escapeHtml(event.message || "")}</div>
          <small>${escapeHtml(event.created_at || "")}${event.round ? ` · round ${event.round}` : ""}</small>
        </div>
      `).join("") : `<p class="muted">暂无进度事件。</p>`;
    }

    function renderTrace(trace) {
      if (!trace.length) {
        $("trace").textContent = "暂无中间输出。";
        return;
      }
      $("trace").textContent = trace.map((event, index) =>
        `${index + 1}. ${event.stage} / ${event.agent}${event.round ? " / round " + event.round : ""}\n` +
        JSON.stringify(event.output, null, 2)
      ).join("\n\n");
    }

    function renderResult(task) {
      if (task.status === "failed") {
        $("scores").innerHTML = `<p class="error">${escapeHtml(task.error || "任务失败")}</p>`;
        $("result").textContent = task.traceback || "";
        return;
      }
      const result = task.result;
      if (!result) {
        $("scores").innerHTML = "";
        $("result").textContent = "暂无最终稿。";
        return;
      }
      const scores = result.scores || {};
      $("scores").innerHTML = `
        <div class="score-grid">
          ${Object.entries(scores).map(([name, value]) => `
            <div class="score"><span>${escapeHtml(name)}</span><b>${escapeHtml(value)}</b></div>
          `).join("")}
        </div>
        <p class="muted">Gate：${result.passed ? "通过" : "未通过"} · ${escapeHtml(result.pass_reason || "")} · 轮次 ${result.rounds}</p>
      `;
      $("result").textContent = result.content || "";
    }

    async function generateFollowups() {
      $("followupBtn").disabled = true;
      try {
        const data = await api("/api/interview/followups", {
          method: "POST",
          body: JSON.stringify({
            topic: $("topic").value,
            preset_observation: $("preset").value,
            fixed_answers: answerItems($("fixedQuestions"))
          })
        });
        renderQuestions($("followupBox"), data.questions || [], "followup");
      } catch (err) {
        $("followupBox").innerHTML = `<p class="error">${escapeHtml(err.message)}</p>`;
      } finally {
        $("followupBtn").disabled = false;
      }
    }

    async function startTask() {
      $("startBtn").disabled = true;
      try {
        const task = await api("/api/tasks", {
          method: "POST",
          body: JSON.stringify({
            topic: $("topic").value,
            preset_observation: $("preset").value,
            fixed_answers: answerItems($("fixedQuestions")),
            followup_answers: answerItems($("followupBox"))
          })
        });
        state.taskId = task.task_id;
        renderTask(task);
        startPolling();
      } catch (err) {
        $("taskMeta").textContent = err.message;
      } finally {
        $("startBtn").disabled = false;
      }
    }

    async function refreshTask() {
      if (!state.taskId) return;
      const task = await api(`/api/tasks/${state.taskId}`);
      renderTask(task);
    }

    function startPolling() {
      stopPolling();
      state.timer = setInterval(() => refreshTask().catch(console.error), 1200);
    }

    function stopPolling() {
      if (state.timer) clearInterval(state.timer);
      state.timer = null;
    }

    document.querySelectorAll(".tab").forEach((tab) => {
      tab.addEventListener("click", () => {
        document.querySelectorAll(".tab").forEach((item) => item.classList.remove("active"));
        tab.classList.add("active");
        for (const name of ["events", "trace", "result"]) {
          $(`tab-${name}`).hidden = tab.dataset.tab !== name;
        }
      });
    });
    $("followupBtn").addEventListener("click", generateFollowups);
    $("startBtn").addEventListener("click", startTask);
    $("refreshBtn").addEventListener("click", () => refreshTask().catch(console.error));
    $("clearBtn").addEventListener("click", () => {
      $("preset").value = "";
      renderQuestions($("fixedQuestions"), fixedQuestions, "fixed");
      $("followupBox").innerHTML = "";
    });

    renderQuestions($("fixedQuestions"), fixedQuestions, "fixed");
    loadConfig().catch((err) => $("config").textContent = err.message);
    loadSteps().catch(console.error);
  </script>
</body>
</html>""".replace("__FIXED_QUESTIONS__", json.dumps(FIXED_INTERVIEW_QUESTIONS, ensure_ascii=False))
