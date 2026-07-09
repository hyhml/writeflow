"""
状态机定义
"""
from __future__ import annotations

from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid


class TaskState(Enum):
    """任务状态"""

    PENDING = auto()  # 任务创建，等待调度
    RUNNING = auto()  # 正在执行（Agent处理中）
    REVIEWING = auto()  # 等待评审
    DISCUSSION = auto()  # 讨论中
    APPROVED = auto()  # 审核通过
    REJECTED = auto()  # 审核拒绝
    REVISION = auto()  # 需要修订
    FAILED = auto()  # 系统失败
    CANCELLED = auto()  # 主动取消

    def can_transition_to(self, target: "TaskState") -> bool:
        """检查是否可以转换到目标状态"""
        return target in VALID_TRANSITIONS.get(self, set())

    def is_terminal(self) -> bool:
        """是否为终态"""
        return self in {
            TaskState.APPROVED,
            TaskState.REJECTED,
            TaskState.FAILED,
            TaskState.CANCELLED,
        }


class RoundState(Enum):
    """讨论轮次状态"""

    INITIAL = auto()  # 初始状态
    WRITING = auto()  # Writer生成中
    CRITICIZING = auto()  # 质疑中
    DEFENDING = auto()  # 辩护中
    JUDGING = auto()  # 裁判评估中
    CONVERGED = auto()  # 收敛完成
    STALEMATE = auto()  # 僵局


# 状态转换规则
VALID_TRANSITIONS: Dict[TaskState, set[TaskState]] = {
    TaskState.PENDING: {TaskState.RUNNING, TaskState.CANCELLED},
    TaskState.RUNNING: {TaskState.REVIEWING, TaskState.DISCUSSION, TaskState.FAILED},
    TaskState.REVIEWING: {
        TaskState.DISCUSSION,
        TaskState.APPROVED,
        TaskState.REJECTED,
    },
    TaskState.DISCUSSION: {
        TaskState.DISCUSSION,
        TaskState.REVISION,
        TaskState.APPROVED,
        TaskState.REJECTED,
    },
    TaskState.REVISION: {TaskState.RUNNING, TaskState.DISCUSSION},
    TaskState.APPROVED: {TaskState.FAILED},
    TaskState.REJECTED: {TaskState.FAILED},
    TaskState.FAILED: set(),
    TaskState.CANCELLED: set(),
}


@dataclass
class TaskContext:
    """任务上下文"""

    task_id: uuid.UUID
    state: TaskState
    round: int
    round_state: RoundState
    content: Dict[str, Any]
    created_at: datetime
    updated_at: datetime
    retry_count: int = 0
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    version: int = 0  # 乐观锁版本

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": str(self.task_id),
            "state": self.state.name,
            "round": self.round,
            "round_state": self.round_state.name,
            "content": self.content,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "retry_count": self.retry_count,
            "error_message": self.error_message,
            "metadata": self.metadata,
            "version": self.version,
        }

    def transition_to(self, new_state: TaskState) -> bool:
        """尝试状态转换"""
        if self.state.can_transition_to(new_state):
            self.state = new_state
            self.updated_at = datetime.utcnow()
            self.version += 1
            return True
        return False


@dataclass
class Criticism:
    """质疑"""

    id: uuid.UUID
    round: int
    dimension: str
    question: str
    basis: str
    consequence: str
    validity: str = "pending"  # pending/valid/invalid/partial
    response: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": str(self.id),
            "round": self.round,
            "dimension": self.dimension,
            "question": self.question,
            "basis": self.basis,
            "consequence": self.consequence,
            "validity": self.validity,
            "response": self.response,
        }


@dataclass
class Defense:
    """辩护"""

    id: uuid.UUID
    criticism_id: uuid.UUID
    response: str
    acknowledged: bool = False
    improvement: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": str(self.id),
            "criticism_id": str(self.criticism_id),
            "response": self.response,
            "acknowledged": self.acknowledged,
            "improvement": self.improvement,
        }


@dataclass
class JudgeAssessment:
    """裁判评估"""

    id: uuid.UUID
    round: int
    criticism_assessments: List[Dict[str, Any]]
    defense_quality: str  # effective/partial/ineffective
    overall_status: str  # progressing/converged/stalemate
    quality_scores: Optional[Dict[str, float]] = None
    recommendations: List[str] = field(default_factory=list)
    is_converged: bool = False
    unresolved_issues: List[str] = field(default_factory=list)
    has_severe_issue: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": str(self.id),
            "round": self.round,
            "criticism_assessments": self.criticism_assessments,
            "defense_quality": self.defense_quality,
            "overall_status": self.overall_status,
            "quality_scores": self.quality_scores,
            "recommendations": self.recommendations,
            "is_converged": self.is_converged,
            "unresolved_issues": self.unresolved_issues,
            "has_severe_issue": self.has_severe_issue,
        }


@dataclass
class RoundContext:
    """讨论轮次上下文"""

    round_number: int
    task_id: uuid.UUID
    writer_input: str
    writer_output: str
    criticisms: List[Criticism] = field(default_factory=list)
    defenses: List[Defense] = field(default_factory=list)
    judge_assessment: Optional[JudgeAssessment] = None
    quality_scores: Optional[Dict[str, float]] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    duration_seconds: float = 0
    is_converged: bool = False
    unresolved_issues: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "round_number": self.round_number,
            "task_id": str(self.task_id),
            "writer_output": self.writer_output,
            "criticisms": [c.to_dict() for c in self.criticisms],
            "defenses": [d.to_dict() for d in self.defenses],
            "judge_assessment": (
                self.judge_assessment.to_dict() if self.judge_assessment else None
            ),
            "quality_scores": self.quality_scores,
            "timestamp": self.timestamp.isoformat(),
            "duration_seconds": self.duration_seconds,
            "is_converged": self.is_converged,
            "unresolved_issues": self.unresolved_issues,
        }
