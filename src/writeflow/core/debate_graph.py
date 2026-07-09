"""
辩论图谱 - 追踪质疑的生命周期
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, List
from datetime import datetime, timezone


@dataclass
class Criticism:
    """质疑条目"""
    criticism_id: str
    dimension: str  # 质疑维度
    question: str  # 质疑问题
    analysis: str  # 具体分析
    consequence: str  # 后果推演
    threat_level: str  # 致命/严重/中等/轻微

    # 生命周期追踪
    created_round: int
    current_round: int
    validity: str = "pending"  # pending/valid/invalid/partial
    defense_response: str = ""
    is_resolved: bool = False
    resolution_type: str = ""  # conceded/rebutted/persisted

    # 依赖关系
    follow_up_from: Optional[str] = None  # 来自哪个质疑的追问
    linked_arguments: List[str] = field(default_factory=list)


@dataclass
class DebateTurn:
    """辩论回合"""
    turn_id: str
    round_number: int
    agent_id: str  # 提出质疑的Agent
    criticisms: List[Criticism] = field(default_factory=list)
    defenses: List[str] = field(default_factory=list)  # 辩护回应
    judge_assessment: Optional[dict] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class DebateGraph:
    """
    辩论图谱 - 管理所有质疑的生命周期

    核心功能：
    1. 追踪每条质疑从提出到解决的完整生命周期
    2. 避免重复质疑
    3. 判断讨论是否收敛
    4. 识别"表面共识"vs"真正解决"
    """

    def __init__(self):
        self.turns: List[DebateTurn] = []
        self._criticisms: dict[str, Criticism] = {}
        self._active_criticisms: dict[str, Criticism] = {}
        self._resolved_criticisms: dict[str, Criticism] = {}

    @property
    def total_criticisms(self) -> int:
        return len(self._criticisms)

    @property
    def active_count(self) -> int:
        return len(self._active_criticisms)

    @property
    def resolved_count(self) -> int:
        return len(self._resolved_criticisms)

    def add_turn(self, turn: DebateTurn) -> None:
        """添加一轮辩论"""
        self.turns.append(turn)

        # 注册新的质疑
        for c in turn.criticisms:
            if c.criticism_id not in self._criticisms:
                self._criticisms[c.criticism_id] = c
                self._active_criticisms[c.criticism_id] = c

        # 更新当前轮次
        for c_id in self._active_criticisms:
            self._criticisms[c_id].current_round = turn.round_number

    def add_defense(
        self,
        criticism_id: str,
        defense: str,
        validity: str,
        resolution_type: str
    ) -> bool:
        """
        添加辩护并解决质疑

        Returns:
            是否成功解决
        """
        if criticism_id not in self._active_criticisms:
            return False

        c = self._active_criticisms[criticism_id]
        c.defense_response = defense
        c.validity = validity
        c.resolution_type = resolution_type
        c.is_resolved = True

        # 移动到已解决
        del self._active_criticisms[criticism_id]
        self._resolved_criticisms[criticism_id] = c

        return True

    def get_unresolved_criticisms(self) -> List[Criticism]:
        """获取未解决的质疑"""
        return list(self._active_criticisms.values())

    def get_criticisms_by_dimension(self, dimension: str) -> List[Criticism]:
        """按维度获取质疑"""
        return [c for c in self._criticisms.values() if c.dimension == dimension]

    def get_round_criticisms(self, round_num: int) -> List[Criticism]:
        """获取指定轮次的质疑"""
        return [c for c in self._criticisms.values() if c.created_round == round_num]

    def get_round_active_criticisms(self, round_num: int) -> List[Criticism]:
        """获取指定轮次的活跃质疑"""
        return [c for c in self._active_criticisms.values() if c.created_round == round_num]

    def is_duplicate(self, question: str, threshold: float = 0.8) -> bool:
        """
        检查是否是重复质疑

        Args:
            question: 新的质疑问题
            threshold: 相似度阈值

        Returns:
            是否重复
        """
        # 简化的相似度检查（实际应用中可用更复杂的NLP方法）
        q_words = set(question.lower().split())

        for c in self._criticisms.values():
            c_words = set(c.question.lower().split())
            intersection = q_words & c_words
            union = q_words | c_words
            if union and len(intersection) / len(union) > threshold:
                return True

        return False

    def check_convergence(self) -> tuple[bool, str]:
        """
        检查是否收敛

        Returns:
            (is_converged, reason)
        """
        if not self.turns:
            return False, "no_discussion_yet"

        last_turn = self.turns[-1]

        # 情况1：所有质疑都已解决
        if self.active_count == 0:
            return True, "all_criticisms_resolved"

        # 情况2：连续2轮无新的有效质疑
        if len(self.turns) >= 2:
            current_round = last_turn.round_number
            if current_round >= 2:
                round_1_active = self.get_round_active_criticisms(current_round - 1)
                round_2_active = self.get_round_active_criticisms(current_round)

                if len(round_1_active) == 0 and len(round_2_active) == 0:
                    return True, "no_new_criticisms_for_2_rounds"

        # 情况3：所有活跃质疑都是"轻微"级别
        if all(c.threat_level in ["中等", "轻微"] for c in self._active_criticisms.values()):
            return True, "only_minor_criticisms_remain"

        return False, "active_criticisms_remain"

    def get_summary(self) -> dict:
        """获取辩论总结"""
        return {
            "total_rounds": len(self.turns),
            "total_criticisms": self.total_criticisms,
            "active_criticisms": self.active_count,
            "resolved_criticisms": self.resolved_count,
            "by_dimension": {
                dim: len(self.get_criticisms_by_dimension(dim))
                for dim in set(c.dimension for c in self._criticisms.values())
            },
            "by_threat_level": {
                level: len([c for c in self._criticisms.values() if c.threat_level == level])
                for level in ["致命", "严重", "中等", "轻微"]
            },
        }

    def get_unresolved_for_next_round(self) -> List[Criticism]:
        """获取需要下一轮继续解决的质疑"""
        return [
            c for c in self._active_criticisms.values()
            if c.resolution_type != "conceded"  # 不包括已承认的质疑
        ]


class ConvergenceChecker:
    """收敛检查器"""

    @staticmethod
    def check_quality_convergence(score_history: List[dict]) -> bool:
        """
        检查质量评分是否收敛

        Args:
            score_history: 每轮的质量评分 [{"维度": 分数}, ...]

        Returns:
            是否收敛
        """
        if len(score_history) < 2:
            return False

        # 计算最近两轮的差异
        recent = score_history[-2:]
        scores1 = recent[0]
        scores2 = recent[1]

        keys = set(scores1.keys()) & set(scores2.keys())
        if not keys:
            return False

        # 计算平均差异
        diffs = [abs(scores1[k] - scores2[k]) for k in keys]
        avg_diff = sum(diffs) / len(diffs)

        # 5%差异阈值
        return avg_diff < 0.5

    @staticmethod
    def check_discussion_convergence(debate_graph: DebateGraph) -> tuple[bool, str, dict]:
        """
        检查讨论是否收敛

        Returns:
            (is_converged, reason, details)
        """
        details = debate_graph.get_summary()

        # 检查质疑收敛
        is_converged, reason = debate_graph.check_convergence()
        if is_converged:
            return True, reason, details

        # 检查质量收敛
        # (需要在外部传入score_history)
        # is_quality_converged = ConvergenceChecker.check_quality_convergence(score_history)

        return False, "not_converged", details
