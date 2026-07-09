"""
轮次控制器
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict
import uuid

from writeflow.core.state_machine import (
    RoundContext,
    RoundState,
    Criticism,
    Defense,
    JudgeAssessment,
)
from writeflow.config import get_settings


@dataclass
class RoundConfig:
    """轮次配置"""

    min_rounds: int = 2
    max_rounds: int = 5
    round_timeout_seconds: int = 300
    convergence_threshold: float = 0.5
    consecutive_rounds_for_convergence: int = 2


class RoundController:
    """
    讨论轮次控制器
    管理多轮讨论的生命周期，判断讨论是否应该终止
    """

    def __init__(self, config: Optional[RoundConfig] = None):
        self.config = config or RoundConfig()
        self.rounds: List[RoundContext] = []
        self._current_round: Optional[RoundContext] = None

    @property
    def current_round_number(self) -> int:
        return len(self.rounds) + 1

    @property
    def is_discussion_complete(self) -> bool:
        """讨论是否完成"""
        if len(self.rounds) >= self.config.max_rounds:
            return True

        if self._check_early_convergence():
            return True

        return False

    def _check_early_convergence(self) -> bool:
        """检查是否提前收敛"""
        if len(self.rounds) < self.config.min_rounds:
            return False

        recent = self.rounds[-self.config.consecutive_rounds_for_convergence :]
        if len(recent) < self.config.consecutive_rounds_for_convergence:
            return False

        return all(r.is_converged for r in recent)

    async def start_round(
        self, task_id: uuid.UUID, writer_input: str
    ) -> RoundContext:
        """开始新的一轮讨论"""
        round_ctx = RoundContext(
            round_number=self.current_round_number,
            task_id=task_id,
            writer_input=writer_input,
            writer_output="",
            timestamp=datetime.utcnow(),
        )
        self._current_round = round_ctx
        return round_ctx

    async def complete_round(
        self,
        writer_output: str,
        criticisms: List[Criticism],
        defenses: List[Defense],
        judge_assessment: Optional[JudgeAssessment],
        quality_scores: Optional[Dict[str, float]],
        is_converged: bool,
        unresolved_issues: List[str],
    ) -> RoundContext:
        """完成当前轮次"""
        if self._current_round is None:
            raise ValueError("No active round to complete")

        self._current_round.writer_output = writer_output
        self._current_round.criticisms = criticisms
        self._current_round.defenses = defenses
        self._current_round.judge_assessment = judge_assessment
        self._current_round.quality_scores = quality_scores
        self._current_round.is_converged = is_converged
        self._current_round.unresolved_issues = unresolved_issues
        self._current_round.duration_seconds = (
            datetime.utcnow() - self._current_round.timestamp
        ).total_seconds()

        self.rounds.append(self._current_round)
        self._current_round = None

        return self.rounds[-1]

    async def should_terminate(
        self, quality_scores: Optional[Dict[str, float]] = None
    ) -> tuple[bool, str]:
        """
        判断是否应该终止讨论

        Returns:
            (should_terminate, reason)
        """
        if len(self.rounds) >= self.config.max_rounds:
            return True, "max_rounds_exceeded"

        if len(self.rounds) < self.config.min_rounds:
            return False, ""

        if self._check_early_convergence():
            return True, "early_convergence"

        if quality_scores and self._check_quality_passed(quality_scores):
            return True, "quality_passed"

        if self._check_stalemate():
            return True, "stalemate"

        return False, ""

    def _check_quality_passed(self, scores: Dict[str, float]) -> bool:
        """检查质量是否已通过"""
        if not scores:
            return False

        settings = get_settings()
        excellent_count = sum(
            1 for s in scores.values() if s >= settings.quality_threshold_excellent
        )
        if excellent_count >= 2:
            return True

        total = sum(scores.values())
        if total >= settings.quality_total_threshold:
            return True

        if all(s >= settings.quality_developed_protection for s in scores.values()):
            return True

        return False

    def _check_stalemate(self) -> bool:
        """检查是否陷入僵局"""
        if len(self.rounds) < 2:
            return False

        recent = self.rounds[-2:]
        for r in recent:
            if len(r.unresolved_issues) > 0:
                return False
            if r.quality_scores is None:
                return False

        return True

    def get_summary(self) -> Dict:
        """获取讨论总结"""
        return {
            "total_rounds": len(self.rounds),
            "current_round": self.current_round_number,
            "is_complete": self.is_discussion_complete,
            "rounds_summary": [
                {
                    "round": r.round_number,
                    "is_converged": r.is_converged,
                    "unresolved_count": len(r.unresolved_issues),
                    "quality_scores": r.quality_scores,
                }
                for r in self.rounds
            ],
        }


class TerminationChecker:
    """
    终止条件检查器
    用于Quality Gate判断是否应该终止讨论
    """

    def __init__(self, config: Optional[RoundConfig] = None):
        self.config = config or RoundConfig()
        self.settings = get_settings()

    def check_termination(
        self,
        round_controller: RoundController,
        quality_scores: Optional[Dict[str, float]] = None,
        has_severe_issue: bool = False,
    ) -> tuple[bool, str, Dict]:
        """
        检查是否应该终止

        Returns:
            (should_terminate, reason, details)
        """
        if has_severe_issue:
            return True, "severe_issue", {"action": "强制复审或拒绝"}

        should_terminate, reason = round_controller.should_terminate(quality_scores)

        if should_terminate:
            details = {
                "reason": reason,
                "rounds_completed": len(round_controller.rounds),
            }
            return True, reason, details

        return False, "", {}

    def check_approval(self, quality_scores: Dict[str, float]) -> tuple[bool, str]:
        """
        检查是否应该批准通过

        Returns:
            (should_approve, reason)
        """
        if not quality_scores:
            return False, "no_scores"

        # 基础门槛
        if any(s < self.settings.quality_threshold_pass for s in quality_scores.values()):
            return False, "below_minimum"

        # 优秀门槛
        excellent_count = sum(
            1
            for s in quality_scores.values()
            if s >= self.settings.quality_threshold_excellent
        )
        if excellent_count >= 2:
            return True, "excellent_dimensions"

        # 总分门槛
        total = sum(quality_scores.values())
        if total >= self.settings.quality_total_threshold:
            return True, "total_score"

        # 全面发展保护
        if all(
            s >= self.settings.quality_developed_protection
            for s in quality_scores.values()
        ):
            return True, "all_developed"

        return False, "not_meets_threshold"
