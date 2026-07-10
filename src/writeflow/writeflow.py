"""
WriteFlow - 批判性写作工作流
"""
from __future__ import annotations

import uuid
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from writeflow.agents.researcher import ResearcherAgent
from writeflow.agents.thesis_architect import ThesisArchitectAgent
from writeflow.agents.writer import WriterAgent
from writeflow.agents.devil_advocate import DevilAdvocateAgent
from writeflow.agents.judge import JudgeAgent
from writeflow.agents.editor import EditorAgent
from writeflow.core.debate_graph import DebateGraph, DebateTurn, Criticism
from writeflow.core.quality_gate import QualityGate, GateResult
from writeflow.config import get_settings
from writeflow.output import clean_final_article

logger = logging.getLogger(__name__)


@dataclass
class QualityScores:
    """5项判浅评分"""
    新判断: float = 0.0
    概念克制: float = 0.0
    句子必要性: float = 0.0
    层次穿透: float = 0.0
    方案具体性: float = 0.0

    def total(self) -> float:
        """总分"""
        return (
            self.新判断
            + self.概念克制
            + self.句子必要性
            + self.层次穿透
            + self.方案具体性
        )

    def passed_dimensions(self, threshold: float = 8.0) -> List[str]:
        """获取达到阈值的维度"""
        return [k for k, v in self.__dict__.items() if v >= threshold]

    def failed_dimensions(self, threshold: float = 6.0) -> List[str]:
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
            "created_at": self.created_at,
        }


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
            "researcher": ResearcherAgent(api_key=api_key),
            "thesis_architect": ThesisArchitectAgent(api_key=api_key),
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
    ) -> WriteResult:
        """
        执行一次完整写作任务

        Args:
            topic: 写作主题
            max_rounds: 最大讨论轮次（覆盖默认值）
            context: 额外上下文

        Returns:
            WriteResult: 包含content, scores, passed, debate_summary
        """
        max_rounds = max_rounds or self.max_rounds
        task_id = str(uuid.uuid4())
        trace_events: List[TraceEvent] = []

        logger.info(f"Task {task_id}: Starting write for topic: {topic}")

        # Phase 1: 素材收集
        materials = await self._collect_materials(task_id, topic)
        self._record_trace(
            trace_events,
            stage="researcher_materials",
            agent="researcher",
            input_summary={"topic": topic},
            output={"materials": materials},
        )

        thesis = await self._build_thesis(task_id, topic, materials)
        self._record_trace(
            trace_events,
            stage="thesis_architect_brief",
            agent="thesis_architect",
            input_summary={
                "topic": topic,
                "materials_count": len(materials),
            },
            output=thesis,
        )

        # Phase 2-N: 讨论循环
        debate_graph = DebateGraph()
        content = ""
        current_scores = QualityScores()
        gate_result: Optional[GateResult] = None
        rewrite_feedback: Dict[str, Any] = {}
        completed_rounds = 0

        for round_num in range(1, max_rounds + 1):
            completed_rounds = round_num
            logger.info(f"Task {task_id}: Round {round_num}")

            # 2a: Writer生成或根据上一轮判浅反馈重写
            content = await self._write_content(
                task_id,
                topic,
                materials,
                thesis,
                round_num,
                content,
                rewrite_feedback,
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

            # 2b: Depth Judge初检。浅稿先退回Writer，不进入Devil Advocate。
            gate_result, judge_output = await self._judge_content(
                task_id,
                topic,
                content,
                criticisms=[],
                materials=materials,
            )
            current_scores = self._parse_scores(gate_result)
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
            criticisms = await self._criticize(
                task_id, topic, content, materials, round_num, debate_graph
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

            # 2d: Writer直接修订正文，而不是输出辩护说明
            source_content = content
            content = await self._revise_content(
                task_id,
                topic,
                materials,
                thesis,
                round_num,
                source_content,
                self._build_rewrite_feedback(
                    gate_result=gate_result,
                    judge_output=judge_output,
                    criticisms=[],
                    phase="judge_precheck",
                ),
                criticisms,
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

            # 2e: 修订稿再次判浅，通过后才进入Editor
            gate_result, judge_output = await self._judge_content(
                task_id,
                topic,
                content,
                criticisms=criticisms,
                materials=materials,
            )
            current_scores = self._parse_scores(gate_result)
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
            editor_raw, content = await self._edit_content(
                task_id, content, current_scores, thesis
            )
            self._record_trace(
                trace_events,
                stage="editor_raw",
                agent="editor",
                input_summary={"source_content_chars": len(editor_raw)},
                output={"raw_content": editor_raw, "clean_content": content},
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

    async def _collect_materials(
        self, task_id: str, topic: str
    ) -> List[Dict[str, Any]]:
        """素材收集"""
        result = await self.agents["researcher"].process({
            "task_id": task_id,
            "topic": topic,
            "material_types": ["data", "case", "theory", "quote", "history"],
            "depth_level": "deep",
        })
        return result.get("materials", [])

    async def _build_thesis(
        self,
        task_id: str,
        topic: str,
        materials: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Build the core thesis brief before drafting."""
        result = await self.agents["thesis_architect"].process({
            "task_id": task_id,
            "topic": topic,
            "materials": materials,
        })
        known_fields = {
            "core_claim",
            "conflict_with_common_view",
            "common_sense_overturned",
            "strongest_evidence",
            "most_dangerous_counterargument",
        }
        return {
            "core_claim": result.get("core_claim", ""),
            "conflict_with_common_view": result.get("conflict_with_common_view", ""),
            "common_sense_overturned": result.get("common_sense_overturned", ""),
            "strongest_evidence": result.get("strongest_evidence", ""),
            "most_dangerous_counterargument": result.get(
                "most_dangerous_counterargument", ""
            ),
            **{key: value for key, value in result.items() if key not in known_fields},
        }

    async def _write_content(
        self,
        task_id: str,
        topic: str,
        materials: List[Dict],
        thesis: Dict[str, Any],
        round_num: int,
        previous_content: str,
        rewrite_feedback: Optional[Dict[str, Any]] = None,
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
            "materials": materials,
            "thesis": thesis,
            "previous_rounds": previous_rounds,
            "rewrite_feedback": rewrite_feedback or {},
        })
        return result.get("content", "")

    async def _revise_content(
        self,
        task_id: str,
        topic: str,
        materials: List[Dict],
        thesis: Dict[str, Any],
        round_num: int,
        content: str,
        judge_feedback: Dict[str, Any],
        criticisms: List[Dict],
    ) -> str:
        """根据Judge和Devil Advocate反馈直接修订正文。"""
        result = await self.agents["writer"].process({
            "task_id": task_id,
            "round": round_num,
            "mode": "revision",
            "topic": topic,
            "materials": materials,
            "thesis": thesis,
            "content": content,
            "judge_feedback": judge_feedback,
            "criticisms": criticisms,
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
            "materials": materials,
            "previous_criticisms": previous_criticisms,
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
        defenses: str = "",
    ) -> tuple[GateResult, Dict[str, Any]]:
        """统一执行Depth Judge和Quality Gate。"""
        result = await self.agents["judge"].process({
            "task_id": task_id,
            "content": content,
            "topic": topic,
            "criticisms": criticisms,
            "defenses": defenses,
            "materials": materials,
        })

        scores = self._parse_scores_from_result(result)
        return self.gate.evaluate(scores.to_dict()), result

    async def _edit_content(
        self,
        task_id: str,
        content: str,
        scores: QualityScores,
        thesis: Optional[Dict[str, Any]] = None,
    ) -> tuple[str, str]:
        """编辑阶段"""
        result = await self.agents["editor"].process({
            "task_id": task_id,
            "content": content,
            "quality_scores": scores.to_dict(),
            "key_issues": scores.failed_dimensions(6.0),
            "criticisms": [],
            "thesis": thesis or {},
        })
        raw_content = result.get("content", content)
        return raw_content, clean_final_article(raw_content)

    def _record_trace(
        self,
        trace_events: List[TraceEvent],
        *,
        stage: str,
        agent: str,
        round_number: Optional[int] = None,
        input_summary: Optional[Dict[str, Any]] = None,
        output: Any = None,
    ) -> None:
        trace_events.append(
            TraceEvent(
                stage=stage,
                agent=agent,
                round_number=round_number,
                input_summary=input_summary or {},
                output=output or {},
            )
        )

    def _gate_result_to_dict(self, gate_result: GateResult) -> Dict[str, Any]:
        return {
            "passed": gate_result.passed,
            "reason": gate_result.reason,
            "quality_scores": gate_result.quality_scores.scores,
            "excellent_dimensions": gate_result.excellent_dimensions,
            "failed_dimensions": gate_result.failed_dimensions,
            "total_score": gate_result.total_score,
            "recommendations": gate_result.recommendations,
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
        """Map raw judge scores to the five depth-check dimensions."""
        return QualityScores(
            新判断=self._coerce_score(scores_dict.get("新判断", 0)),
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
