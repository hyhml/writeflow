"""
WriteFlow - 批判性写作工作流
"""
from __future__ import annotations

import uuid
import logging
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

from writeflow.agents.researcher import ResearcherAgent
from writeflow.agents.writer import WriterAgent
from writeflow.agents.devil_advocate import DevilAdvocateAgent
from writeflow.agents.judge import JudgeAgent
from writeflow.agents.editor import EditorAgent
from writeflow.core.debate_graph import DebateGraph, DebateTurn, Criticism
from writeflow.core.quality_gate import QualityGate, GateResult
from writeflow.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class QualityScores:
    """7维质量评分"""
    批判锋芒: float = 0.0
    理论深度: float = 0.0
    洞察力度: float = 0.0
    论证严谨性: float = 0.0
    社会关联度: float = 0.0
    文字穿透力: float = 0.0
    学术规范性: float = 0.0

    def total(self) -> float:
        """总分"""
        return (
            self.批判锋芒
            + self.理论深度
            + self.洞察力度
            + self.论证严谨性
            + self.社会关联度
            + self.文字穿透力
            + self.学术规范性
        )

    def passed_dimensions(self, threshold: float = 8.0) -> List[str]:
        """获取达到阈值的维度"""
        return [k for k, v in self.__dict__.items() if v >= threshold]

    def failed_dimensions(self, threshold: float = 4.0) -> List[str]:
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
class WriteResult:
    """写作结果"""
    content: str
    scores: QualityScores
    passed: bool
    pass_reason: str
    debate_summary: DebateSummary
    rounds: int
    task_id: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "content": self.content,
            "scores": self.scores.to_dict(),
            "passed": self.passed,
            "pass_reason": self.pass_reason,
            "debate_summary": self.debate_summary.to_dict(),
            "rounds": self.rounds,
            "task_id": self.task_id,
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

        logger.info(f"Task {task_id}: Starting write for topic: {topic}")

        # Phase 1: 素材收集
        materials = await self._collect_materials(task_id, topic)

        # Phase 2-N: 讨论循环
        debate_graph = DebateGraph()
        content = ""
        current_scores = QualityScores()
        gate_result: Optional[GateResult] = None

        for round_num in range(1, max_rounds + 1):
            logger.info(f"Task {task_id}: Round {round_num}")

            # 2a: Writer生成
            content = await self._write_content(
                task_id, topic, materials, round_num, content
            )

            # 2b: Devil's Advocate质疑
            criticisms = await self._criticize(
                task_id, topic, content, materials, round_num, debate_graph
            )

            # 2c: Writer辩护
            defenses = await self._defend(
                task_id, content, criticisms, round_num
            )

            # 2d: Judge评估
            gate_result = await self._judge(
                task_id, topic, content, criticisms, defenses, materials
            )
            current_scores = self._parse_scores(gate_result)

            # 检查是否通过
            if gate_result.passed:
                logger.info(f"Task {task_id}: Passed at round {round_num}")
                break

            # 检查收敛
            is_converged, _ = debate_graph.check_convergence()
            if is_converged and round_num >= self.min_rounds:
                logger.info(f"Task {task_id}: Converged at round {round_num}")
                break

        # Phase N+1: Editor打磨
        if gate_result and gate_result.passed:
            content = await self._edit_content(
                task_id, content, current_scores
            )

        # 构建结果
        debate_summary = DebateSummary(
            total_criticisms=debate_graph.total_criticisms,
            resolved_criticisms=debate_graph.resolved_count,
            active_criticisms=debate_graph.active_count,
            key_issues=gate_result.recommendations if gate_result else [],
            rounds=min(max_rounds, len(debate_graph.turns) + 1) if debate_graph.turns else 1,
        )

        return WriteResult(
            content=content,
            scores=current_scores,
            passed=gate_result.passed if gate_result else False,
            pass_reason=gate_result.reason if gate_result else "unknown",
            debate_summary=debate_summary,
            rounds=len(debate_graph.turns) if debate_graph.turns else 0,
            task_id=task_id,
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

    async def _write_content(
        self,
        task_id: str,
        topic: str,
        materials: List[Dict],
        round_num: int,
        previous_content: str,
    ) -> str:
        """写作阶段"""
        result = await self.agents["writer"].process({
            "task_id": task_id,
            "round": round_num,
            "mode": "write",
            "topic": topic,
            "materials": materials,
            "previous_rounds": [],
        })
        return result.get("content", "")

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
    ) -> GateResult:
        """评估阶段"""
        result = await self.agents["judge"].process({
            "task_id": task_id,
            "content": content,
            "topic": topic,
            "criticisms": criticisms,
            "defenses": defenses,
            "materials": materials,
        })

        scores = self._parse_scores_from_result(result)
        return self.gate.evaluate(scores.to_dict())

    async def _edit_content(
        self,
        task_id: str,
        content: str,
        scores: QualityScores,
    ) -> str:
        """编辑阶段"""
        result = await self.agents["editor"].process({
            "task_id": task_id,
            "content": content,
            "quality_scores": scores.to_dict(),
            "key_issues": scores.failed_dimensions(6.0),
            "criticisms": [],
        })
        return result.get("content", content)

    def _parse_scores(self, gate_result: GateResult) -> QualityScores:
        """从GateResult解析评分"""
        if not gate_result:
            return QualityScores()

        qs = gate_result.quality_scores
        if isinstance(qs, dict):
            return QualityScores(
                批判锋芒=qs.get("批判锋芒", 0),
                理论深度=qs.get("理论深度", 0),
                洞察力度=qs.get("洞察力度", 0),
                论证严谨性=qs.get("论证严谨性", 0),
                社会关联度=qs.get("社会关联度", 0),
                文字穿透力=qs.get("文字穿透力", 0),
                学术规范性=qs.get("学术规范性", 0),
            )

        if hasattr(qs, "scores"):
            scores_dict = qs.scores
            return QualityScores(
                批判锋芒=scores_dict.get("批判锋芒", 0),
                理论深度=scores_dict.get("理论深度", 0),
                洞察力度=scores_dict.get("洞察力度", 0),
                论证严谨性=scores_dict.get("论证严谨性", 0),
                社会关联度=scores_dict.get("社会关联度", 0),
                文字穿透力=scores_dict.get("文字穿透力", 0),
                学术规范性=scores_dict.get("学术规范性", 0),
            )

        return QualityScores()

    def _parse_scores_from_result(self, result: Dict) -> QualityScores:
        """从Agent结果解析评分"""
        scores_dict = result.get("quality_scores", {})
        if not scores_dict:
            return QualityScores()

        return QualityScores(
            批判锋芒=scores_dict.get("批判锋芒", 0),
            理论深度=scores_dict.get("理论深度", 0),
            洞察力度=scores_dict.get("洞察力度", 0),
            论证严谨性=scores_dict.get("论证严谨性", 0),
            社会关联度=scores_dict.get("社会关联度", 0),
            文字穿透力=scores_dict.get("文字穿透力", 0),
            学术规范性=scores_dict.get("学术规范性", 0),
        )
