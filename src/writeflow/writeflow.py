"""
WriteFlow - 批判性写作工作流
"""
from __future__ import annotations

import uuid
import logging
import inspect
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Callable

from writeflow.agents.observation_interviewer import ObservationInterviewerAgent
from writeflow.agents.local_voice_collector import LocalVoiceCollectorAgent
from writeflow.agents.researcher import ResearcherAgent
from writeflow.agents.thesis_architect import ThesisArchitectAgent
from writeflow.agents.real_novelty_gate import RealNoveltyGateAgent
from writeflow.agents.writer import WriterAgent
from writeflow.agents.devil_advocate import DevilAdvocateAgent
from writeflow.agents.judge import JudgeAgent
from writeflow.agents.editor import EditorAgent
from writeflow.core.debate_graph import DebateGraph, DebateTurn, Criticism
from writeflow.core.quality_gate import QualityGate, GateResult
from writeflow.config import get_settings
from writeflow.output import clean_final_article
from writeflow.progress import ProgressEvent

logger = logging.getLogger(__name__)


@dataclass
class QualityScores:
    """4项判浅评分"""
    概念克制: float = 0.0
    句子必要性: float = 0.0
    层次穿透: float = 0.0
    方案具体性: float = 0.0

    def total(self) -> float:
        """总分"""
        return (
            self.概念克制
            + self.句子必要性
            + self.层次穿透
            + self.方案具体性
        )

    def passed_dimensions(self, threshold: float = 8.0) -> List[str]:
        """获取达到阈值的维度"""
        return [k for k, v in self.__dict__.items() if v >= threshold]

    def failed_dimensions(self, threshold: float = 5.0) -> List[str]:
        """获取未达标的维度"""
        return [k for k, v in self.__dict__.items() if v < threshold]

    def to_dict(self) -> Dict[str, float]:
        return self.__dict__


@dataclass
class DebateSummary:
    """辩论摘要"""
    total_criticisms: int = 0
    resolved_criticisms: int = 0
    active_criticisms: int = 0
    key_issues: List[str] = field(default_factory=list)
    rounds: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_criticisms": self.total_criticisms,
            "resolved_criticisms": self.resolved_criticisms,
            "active_criticisms": self.active_criticisms,
            "key_issues": self.key_issues,
            "rounds": self.rounds,
        }


@dataclass
class TraceEvent:
    """One observable step in the multi-agent workflow."""

    stage: str
    agent: str
    round_number: Optional[int] = None
    input_summary: Dict[str, Any] = field(default_factory=dict)
    output: Any = field(default_factory=dict)
    attempt: int = 1
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stage": self.stage,
            "agent": self.agent,
            "round": self.round_number,
            "input_summary": self.input_summary,
            "output": self.output,
            "attempt": self.attempt,
            "created_at": self.created_at,
        }


class TraceEventBuffer(list):
    """Trace list with an optional sync callback for live observers."""

    def __init__(
        self,
        trace_callback: Optional[Callable[[TraceEvent], Any]] = None,
        human_interventions: Optional[List[Dict[str, Any]]] = None,
    ):
        super().__init__()
        self.trace_callback = trace_callback
        self.human_interventions = human_interventions


@dataclass
class BestFailedCandidate:
    """Highest-scoring draft retained when the workflow cannot pass the gate."""

    content: str
    scores: QualityScores
    gate_result: GateResult
    judge_output: Dict[str, Any]
    stage: str
    round_number: int
    total_score: float


@dataclass
class WriteResult:
    """写作结果"""
    content: str
    scores: QualityScores
    passed: bool
    pass_reason: str
    debate_summary: DebateSummary
    rounds: int
    task_id: str
    trace_events: List[TraceEvent] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "content": self.content,
            "scores": self.scores.to_dict(),
            "passed": self.passed,
            "pass_reason": self.pass_reason,
            "debate_summary": self.debate_summary.to_dict(),
            "rounds": self.rounds,
            "task_id": self.task_id,
            "trace_events": [event.to_dict() for event in self.trace_events],
        }


class WriteFlow:
    """
    批判性写作工作流

    被Claude Code直接调用，辅助完成批判性稿件创作。

    使用示例：
    ```python
    from writeflow import WriteFlow

    wf = WriteFlow()
    result = await wf.write("当代资本主义的结构性矛盾")
    print(result.content)
    print(result.passed)
    ```
    """

    def __init__(
        self,
        max_rounds: Optional[int] = None,
        min_rounds: Optional[int] = None,
        api_key: Optional[str] = None,
    ):
        """
        初始化工作流

        Args:
            max_rounds: 最大讨论轮次
            min_rounds: 最小讨论轮次
            api_key: Anthropic API Key（可选，从环境变量读取）
        """
        settings = get_settings()
        self.max_rounds = max_rounds or settings.max_rounds
        self.min_rounds = min_rounds or settings.min_rounds

        # 初始化Agent
        self.agents = {
            "observation_interviewer": ObservationInterviewerAgent(api_key=api_key),
            "local_voice_collector": LocalVoiceCollectorAgent(api_key=api_key),
            "researcher": ResearcherAgent(api_key=api_key),
            "thesis_architect": ThesisArchitectAgent(api_key=api_key),
            "real_novelty_gate": RealNoveltyGateAgent(api_key=api_key),
            "writer": WriterAgent(api_key=api_key),
            "devil_advocate": DevilAdvocateAgent(api_key=api_key),
            "judge": JudgeAgent(api_key=api_key),
            "editor": EditorAgent(api_key=api_key),
        }

        # 质量Gate
        self.gate = QualityGate()

        # 任务存储
        self._tasks: Dict[str, Dict[str, Any]] = {}

    async def write(
        self,
        topic: str,
        max_rounds: Optional[int] = None,
        context: Optional[Dict[str, Any]] = None,
        progress_callback: Optional[Callable[[ProgressEvent], Any]] = None,
        trace_callback: Optional[Callable[[TraceEvent], Any]] = None,
    ) -> WriteResult:
        """
        执行一次完整写作任务

        Args:
            topic: 写作主题
            max_rounds: 最大讨论轮次（覆盖默认值）
            context: 额外上下文
            progress_callback: 可选进度回调，每个阶段开始/结束/失败时调用
            trace_callback: 可选同步回调，每个 Agent 输出 trace 时调用

        Returns:
            WriteResult: 包含content, scores, passed, debate_summary
        """
        max_rounds = max_rounds or self.max_rounds
        task_id = str(uuid.uuid4())
        human_interventions: List[Dict[str, Any]] = list(
            context.get("human_interventions", []) if context else []
        )
        trace_events: List[TraceEvent] = TraceEventBuffer(
            trace_callback,
            human_interventions=human_interventions,
        )

        logger.info(f"Task {task_id}: Starting write for topic: {topic}")

        context = context or {}

        # Phase 0: 人类观察与真实声音
        await self._emit_progress(
            progress_callback,
            step="observation_interviewer",
            label="Observation Interviewer",
            status="started",
            message="整理人类观察",
        )
        observation_result = await self._interview_observation(
            task_id,
            topic,
            human_observation=context.get("human_observation", ""),
        )
        observation_brief = observation_result.get("observation_brief", {})
        self._record_trace(
            trace_events,
            stage="observation_interviewer",
            agent="observation_interviewer",
            input_summary={
                "topic": topic,
                "has_human_observation": bool(context.get("human_observation")),
            },
            output=observation_result,
        )
        await self._emit_progress(
            progress_callback,
            step="observation_interviewer",
            label="Observation Interviewer",
            status="completed",
            message=observation_result.get("source_status", "完成"),
        )

        await self._emit_progress(
            progress_callback,
            step="local_voice_collector",
            label="Local Voice Collector",
            status="started",
            message="收集或标准化本地真实声音",
        )
        local_voice_result = await self._collect_local_voices(
            task_id,
            topic,
            observation_brief=observation_brief,
            search_results=context.get("search_results", []),
            human_interventions=human_interventions,
        )
        local_voice_brief = local_voice_result.get("local_voice_brief", {})
        self._record_trace(
            trace_events,
            stage="local_voice_collector",
            agent="local_voice_collector",
            input_summary={
                "topic": topic,
                "search_results_count": len(context.get("search_results", []) or []),
            },
            output=local_voice_result,
        )
        await self._emit_progress(
            progress_callback,
            step="local_voice_collector",
            label="Local Voice Collector",
            status="completed",
            message=local_voice_result.get("source_status", "完成"),
        )

        # Phase 1: 素材收集
        await self._emit_progress(
            progress_callback,
            step="researcher",
            label="Researcher",
            status="started",
            message="整理参考素材",
        )
        materials = await self._collect_materials(
            task_id,
            topic,
            observation_brief=observation_brief,
            local_voice_brief=local_voice_brief,
            human_interventions=human_interventions,
        )
        self._record_trace(
            trace_events,
            stage="researcher_materials",
            agent="researcher",
            input_summary={
                "topic": topic,
                "has_observation": bool(observation_brief),
                "local_voice_count": len(local_voice_brief.get("voices", []))
                if isinstance(local_voice_brief, dict)
                else 0,
            },
            output={"materials": materials},
        )
        await self._emit_progress(
            progress_callback,
            step="researcher",
            label="Researcher",
            status="completed",
            message=f"{len(materials)} materials",
        )

        await self._emit_progress(
            progress_callback,
            step="thesis_architect",
            label="Thesis Architect",
            status="started",
            attempt=1,
            message="生成核心判断",
        )
        thesis = await self._build_thesis(
            task_id,
            topic,
            materials,
            observation_brief=observation_brief,
            local_voice_brief=local_voice_brief,
            human_interventions=human_interventions,
        )
        self._record_trace(
            trace_events,
            stage="thesis_architect_brief",
            agent="thesis_architect",
            input_summary={
                "topic": topic,
                "materials_count": len(materials),
                "has_observation": bool(observation_brief),
                "local_voice_count": len(local_voice_brief.get("voices", []))
                if isinstance(local_voice_brief, dict)
                else 0,
            },
            output=thesis,
        )
        await self._emit_progress(
            progress_callback,
            step="thesis_architect",
            label="Thesis Architect",
            status="completed",
            attempt=1,
            message="核心判断已生成",
        )

        await self._emit_progress(
            progress_callback,
            step="real_novelty_gate",
            label="Real Novelty Gate",
            status="started",
            attempt=1,
            message="检查真实新意资产",
        )
        novelty_result = await self._run_real_novelty_gate(
            task_id,
            topic,
            observation_brief=observation_brief,
            local_voice_brief=local_voice_brief,
            materials=materials,
            thesis=thesis,
            human_interventions=human_interventions,
        )
        novelty_decision = (
            "passed, sent to Writer"
            if novelty_result.get("passed")
            else "failed, sent back to Thesis Architect"
        )
        novelty_trace_output = {**novelty_result, "decision": novelty_decision}
        self._record_trace(
            trace_events,
            stage="real_novelty_gate",
            agent="real_novelty_gate",
            attempt=1,
            input_summary={
                "topic": topic,
                "thesis_core_claim": thesis.get("core_claim", ""),
                "novelty_retry": False,
            },
            output=novelty_trace_output,
        )
        await self._emit_progress(
            progress_callback,
            step="real_novelty_gate",
            label="Real Novelty Gate",
            status="completed" if novelty_result.get("passed") else "failed",
            attempt=1,
            message=novelty_decision
            if novelty_result.get("passed")
            else novelty_result.get("pass_reason", "no_real_novelty"),
        )
        if not novelty_result.get("passed"):
            await self._emit_progress(
                progress_callback,
                step="thesis_architect",
                label="Thesis Architect",
                status="started",
                attempt=2,
                message="退回后重建核心判断",
            )
            thesis = await self._build_thesis(
                task_id,
                topic,
                materials,
                observation_brief=observation_brief,
                local_voice_brief=local_voice_brief,
                novelty_feedback=novelty_result,
                human_interventions=human_interventions,
            )
            self._record_trace(
                trace_events,
                stage="thesis_architect_brief",
                agent="thesis_architect",
                attempt=2,
                input_summary={
                    "topic": topic,
                    "materials_count": len(materials),
                    "novelty_retry": True,
                },
                output=thesis,
            )
            await self._emit_progress(
                progress_callback,
                step="thesis_architect",
                label="Thesis Architect",
                status="completed",
                attempt=2,
                message="重建核心判断完成",
            )
            await self._emit_progress(
                progress_callback,
                step="real_novelty_gate",
                label="Real Novelty Gate",
                status="started",
                attempt=2,
                message="复检真实新意资产",
            )
            novelty_result = await self._run_real_novelty_gate(
                task_id,
                topic,
                observation_brief=observation_brief,
                local_voice_brief=local_voice_brief,
                materials=materials,
                thesis=thesis,
                human_interventions=human_interventions,
            )
            novelty_decision = (
                "passed, sent to Writer"
                if novelty_result.get("passed")
                else "failed again, stopped before Writer"
            )
            novelty_trace_output = {**novelty_result, "decision": novelty_decision}
            self._record_trace(
                trace_events,
                stage="real_novelty_gate",
                agent="real_novelty_gate",
                attempt=2,
                input_summary={
                    "topic": topic,
                    "thesis_core_claim": thesis.get("core_claim", ""),
                    "novelty_retry": True,
                },
                output=novelty_trace_output,
            )
            await self._emit_progress(
                progress_callback,
                step="real_novelty_gate",
                label="Real Novelty Gate",
                status="completed" if novelty_result.get("passed") else "failed",
                attempt=2,
                message=novelty_decision
                if novelty_result.get("passed")
                else novelty_result.get("pass_reason", "no_real_novelty"),
            )

        novelty_assets = novelty_result.get("novelty_assets", [])
        if not novelty_result.get("passed"):
            await self._emit_progress(
                progress_callback,
                step="writer_draft",
                label="Writer Draft",
                status="skipped",
                message="停止：没有真实新意资产，不进入 Writer",
            )
            self._record_trace(
                trace_events,
                stage="final_article",
                agent="writeflow",
                input_summary={"topic": topic},
                output={"content": ""},
            )
            debate_summary = DebateSummary(
                key_issues=novelty_result.get("recommendations", []),
                rounds=0,
            )
            return WriteResult(
                content="",
                scores=QualityScores(),
                passed=False,
                pass_reason=novelty_result.get("pass_reason", "no_real_novelty"),
                debate_summary=debate_summary,
                rounds=0,
                task_id=task_id,
                trace_events=trace_events,
            )

        # Phase 2-N: 讨论循环
        debate_graph = DebateGraph()
        content = ""
        current_scores = QualityScores()
        gate_result: Optional[GateResult] = None
        rewrite_feedback: Dict[str, Any] = {}
        completed_rounds = 0
        best_failed_candidate: Optional[BestFailedCandidate] = None

        for round_num in range(1, max_rounds + 1):
            completed_rounds = round_num
            logger.info(f"Task {task_id}: Round {round_num}")

            # 2a: Writer生成或根据上一轮判浅反馈重写
            await self._emit_progress(
                progress_callback,
                step="writer_draft",
                label="Writer Draft",
                status="started",
                round_number=round_num,
                message="生成或重写初稿",
            )
            content = await self._write_content(
                task_id,
                topic,
                materials,
                thesis,
                observation_brief,
                local_voice_brief,
                novelty_assets,
                rewrite_feedback.get("depth_questions", []),
                round_num,
                content,
                rewrite_feedback,
                human_interventions,
            )
            self._record_trace(
                trace_events,
                stage="writer_draft",
                agent="writer",
                round_number=round_num,
                input_summary={
                    "topic": topic,
                    "materials_count": len(materials),
                    "core_claim": thesis.get("core_claim", ""),
                },
                output={"content": content},
            )
            await self._emit_progress(
                progress_callback,
                step="writer_draft",
                label="Writer Draft",
                status="completed",
                round_number=round_num,
                message=f"{len(content)} chars",
            )

            # 2b: Depth Judge初检。浅稿先退回Writer，不进入Devil Advocate。
            await self._emit_progress(
                progress_callback,
                step="judge_precheck",
                label="Depth Judge Precheck",
                status="started",
                round_number=round_num,
                message="判浅初检",
            )
            gate_result, judge_output = await self._judge_content(
                task_id,
                topic,
                content,
                criticisms=[],
                materials=materials,
                thesis=thesis,
                novelty_assets=novelty_assets,
                human_interventions=human_interventions,
            )
            current_scores = self._parse_scores(gate_result)
            best_failed_candidate = self._select_best_failed_candidate(
                best_failed_candidate,
                content=content,
                gate_result=gate_result,
                judge_output=judge_output,
                stage="judge_precheck",
                round_number=round_num,
            )
            precheck_output = {
                "agent_result": judge_output,
                "gate_result": self._gate_result_to_dict(gate_result),
            }

            if gate_result.passed:
                precheck_output["decision"] = "Depth precheck passed; sent to Devil Advocate"
            else:
                precheck_output["decision"] = "Judge failed, sent back to Writer"

            self._record_trace(
                trace_events,
                stage="judge_precheck",
                agent="judge",
                round_number=round_num,
                input_summary={
                    "content_chars": len(content),
                    "criticisms_count": 0,
                },
                output=precheck_output,
            )
            await self._emit_progress(
                progress_callback,
                step="judge_precheck",
                label="Depth Judge Precheck",
                status="completed" if gate_result.passed else "failed",
                round_number=round_num,
                message=precheck_output["decision"],
            )

            if not gate_result.passed:
                rewrite_feedback = self._build_rewrite_feedback(
                    gate_result=gate_result,
                    judge_output=judge_output,
                    criticisms=[],
                    phase="judge_precheck",
                )
                if round_num < max_rounds:
                    continue
                break

            # 2c: Devil's Advocate质疑
            await self._emit_progress(
                progress_callback,
                step="devil_advocate",
                label="Devil Advocate",
                status="started",
                round_number=round_num,
                message="提出反方质疑",
            )
            criticisms = await self._criticize(
                task_id,
                topic,
                content,
                materials,
                round_num,
                debate_graph,
                human_interventions,
            )
            self._record_trace(
                trace_events,
                stage="devil_advocate_criticisms",
                agent="devil_advocate",
                round_number=round_num,
                input_summary={
                    "content_chars": len(content),
                    "materials_count": len(materials),
                },
                output={"criticisms": criticisms},
            )
            await self._emit_progress(
                progress_callback,
                step="devil_advocate",
                label="Devil Advocate",
                status="completed",
                round_number=round_num,
                message=f"{len(criticisms)} criticisms",
            )

            # 2d: Writer直接修订正文，而不是输出辩护说明
            source_content = content
            await self._emit_progress(
                progress_callback,
                step="writer_revision",
                label="Writer Revision",
                status="started",
                round_number=round_num,
                message="根据 Judge 和质疑修订正文",
            )
            content = await self._revise_content(
                task_id,
                topic,
                materials,
                thesis,
                observation_brief,
                local_voice_brief,
                novelty_assets,
                (judge_output.get("depth_questions") or gate_result.depth_questions),
                round_num,
                source_content,
                self._build_rewrite_feedback(
                    gate_result=gate_result,
                    judge_output=judge_output,
                    criticisms=[],
                    phase="judge_precheck",
                ),
                criticisms,
                human_interventions,
            )
            self._record_trace(
                trace_events,
                stage="writer_revision",
                agent="writer",
                round_number=round_num,
                input_summary={
                    "source_content_chars": len(source_content),
                    "criticisms_count": len(criticisms),
                },
                output={"content": content},
            )
            await self._emit_progress(
                progress_callback,
                step="writer_revision",
                label="Writer Revision",
                status="completed",
                round_number=round_num,
                message=f"{len(content)} chars",
            )

            # 2e: 修订稿再次判浅，通过后才进入Editor
            await self._emit_progress(
                progress_callback,
                step="judge_final",
                label="Depth Judge Final",
                status="started",
                round_number=round_num,
                message="终检修订稿",
            )
            gate_result, judge_output = await self._judge_content(
                task_id,
                topic,
                content,
                criticisms=criticisms,
                materials=materials,
                thesis=thesis,
                novelty_assets=novelty_assets,
                human_interventions=human_interventions,
            )
            current_scores = self._parse_scores(gate_result)
            best_failed_candidate = self._select_best_failed_candidate(
                best_failed_candidate,
                content=content,
                gate_result=gate_result,
                judge_output=judge_output,
                stage="judge_final",
                round_number=round_num,
            )
            self._record_trace(
                trace_events,
                stage="judge_final",
                agent="judge",
                round_number=round_num,
                input_summary={
                    "content_chars": len(content),
                    "criticisms_count": len(criticisms),
                },
                output={
                    "agent_result": judge_output,
                    "gate_result": self._gate_result_to_dict(gate_result),
                    "decision": (
                        "Depth final passed; sent to Editor"
                        if gate_result.passed
                        else "Judge failed, sent back to Writer"
                    ),
                },
            )
            await self._emit_progress(
                progress_callback,
                step="judge_final",
                label="Depth Judge Final",
                status="completed" if gate_result.passed else "failed",
                round_number=round_num,
                message=(
                    "Depth final passed; sent to Editor"
                    if gate_result.passed
                    else "Judge failed, sent back to Writer"
                ),
            )

            # 检查是否通过
            if gate_result.passed:
                logger.info(f"Task {task_id}: Passed at round {round_num}")
                break

            rewrite_feedback = self._build_rewrite_feedback(
                gate_result=gate_result,
                judge_output=judge_output,
                criticisms=criticisms,
                phase="judge_final",
            )

        # Phase N+1: Editor打磨
        if gate_result and gate_result.passed:
            await self._emit_progress(
                progress_callback,
                step="editor",
                label="Editor",
                status="started",
                message="最终编辑清洗",
            )
            editor_raw, content = await self._edit_content(
                task_id,
                content,
                current_scores,
                thesis,
                observation_brief,
                human_interventions,
            )
            self._record_trace(
                trace_events,
                stage="editor_raw",
                agent="editor",
                input_summary={"source_content_chars": len(editor_raw)},
                output={"raw_content": editor_raw, "clean_content": content},
            )
            await self._emit_progress(
                progress_callback,
                step="editor",
                label="Editor",
                status="completed",
                message=f"{len(content)} chars",
            )
        else:
            await self._emit_progress(
                progress_callback,
                step="editor",
                label="Editor",
                status="skipped",
                message="未通过 Gate，跳过 Editor",
            )
            if best_failed_candidate:
                content = self._build_best_failed_candidate_content(
                    best_failed_candidate,
                    completed_rounds=completed_rounds,
                )
                current_scores = best_failed_candidate.scores
                gate_result = best_failed_candidate.gate_result
                self._record_trace(
                    trace_events,
                    stage="best_failed_candidate",
                    agent="writeflow",
                    round_number=best_failed_candidate.round_number,
                    input_summary={
                        "completed_rounds": completed_rounds,
                        "candidate_stage": best_failed_candidate.stage,
                    },
                    output={
                        "decision": "Max rounds reached; saved highest-scoring failed candidate",
                        "total_score": best_failed_candidate.total_score,
                        "scores": best_failed_candidate.scores.to_dict(),
                        "pass_reason": best_failed_candidate.gate_result.reason,
                        "failed_dimensions": best_failed_candidate.gate_result.failed_dimensions,
                    },
                )

        content = clean_final_article(content)
        self._record_trace(
            trace_events,
            stage="final_article",
            agent="writeflow",
            input_summary={"topic": topic},
            output={"content": content},
        )

        # 构建结果
        debate_summary = DebateSummary(
            total_criticisms=debate_graph.total_criticisms,
            resolved_criticisms=debate_graph.resolved_count,
            active_criticisms=debate_graph.active_count,
            key_issues=gate_result.recommendations if gate_result else [],
            rounds=completed_rounds,
        )

        return WriteResult(
            content=content,
            scores=current_scores,
            passed=gate_result.passed if gate_result else False,
            pass_reason=gate_result.reason if gate_result else "unknown",
            debate_summary=debate_summary,
            rounds=completed_rounds,
            task_id=task_id,
            trace_events=trace_events,
        )

    async def batch_write(
        self,
        topics: List[str],
        max_rounds: Optional[int] = None,
    ) -> List[WriteResult]:
        """
        批量写作

        Args:
            topics: 主题列表
            max_rounds: 最大讨论轮次

        Returns:
            List[WriteResult]: 每篇的结果
        """
        results = []
        for topic in topics:
            try:
                result = await self.write(topic, max_rounds)
                results.append(result)
            except Exception as e:
                logger.error(f"Task failed for topic {topic}: {e}")
                results.append(WriteResult(
                    content="",
                    scores=QualityScores(),
                    passed=False,
                    pass_reason=f"error: {str(e)}",
                    debate_summary=DebateSummary(),
                    rounds=0,
                    task_id="",
                    trace_events=[],
                ))
        return results

    async def _interview_observation(
        self,
        task_id: str,
        topic: str,
        human_observation: str = "",
    ) -> Dict[str, Any]:
        """整理用户提供的人类观察；没有观察时只返回问题清单。"""
        return await self.agents["observation_interviewer"].process({
            "task_id": task_id,
            "topic": topic,
            "human_observation": human_observation,
        })

    async def _collect_local_voices(
        self,
        task_id: str,
        topic: str,
        observation_brief: Dict[str, Any],
        search_results: Optional[List[Dict[str, Any]]] = None,
        human_interventions: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """收集或标准化真实声音；无搜索配置时不得编造引语。"""
        return await self.agents["local_voice_collector"].process({
            "task_id": task_id,
            "topic": topic,
            "observation_brief": observation_brief,
            "search_results": search_results or [],
            "human_interventions": human_interventions or [],
        })

    async def _collect_materials(
        self,
        task_id: str,
        topic: str,
        observation_brief: Optional[Dict[str, Any]] = None,
        local_voice_brief: Optional[Dict[str, Any]] = None,
        human_interventions: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """素材收集"""
        result = await self.agents["researcher"].process({
            "task_id": task_id,
            "topic": topic,
            "observation_brief": observation_brief or {},
            "local_voice_brief": local_voice_brief or {},
            "human_interventions": human_interventions or [],
            "material_types": ["data", "case", "theory", "quote", "history"],
            "depth_level": "deep",
        })
        return result.get("materials", [])

    async def _build_thesis(
        self,
        task_id: str,
        topic: str,
        materials: List[Dict[str, Any]],
        observation_brief: Optional[Dict[str, Any]] = None,
        local_voice_brief: Optional[Dict[str, Any]] = None,
        novelty_feedback: Optional[Dict[str, Any]] = None,
        human_interventions: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Build the core thesis brief before drafting."""
        result = await self.agents["thesis_architect"].process({
            "task_id": task_id,
            "topic": topic,
            "materials": self._materials_with_human_interventions(
                materials,
                human_interventions,
            ),
            "observation_brief": observation_brief or {},
            "local_voice_brief": local_voice_brief or {},
            "novelty_feedback": novelty_feedback or {},
            "human_interventions": human_interventions or [],
        })
        known_fields = {
            "core_claim",
            "conflict_with_common_view",
            "common_sense_overturned",
            "strongest_evidence",
            "most_dangerous_counterargument",
            "novelty_assets",
        }
        thesis = {
            "core_claim": result.get("core_claim", ""),
            "conflict_with_common_view": result.get("conflict_with_common_view", ""),
            "common_sense_overturned": result.get("common_sense_overturned", ""),
            "strongest_evidence": result.get("strongest_evidence", ""),
            "most_dangerous_counterargument": result.get(
                "most_dangerous_counterargument", ""
            ),
            "novelty_assets": result.get("novelty_assets", []),
            **{key: value for key, value in result.items() if key not in known_fields},
        }
        preserved = self._observation_hard_requirements(observation_brief or {})
        if preserved and not thesis.get("preserved_human_requirements"):
            thesis["preserved_human_requirements"] = preserved
        return thesis

    async def _run_real_novelty_gate(
        self,
        task_id: str,
        topic: str,
        observation_brief: Dict[str, Any],
        local_voice_brief: Dict[str, Any],
        materials: List[Dict[str, Any]],
        thesis: Dict[str, Any],
        human_interventions: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Run the one-vote novelty gate before drafting."""
        return await self.agents["real_novelty_gate"].process({
            "task_id": task_id,
            "topic": topic,
            "observation_brief": observation_brief,
            "local_voice_brief": local_voice_brief,
            "materials": self._materials_with_human_interventions(
                materials,
                human_interventions,
            ),
            "thesis": thesis,
            "human_interventions": human_interventions or [],
        })

    async def _write_content(
        self,
        task_id: str,
        topic: str,
        materials: List[Dict],
        thesis: Dict[str, Any],
        observation_brief: Dict[str, Any],
        local_voice_brief: Dict[str, Any],
        novelty_assets: List[Dict[str, Any]],
        depth_questions: List[Dict[str, Any]],
        round_num: int,
        previous_content: str,
        rewrite_feedback: Optional[Dict[str, Any]] = None,
        human_interventions: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """写作阶段"""
        previous_rounds = []
        if previous_content or rewrite_feedback:
            previous_rounds.append({
                "round": round_num - 1,
                "writer_output": previous_content,
                "judge_feedback": rewrite_feedback or {},
            })

        result = await self.agents["writer"].process({
            "task_id": task_id,
            "round": round_num,
            "mode": "write",
            "topic": topic,
            "materials": self._materials_with_human_interventions(
                materials,
                human_interventions,
            ),
            "thesis": thesis,
            "observation_brief": observation_brief,
            "local_voice_brief": local_voice_brief,
            "novelty_assets": novelty_assets,
            "depth_questions": depth_questions,
            "previous_rounds": previous_rounds,
            "rewrite_feedback": rewrite_feedback or {},
            "human_interventions": human_interventions or [],
        })
        return result.get("content", "")

    async def _revise_content(
        self,
        task_id: str,
        topic: str,
        materials: List[Dict],
        thesis: Dict[str, Any],
        observation_brief: Dict[str, Any],
        local_voice_brief: Dict[str, Any],
        novelty_assets: List[Dict[str, Any]],
        depth_questions: List[Dict[str, Any]],
        round_num: int,
        content: str,
        judge_feedback: Dict[str, Any],
        criticisms: List[Dict],
        human_interventions: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """根据Judge和Devil Advocate反馈直接修订正文。"""
        result = await self.agents["writer"].process({
            "task_id": task_id,
            "round": round_num,
            "mode": "revision",
            "topic": topic,
            "materials": self._materials_with_human_interventions(
                materials,
                human_interventions,
            ),
            "thesis": thesis,
            "observation_brief": observation_brief,
            "local_voice_brief": local_voice_brief,
            "novelty_assets": novelty_assets,
            "depth_questions": depth_questions,
            "content": content,
            "judge_feedback": judge_feedback,
            "criticisms": criticisms,
            "human_interventions": human_interventions or [],
        })
        return result.get("content", content)

    async def _criticize(
        self,
        task_id: str,
        topic: str,
        content: str,
        materials: List[Dict],
        round_num: int,
        debate_graph: DebateGraph,
        human_interventions: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict]:
        """质疑阶段"""
        previous_criticisms = []
        for turn in debate_graph.turns:
            for c in turn.criticisms:
                previous_criticisms.append(c)

        result = await self.agents["devil_advocate"].process({
            "task_id": task_id,
            "round": round_num,
            "content": content,
            "topic": topic,
            "materials": self._materials_with_human_interventions(
                materials,
                human_interventions,
            ),
            "previous_criticisms": previous_criticisms,
            "human_interventions": human_interventions or [],
        })

        criticisms = result.get("criticisms", [])

        # 更新辩论图谱
        turn = DebateTurn(
            turn_id=str(uuid.uuid4()),
            round_number=round_num,
            agent_id="devil_advocate",
            criticisms=[
                Criticism(
                    criticism_id=f"C{len(debate_graph.turns) * 10 + i + 1}",
                    dimension=c.get("dimension", "unknown"),
                    question=c.get("question", ""),
                    analysis=c.get("analysis", ""),
                    consequence=c.get("consequence", ""),
                    threat_level=c.get("threat_level", "中等"),
                    created_round=round_num,
                    current_round=round_num,
                )
                for i, c in enumerate(criticisms)
            ],
        )
        debate_graph.add_turn(turn)

        return criticisms

    async def _defend(
        self,
        task_id: str,
        content: str,
        criticisms: List[Dict],
        round_num: int,
    ) -> str:
        """辩护阶段"""
        if not criticisms:
            return ""

        result = await self.agents["writer"].process({
            "task_id": task_id,
            "round": round_num,
            "mode": "defense",
            "content": content,
            "criticisms": criticisms,
        })
        return result.get("content", "")

    async def _judge(
        self,
        task_id: str,
        topic: str,
        content: str,
        criticisms: List[Dict],
        defenses: str,
        materials: List[Dict],
    ) -> tuple[GateResult, Dict[str, Any]]:
        """评估阶段"""
        return await self._judge_content(
            task_id,
            topic,
            content,
            criticisms=criticisms,
            materials=materials,
            defenses=defenses,
        )

    async def _judge_content(
        self,
        task_id: str,
        topic: str,
        content: str,
        *,
        criticisms: List[Dict],
        materials: List[Dict],
        thesis: Optional[Dict[str, Any]] = None,
        novelty_assets: Optional[List[Dict[str, Any]]] = None,
        defenses: str = "",
        human_interventions: Optional[List[Dict[str, Any]]] = None,
    ) -> tuple[GateResult, Dict[str, Any]]:
        """统一执行Depth Judge和Quality Gate。"""
        result = await self.agents["judge"].process({
            "task_id": task_id,
            "content": content,
            "topic": topic,
            "criticisms": criticisms,
            "defenses": defenses,
            "materials": self._materials_with_human_interventions(
                materials,
                human_interventions,
            ),
            "thesis": thesis or {},
            "novelty_assets": novelty_assets or [],
            "human_interventions": human_interventions or [],
        })

        scores = self._parse_scores_from_result(result)
        return self.gate.evaluate(
            scores.to_dict(),
            depth_questions=result.get("depth_questions", []),
        ), result

    async def _edit_content(
        self,
        task_id: str,
        content: str,
        scores: QualityScores,
        thesis: Optional[Dict[str, Any]] = None,
        observation_brief: Optional[Dict[str, Any]] = None,
        human_interventions: Optional[List[Dict[str, Any]]] = None,
    ) -> tuple[str, str]:
        """编辑阶段"""
        result = await self.agents["editor"].process({
            "task_id": task_id,
            "content": content,
            "quality_scores": scores.to_dict(),
            "key_issues": scores.failed_dimensions(5.0),
            "criticisms": [],
            "thesis": thesis or {},
            "observation_brief": observation_brief or {},
            "human_interventions": human_interventions or [],
        })
        raw_content = result.get("content", content)
        return raw_content, clean_final_article(raw_content)

    def _select_best_failed_candidate(
        self,
        current: Optional[BestFailedCandidate],
        *,
        content: str,
        gate_result: GateResult,
        judge_output: Dict[str, Any],
        stage: str,
        round_number: int,
    ) -> Optional[BestFailedCandidate]:
        """Keep the highest-scoring failed draft for fallback output."""
        if not content.strip() or gate_result.passed:
            return current

        scores = self._parse_scores(gate_result)
        total_score = gate_result.total_score
        candidate = BestFailedCandidate(
            content=content,
            scores=scores,
            gate_result=gate_result,
            judge_output=judge_output,
            stage=stage,
            round_number=round_number,
            total_score=total_score,
        )
        if current is None:
            return candidate
        if candidate.total_score > current.total_score:
            return candidate
        if (
            candidate.total_score == current.total_score
            and candidate.stage == "judge_final"
            and current.stage != "judge_final"
        ):
            return candidate
        return current

    def _build_best_failed_candidate_content(
        self,
        candidate: BestFailedCandidate,
        *,
        completed_rounds: int,
    ) -> str:
        """Append failure diagnostics to the highest-scoring failed draft."""
        body = clean_final_article(candidate.content).rstrip()
        appendix = self._render_failure_appendix(candidate, completed_rounds=completed_rounds)
        return f"{body}\n\n---\n\n{appendix}\n" if body else f"{appendix}\n"

    def _render_failure_appendix(
        self,
        candidate: BestFailedCandidate,
        *,
        completed_rounds: int,
    ) -> str:
        gate_result = candidate.gate_result
        lines = [
            "## 未通过原因",
            "",
            "这是完整流程结束后保留下来的最高评分候选稿，尚未通过 Depth Judge。",
            "",
            f"- 完成轮次：{completed_rounds}",
            f"- 候选来源：第 {candidate.round_number} 轮 `{candidate.stage}`",
            f"- 最高评分：{candidate.total_score:g} / 40",
            f"- Gate 结果：未通过",
            f"- 失败原因：{gate_result.reason}",
        ]

        failed_dimensions = gate_result.failed_dimensions
        if failed_dimensions:
            lines.append("- 未达标维度：" + "、".join(failed_dimensions))

        score_parts = [
            f"{name} {value:g}"
            for name, value in candidate.scores.to_dict().items()
        ]
        if score_parts:
            lines.append("- 四项评分：" + "；".join(score_parts))

        depth_questions = [
            question
            for question in gate_result.depth_questions
            if question.get("status") in {"missing", "not_deep_enough"}
        ]
        if depth_questions:
            lines.extend(["", "### 仍需处理的追问", ""])
            for question in depth_questions:
                status = question.get("status", "")
                text = question.get("question", "")
                revision = question.get("required_revision", "")
                lines.append(f"- [{status}] {text}")
                if revision:
                    lines.append(f"  建议：{revision}")

        recommendations = gate_result.recommendations or candidate.judge_output.get(
            "recommendations",
            [],
        )
        if recommendations:
            lines.extend(["", "### 修改建议", ""])
            for item in recommendations:
                if str(item).strip():
                    lines.append(f"- {str(item).strip()}")

        key_issues = candidate.judge_output.get("key_issues", [])
        if key_issues:
            lines.extend(["", "### Judge 标出的主要问题", ""])
            for item in key_issues:
                if str(item).strip():
                    lines.append(f"- {str(item).strip()}")

        return "\n".join(lines).rstrip()

    def _record_trace(
        self,
        trace_events: List[TraceEvent],
        *,
        stage: str,
        agent: str,
        round_number: Optional[int] = None,
        attempt: int = 1,
        input_summary: Optional[Dict[str, Any]] = None,
        output: Any = None,
    ) -> None:
        event = TraceEvent(
            stage=stage,
            agent=agent,
            round_number=round_number,
            attempt=attempt,
            input_summary=input_summary or {},
            output=output or {},
        )
        trace_events.append(event)
        trace_callback = getattr(trace_events, "trace_callback", None)
        if trace_callback is not None:
            feedback = trace_callback(event)
            intervention = self._normalize_human_intervention(feedback, event)
            interventions = getattr(trace_events, "human_interventions", None)
            if intervention and interventions is not None:
                interventions.append(intervention)

    def _normalize_human_intervention(
        self,
        feedback: Any,
        event: TraceEvent,
    ) -> Optional[Dict[str, Any]]:
        """Normalize optional live user feedback collected after a trace event."""
        if not feedback:
            return None
        if isinstance(feedback, str):
            content = feedback.strip()
            raw: Dict[str, Any] = {}
        elif isinstance(feedback, dict):
            content = str(feedback.get("content", "") or "").strip()
            raw = feedback
        else:
            return None
        if not content:
            return None
        return {
            "content": content,
            "after_stage": str(raw.get("after_stage") or event.stage),
            "after_agent": str(raw.get("after_agent") or event.agent),
            "round": raw.get("round", event.round_number),
            "attempt": raw.get("attempt", event.attempt),
            "created_at": str(
                raw.get("created_at")
                or datetime.now(timezone.utc)
                .isoformat(timespec="seconds")
                .replace("+00:00", "Z")
            ),
        }

    def _human_interventions_prompt(self, interventions: List[Dict[str, Any]]) -> str:
        if not interventions:
            return ""
        lines = ["【运行中人工补充】", "这些内容来自 Web 工作台，优先作为用户新增事实、方向或修改要求处理。"]
        for index, item in enumerate(interventions[-8:], 1):
            source = item.get("after_agent") or item.get("after_stage") or "unknown"
            round_number = item.get("round")
            suffix = f"，第 {round_number} 轮" if round_number is not None else ""
            lines.append(f"{index}. 在 {source}{suffix} 之后补充：{item.get('content', '')}")
        return "\n".join(lines)

    def _observation_hard_requirements(
        self,
        observation_brief: Dict[str, Any],
    ) -> List[str]:
        requirements: List[str] = []
        for key in (
            "user_requirements",
            "must_preserve_details",
            "raw_human_observation",
        ):
            value = observation_brief.get(key)
            if isinstance(value, list):
                requirements.extend(str(item).strip() for item in value if str(item).strip())
            elif value:
                requirements.append(str(value).strip())
        return requirements

    def _materials_with_human_interventions(
        self,
        materials: List[Dict[str, Any]],
        interventions: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        enriched = list(materials or [])
        for item in (interventions or [])[-8:]:
            content = str(item.get("content", "")).strip()
            if not content:
                continue
            enriched.append(
                {
                    "material_type": "human_intervention",
                    "source": "web_runtime_input",
                    "content": content,
                }
            )
        return enriched

    async def _emit_progress(
        self,
        progress_callback: Optional[Callable[[ProgressEvent], Any]],
        *,
        step: str,
        label: str,
        status: str,
        attempt: int = 1,
        message: str = "",
        round_number: Optional[int] = None,
    ) -> None:
        """Emit one live progress event to an optional callback."""
        if progress_callback is None:
            return

        event = ProgressEvent(
            step=step,
            label=label,
            status=status,
            attempt=attempt,
            message=message,
            round_number=round_number,
        )
        result = progress_callback(event)
        if inspect.isawaitable(result):
            await result

    def _gate_result_to_dict(self, gate_result: GateResult) -> Dict[str, Any]:
        return {
            "passed": gate_result.passed,
            "reason": gate_result.reason,
            "quality_scores": gate_result.quality_scores.scores,
            "excellent_dimensions": gate_result.excellent_dimensions,
            "failed_dimensions": gate_result.failed_dimensions,
            "total_score": gate_result.total_score,
            "recommendations": gate_result.recommendations,
            "depth_questions": gate_result.depth_questions,
        }

    def _build_rewrite_feedback(
        self,
        *,
        gate_result: GateResult,
        judge_output: Dict[str, Any],
        criticisms: List[Dict],
        phase: str,
    ) -> Dict[str, Any]:
        """Build compact feedback for the next Writer rewrite/revision."""
        return {
            "phase": phase,
            "passed": gate_result.passed,
            "pass_reason": gate_result.reason,
            "quality_scores": gate_result.quality_scores.scores,
            "failed_dimensions": gate_result.failed_dimensions,
            "key_issues": judge_output.get("key_issues", []),
            "recommendations": gate_result.recommendations
            or judge_output.get("recommendations", []),
            "depth_questions": gate_result.depth_questions
            or judge_output.get("depth_questions", []),
            "criticisms": criticisms,
        }

    def _parse_scores(self, gate_result: GateResult) -> QualityScores:
        """从GateResult解析评分"""
        if not gate_result:
            return QualityScores()

        qs = gate_result.quality_scores
        if isinstance(qs, dict):
            return self._scores_from_dict(qs)

        if hasattr(qs, "scores"):
            return self._scores_from_dict(qs.scores)

        return QualityScores()

    def _parse_scores_from_result(self, result: Dict) -> QualityScores:
        """从Agent结果解析评分"""
        scores_dict = result.get("quality_scores", {})
        if not scores_dict:
            return QualityScores()

        return self._scores_from_dict(scores_dict)

    def _scores_from_dict(self, scores_dict: Dict[str, Any]) -> QualityScores:
        """Map raw judge scores to the four depth-check dimensions."""
        return QualityScores(
            概念克制=self._coerce_score(scores_dict.get("概念克制", 0)),
            句子必要性=self._coerce_score(scores_dict.get("句子必要性", 0)),
            层次穿透=self._coerce_score(scores_dict.get("层次穿透", 0)),
            方案具体性=self._coerce_score(scores_dict.get("方案具体性", 0)),
        )

    @staticmethod
    def _coerce_score(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0
