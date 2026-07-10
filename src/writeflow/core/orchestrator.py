"""
核心调度器 - 多Agent协作编排
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List

from writeflow.agents.researcher import ResearcherAgent
from writeflow.agents.thesis_architect import ThesisArchitectAgent
from writeflow.agents.writer import WriterAgent
from writeflow.agents.devil_advocate import DevilAdvocateAgent
from writeflow.agents.judge import JudgeAgent
from writeflow.agents.editor import EditorAgent
from writeflow.core.debate_graph import DebateGraph, DebateTurn, Criticism
from writeflow.core.quality_gate import QualityGate, GateResult
from writeflow.config import get_settings

logger = logging.getLogger(__name__)


class TaskContext:
    """任务上下文"""

    def __init__(self, task_id: str, topic: str, priority: int = 50):
        self.task_id = task_id
        self.topic = topic
        self.priority = priority
        self.status = "pending"  # pending/running/completed/failed
        self.current_round = 0
        self.max_rounds = 5
        self.created_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

        # 素材
        self.materials: List[dict] = []
        self.thesis: Dict[str, Any] = {}

        # 讨论
        self.debate_graph = DebateGraph()
        self.discussion_history: List[Dict[str, Any]] = []

        # 质量
        self.quality_scores: Dict[str, float] = {}
        self.gate_result: Optional[GateResult] = None

        # 最终结果
        self.final_content: str = ""
        self.iteration_count = 0

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "topic": self.topic,
            "priority": self.priority,
            "status": self.status,
            "current_round": self.current_round,
            "materials_count": len(self.materials),
            "thesis_core_claim": self.thesis.get("core_claim", ""),
            "criticisms_total": self.debate_graph.total_criticisms,
            "criticisms_active": self.debate_graph.active_count,
            "quality_scores": self.quality_scores,
            "gate_passed": self.gate_result.passed if self.gate_result else None,
            "final_content_length": len(self.final_content),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class Orchestrator:
    """
    核心调度器

    流程：
    1. Researcher收集素材
    2. Thesis Architect产出核心判断
    3. Writer写初稿
    4. Depth Judge初检，浅稿直接退回Writer重写
    5. 初检通过后进入Devil's Advocate质疑
    6. Writer直接修订正文，再由Depth Judge终检
    7. 终检通过 → Editor最终打磨
    """

    def __init__(
        self,
        max_rounds: Optional[int] = None,
        min_rounds: Optional[int] = None,
    ):
        settings = get_settings()
        # Agent实例
        self.agents = {
            "researcher": ResearcherAgent(),
            "thesis_architect": ThesisArchitectAgent(),
            "writer": WriterAgent(),
            "devil_advocate": DevilAdvocateAgent(),
            "judge": JudgeAgent(),
            "editor": EditorAgent(),
        }

        # 质量Gate
        self.gate = QualityGate()

        # 配置
        self.max_rounds = max_rounds or settings.max_rounds
        self.min_rounds = min_rounds or settings.min_rounds

        # 任务存储
        self.tasks: Dict[str, TaskContext] = {}

    async def submit_task(self, topic: str, priority: int = 50) -> str:
        """提交任务"""
        task_id = str(uuid.uuid4())
        task = TaskContext(task_id=task_id, topic=topic, priority=priority)
        self.tasks[task_id] = task
        logger.info(f"Task submitted: {task_id}")
        return task_id

    async def process_task(self, task_id: str) -> dict:
        """
        处理单个任务

        Returns:
            处理结果
        """
        if task_id not in self.tasks:
            raise ValueError(f"Task {task_id} not found")

        task = self.tasks[task_id]
        task.status = "running"

        try:
            # Phase 1: 素材收集
            logger.info(f"Task {task_id}: Phase 1 - Research")
            await self._phase_research(task)
            logger.info(f"Task {task_id}: Phase 1b - Thesis Architect")
            await self._phase_thesis(task)

            # Phase 2-4: 讨论循环
            rewrite_feedback: Dict[str, Any] = {}
            for round_num in range(1, self.max_rounds + 1):
                task.current_round = round_num
                logger.info(f"Task {task_id}: Round {round_num}")

                # 2a: Writer生成或根据上一轮Judge反馈重写
                logger.info(f"Task {task_id}: Round {round_num} - Writing")
                content = await self._phase_write(task, rewrite_feedback)

                # 2b: Depth Judge初检
                logger.info(f"Task {task_id}: Round {round_num} - Judge precheck")
                gate_result = await self._phase_judge(
                    task,
                    content,
                    criticisms=[],
                    phase="judge_precheck",
                )
                task.gate_result = gate_result

                if not gate_result.passed:
                    rewrite_feedback = self._build_rewrite_feedback(
                        task=task,
                        gate_result=gate_result,
                        criticisms=[],
                        phase="judge_precheck",
                    )
                    if round_num < self.max_rounds:
                        task.iteration_count += 1
                        continue
                    break

                # 2c: Devil's Advocate质疑
                logger.info(f"Task {task_id}: Round {round_num} - Criticism")
                criticisms = await self._phase_criticism(task, content)

                # 2d: Writer直接修订正文
                logger.info(f"Task {task_id}: Round {round_num} - Revision")
                content = await self._phase_revision(
                    task,
                    content,
                    criticisms,
                    self._build_rewrite_feedback(
                        task=task,
                        gate_result=gate_result,
                        criticisms=[],
                        phase="judge_precheck",
                    ),
                )

                # 2e: 修订稿终检
                logger.info(f"Task {task_id}: Round {round_num} - Judge final")
                gate_result = await self._phase_judge(
                    task,
                    content,
                    criticisms=criticisms,
                    phase="judge_final",
                )
                task.gate_result = gate_result

                # 检查是否通过
                if gate_result.passed:
                    logger.info(f"Task {task_id}: Passed at round {round_num}")
                    break

                rewrite_feedback = self._build_rewrite_feedback(
                    task=task,
                    gate_result=gate_result,
                    criticisms=criticisms,
                    phase="judge_final",
                )
                if round_num < self.max_rounds:
                    task.iteration_count += 1

            # Phase 5: Editor最终打磨
            if task.gate_result and task.gate_result.passed:
                logger.info(f"Task {task_id}: Phase 5 - Editor")
                task.final_content = await self._phase_edit(task)
            else:
                task.final_content = self._latest_article_content(task)

            task.status = "completed"
            task.updated_at = datetime.utcnow()

            return self._build_result(task)

        except Exception as e:
            logger.error(f"Task {task_id} failed: {e}")
            task.status = "failed"
            task.updated_at = datetime.utcnow()
            raise

    async def _phase_research(self, task: TaskContext) -> List[dict]:
        """素材收集阶段"""
        result = await self.agents["researcher"].process({
            "task_id": task.task_id,
            "topic": task.topic,
            "material_types": ["data", "case", "theory", "quote", "history"],
            "depth_level": "deep",
        })

        task.materials = result.get("materials", [])
        return task.materials

    async def _phase_thesis(self, task: TaskContext) -> Dict[str, Any]:
        """Build the core thesis brief before drafting."""
        result = await self.agents["thesis_architect"].process({
            "task_id": task.task_id,
            "topic": task.topic,
            "materials": task.materials,
        })
        task.thesis = result
        task.discussion_history.append({
            "round": 0,
            "phase": "thesis_architect",
            "thesis": result,
            "timestamp": datetime.utcnow().isoformat(),
        })
        return task.thesis

    async def _phase_write(
        self, task: TaskContext, rewrite_feedback: Optional[Dict[str, Any]] = None
    ) -> str:
        """写作阶段"""
        previous_rounds = []
        if task.discussion_history:
            # 只传最近2轮
            previous_rounds = task.discussion_history[-2:]

        result = await self.agents["writer"].process({
            "task_id": task.task_id,
            "round": task.current_round,
            "mode": "write",
            "topic": task.topic,
            "materials": task.materials,
            "thesis": task.thesis,
            "previous_rounds": previous_rounds,
            "rewrite_feedback": rewrite_feedback or {},
        })

        content = result["content"]

        # 记录
        task.discussion_history.append({
            "round": task.current_round,
            "phase": "write",
            "content": content,
            "timestamp": datetime.utcnow().isoformat(),
        })

        return content

    async def _phase_criticism(self, task: TaskContext, content: str) -> List[dict]:
        """质疑阶段"""
        previous_criticisms = []
        for h in task.discussion_history:
            if h.get("phase") == "criticism":
                previous_criticisms.extend(h.get("criticisms", []))

        result = await self.agents["devil_advocate"].process({
            "task_id": task.task_id,
            "round": task.current_round,
            "content": content,
            "topic": task.topic,
            "materials": task.materials,
            "previous_criticisms": previous_criticisms,
        })

        criticisms = result.get("criticisms", [])

        # 更新辩论图谱
        debate_turn = DebateTurn(
            turn_id=str(uuid.uuid4()),
            round_number=task.current_round,
            agent_id="devil_advocate",
            criticisms=[
                Criticism(
                    criticism_id=f"C{len(task.debate_graph.turns) * 10 + i + 1}",
                    dimension=c.get("dimension", "unknown"),
                    question=c.get("question", ""),
                    analysis=c.get("analysis", ""),
                    consequence=c.get("consequence", ""),
                    threat_level=c.get("threat_level", "中等"),
                    created_round=task.current_round,
                    current_round=task.current_round,
                )
                for i, c in enumerate(criticisms)
            ],
        )
        task.debate_graph.add_turn(debate_turn)

        # 记录
        task.discussion_history.append({
            "round": task.current_round,
            "phase": "criticism",
            "criticisms": criticisms,
            "timestamp": datetime.utcnow().isoformat(),
        })

        return criticisms

    async def _phase_revision(
        self,
        task: TaskContext,
        content: str,
        criticisms: List[dict],
        judge_feedback: Dict[str, Any],
    ) -> str:
        """修订阶段：直接输出新的正文，不输出辩护说明。"""
        result = await self.agents["writer"].process({
            "task_id": task.task_id,
            "round": task.current_round,
            "mode": "revision",
            "topic": task.topic,
            "materials": task.materials,
            "thesis": task.thesis,
            "content": content,
            "criticisms": criticisms,
            "judge_feedback": judge_feedback,
        })

        revised_content = result["content"]
        task.discussion_history.append({
            "round": task.current_round,
            "phase": "revision",
            "content": revised_content,
            "timestamp": datetime.utcnow().isoformat(),
        })
        return revised_content

    async def _phase_defense(
        self,
        task: TaskContext,
        content: str,
        criticisms: List[dict]
    ) -> str:
        """辩护阶段"""
        if not criticisms:
            return ""

        result = await self.agents["writer"].process({
            "task_id": task.task_id,
            "round": task.current_round,
            "mode": "defense",
            "content": content,
            "criticisms": criticisms,
        })

        defenses = result["content"]

        # 记录
        task.discussion_history.append({
            "round": task.current_round,
            "phase": "defense",
            "defenses": defenses,
            "timestamp": datetime.utcnow().isoformat(),
        })

        return defenses

    async def _phase_judge(
        self,
        task: TaskContext,
        content: str,
        criticisms: List[dict],
        phase: str,
        defenses: str = "",
    ) -> GateResult:
        """评估阶段"""
        result = await self.agents["judge"].process({
            "task_id": task.task_id,
            "content": content,
            "topic": task.topic,
            "criticisms": criticisms,
            "defenses": defenses,
            "materials": task.materials,
        })

        scores = result.get("quality_scores", {})
        task.quality_scores = scores

        gate_result = self.gate.evaluate_with_context(
            scores,
            context={
                "topic": task.topic,
                "materials_used": bool(task.materials),
                "criticism_count": len(criticisms),
                "discussion_rounds": task.current_round,
            }
        )

        # 更新辩论图谱中的质疑状态
        for c in task.debate_graph.get_unresolved_criticisms():
            # 简化处理：所有未解决质疑标记为部分有效
            task.debate_graph.add_defense(
                c.criticism_id,
                defense="待进一步讨论",
                validity="partial",
                resolution_type="persisted",
            )

        # 记录
        task.discussion_history.append({
            "round": task.current_round,
            "phase": phase,
            "quality_scores": scores,
            "gate_result": {
                "passed": gate_result.passed,
                "reason": gate_result.reason,
            },
            "failed_dimensions": gate_result.failed_dimensions,
            "recommendations": gate_result.recommendations,
            "timestamp": datetime.utcnow().isoformat(),
        })

        return gate_result

    async def _phase_edit(self, task: TaskContext) -> str:
        """编辑阶段"""
        last_content = self._latest_article_content(task)

        result = await self.agents["editor"].process({
            "task_id": task.task_id,
            "content": last_content,
            "quality_scores": task.quality_scores,
            "key_issues": [
                r for r in task.gate_result.recommendations if "缺陷" in r or "不足" in r
            ] if task.gate_result else [],
            "criticisms": [
                c.to_dict() for c in task.debate_graph.get_unresolved_criticisms()
            ],
            "thesis": task.thesis,
        })

        return result["content"]

    def _latest_article_content(self, task: TaskContext) -> str:
        """Return the latest Writer-produced article body."""
        for history in reversed(task.discussion_history):
            if history.get("phase") in {"revision", "write"}:
                return history.get("content", "")
        return ""

    def _build_rewrite_feedback(
        self,
        *,
        task: TaskContext,
        gate_result: GateResult,
        criticisms: List[dict],
        phase: str,
    ) -> Dict[str, Any]:
        """Build compact Judge feedback for Writer rewrite/revision."""
        latest_judge = next(
            (
                history
                for history in reversed(task.discussion_history)
                if history.get("phase") == phase
            ),
            {},
        )
        return {
            "phase": phase,
            "passed": gate_result.passed,
            "pass_reason": gate_result.reason,
            "quality_scores": task.quality_scores,
            "failed_dimensions": gate_result.failed_dimensions,
            "key_issues": latest_judge.get("key_issues", []),
            "recommendations": gate_result.recommendations
            or latest_judge.get("recommendations", []),
            "criticisms": criticisms,
        }

    def _build_result(self, task: TaskContext) -> dict:
        """构建结果"""
        return {
            "task_id": task.task_id,
            "topic": task.topic,
            "status": task.status,
            "rounds_completed": task.current_round,
            "thesis": task.thesis,
            "quality_scores": task.quality_scores,
            "gate_result": {
                "passed": task.gate_result.passed if task.gate_result else False,
                "reason": task.gate_result.reason if task.gate_result else "",
                "excellent_dimensions": (
                    task.gate_result.excellent_dimensions if task.gate_result else []
                ),
                "failed_dimensions": (
                    task.gate_result.failed_dimensions if task.gate_result else []
                ),
            },
            "debate_summary": task.debate_graph.get_summary(),
            "final_content": task.final_content,
        }

    async def process_batch(self, topics: List[str], priority: int = 50) -> List[dict]:
        """批量处理"""
        results = []
        for topic in topics:
            task_id = await self.submit_task(topic, priority)
            try:
                result = await self.process_task(task_id)
                results.append(result)
            except Exception as e:
                results.append({
                    "task_id": task_id,
                    "topic": topic,
                    "status": "failed",
                    "error": str(e),
                })
        return results
