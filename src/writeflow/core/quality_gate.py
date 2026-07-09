"""Quality gate based on five shallow-depth checks."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


QUALITY_DIMENSIONS = {
    "新判断": {"weight": 0.20, "min_score": 6.0},
    "概念克制": {"weight": 0.20, "min_score": 6.0},
    "句子必要性": {"weight": 0.20, "min_score": 6.0},
    "层次穿透": {"weight": 0.20, "min_score": 6.0},
    "方案具体性": {"weight": 0.20, "min_score": 6.0},
}


@dataclass
class QualityScores:
    """Depth-oriented quality scores."""

    scores: Dict[str, float]

    @property
    def total(self) -> float:
        return sum(self.scores.values())

    @property
    def average(self) -> float:
        return self.total / len(self.scores) if self.scores else 0

    def failed_dimensions(self, threshold: float = 6.0) -> List[str]:
        return [key for key, value in self.scores.items() if value < threshold]

    def excellent_dimensions(self, threshold: float = 8.0) -> List[str]:
        # Kept for output compatibility; no longer used as a pass condition.
        return [key for key, value in self.scores.items() if value >= threshold]

    def is_all_developed(self, threshold: float = 6.0) -> bool:
        # Kept for compatibility with older callers.
        return all(value >= threshold for value in self.scores.values())


@dataclass
class GateResult:
    """Gate decision result."""

    passed: bool
    reason: str
    quality_scores: QualityScores
    excellent_dimensions: List[str] = field(default_factory=list)
    failed_dimensions: List[str] = field(default_factory=list)
    total_score: float = 0
    recommendations: List[str] = field(default_factory=list)


class QualityGate:
    """Reject shallow drafts unless all five depth dimensions pass."""

    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}
        self.dimensions = {
            dimension: dict(settings)
            for dimension, settings in QUALITY_DIMENSIONS.items()
        }
        for dimension, dimension_config in self.config.get("dimensions", {}).items():
            if dimension in self.dimensions:
                self.dimensions[dimension].update(dimension_config)

    def evaluate(self, scores: Dict[str, float]) -> GateResult:
        normalized_scores = self._normalize_scores(scores)
        quality_scores = QualityScores(scores=normalized_scores)
        total_score = quality_scores.total
        failed_dims = [
            dimension
            for dimension, score in normalized_scores.items()
            if score < self.dimensions[dimension]["min_score"]
        ]

        if failed_dims:
            return GateResult(
                passed=False,
                reason="shallow_dimensions",
                quality_scores=quality_scores,
                failed_dimensions=failed_dims,
                total_score=total_score,
                recommendations=[
                    "以下判浅维度未达到 6 分："
                    + ", ".join(failed_dims),
                    "需要重写对应段落，而不是补术语或扩写套话。",
                ],
            )

        return GateResult(
            passed=True,
            reason="depth_passed",
            quality_scores=quality_scores,
            failed_dimensions=[],
            total_score=total_score,
            recommendations=["五项判浅标准均通过。"],
        )

    def _normalize_scores(self, scores: Dict[str, float]) -> Dict[str, float]:
        normalized = {}
        for dimension in self.dimensions:
            try:
                normalized[dimension] = float(scores.get(dimension, 0))
            except (TypeError, ValueError):
                normalized[dimension] = 0.0
        return normalized

    def evaluate_with_context(
        self,
        scores: Dict[str, float],
        context: dict,
    ) -> GateResult:
        result = self.evaluate(scores)

        if not result.passed:
            if context.get("discussion_rounds", 0) >= 5:
                result.recommendations.append(
                    "已达到最大讨论轮次，建议围绕失败的判浅维度重新立论。"
                )
            if not context.get("materials_used"):
                result.recommendations.append(
                    "缺少具体素材时，判浅维度更容易失败。"
                )

        return result


class BatchQualityAnalyzer:
    """Batch statistics for depth-oriented quality scores."""

    def __init__(self, gate: QualityGate):
        self.gate = gate

    def analyze_batch(self, results: List[dict]) -> dict:
        total = len(results)
        if total == 0:
            return {"total": 0}

        approved = [result for result in results if result.get("status") == "approved"]
        rejected = [result for result in results if result.get("status") == "rejected"]
        all_scores = [result.get("quality_scores", {}) for result in results]

        dimension_stats = {}
        for dimension in QUALITY_DIMENSIONS:
            dimension_scores = [
                score.get(dimension, 0)
                for score in all_scores
                if dimension in score
            ]
            if dimension_scores:
                dimension_stats[dimension] = {
                    "avg": sum(dimension_scores) / len(dimension_scores),
                    "min": min(dimension_scores),
                    "max": max(dimension_scores),
                }

        return {
            "total": total,
            "approved_count": len(approved),
            "rejected_count": len(rejected),
            "pass_rate": len(approved) / total,
            "dimension_stats": dimension_stats,
            "pass_rates": {
                dimension: sum(
                    1
                    for score in all_scores
                    if score.get(dimension, 0) >= QUALITY_DIMENSIONS[dimension]["min_score"]
                )
                / total
                for dimension in QUALITY_DIMENSIONS
            },
        }
