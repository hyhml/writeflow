"""
质量门禁 - 7维质量评估和质量Gate判定
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


# 7维质量评估配置
QUALITY_DIMENSIONS = {
    "批判锋芒": {"weight": 0.20, "min_score": 4.0},
    "理论深度": {"weight": 0.15, "min_score": 4.0},
    "洞察力度": {"weight": 0.15, "min_score": 4.0},
    "论证严谨性": {"weight": 0.20, "min_score": 4.0},
    "社会关联度": {"weight": 0.10, "min_score": 4.0},
    "文字穿透力": {"weight": 0.10, "min_score": 4.0},
    "学术规范性": {"weight": 0.10, "min_score": 4.0},
}


@dataclass
class QualityScores:
    """质量评分"""
    scores: Dict[str, float]

    @property
    def total(self) -> float:
        return sum(self.scores.values())

    @property
    def average(self) -> float:
        return self.total / len(self.scores) if self.scores else 0

    def excellent_dimensions(self, threshold: float = 8.0) -> List[str]:
        return [k for k, v in self.scores.items() if v >= threshold]

    def failed_dimensions(self, threshold: float = 4.0) -> List[str]:
        return [k for k, v in self.scores.items() if v < threshold]

    def is_all_developed(self, threshold: float = 6.0) -> bool:
        return all(v >= threshold for v in self.scores.values())


@dataclass
class GateResult:
    """Gate判定结果"""
    passed: bool
    reason: str  # excellent_dimensions / total_score / all_developed / failed
    quality_scores: QualityScores
    excellent_dimensions: List[str] = field(default_factory=list)
    failed_dimensions: List[str] = field(default_factory=list)
    total_score: float = 0
    recommendations: List[str] = field(default_factory=list)


class QualityGate:
    """
    质量门禁

    通过条件（满足任一即可）：
    1. 至少2个维度≥8分（优秀维度）
    2. 总分≥56分（7维度满分70分的80%）
    3. 5个维度全部≥6分（全面发展）

    拒绝条件（满足任一即拒）：
    1. 任何维度<4分（严重缺陷）
    """

    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}
        self.dimensions = QUALITY_DIMENSIONS

        # 从配置覆盖
        for dim, dim_config in self.config.get("dimensions", {}).items():
            if dim in self.dimensions:
                self.dimensions[dim].update(dim_config)

    def evaluate(self, scores: Dict[str, float]) -> GateResult:
        """
        评估质量是否通过Gate

        Args:
            scores: {"维度": 分数, ...}

        Returns:
            GateResult
        """
        quality_scores = QualityScores(scores=scores)

        # 计算
        total_score = quality_scores.total
        excellent_dims = quality_scores.excellent_dimensions(8.0)
        failed_dims = quality_scores.failed_dimensions(4.0)

        recommendations = []

        # 拒绝条件检查
        if failed_dims:
            return GateResult(
                passed=False,
                reason="failed_dimensions",
                quality_scores=quality_scores,
                failed_dimensions=failed_dims,
                total_score=total_score,
                recommendations=[
                    f"以下维度存在严重缺陷（<4分）：{', '.join(failed_dims)}",
                    "需要大幅改进后才能重新提交",
                ],
            )

        # 通过条件检查
        if len(excellent_dims) >= 2:
            return GateResult(
                passed=True,
                reason="excellent_dimensions",
                quality_scores=quality_scores,
                excellent_dimensions=excellent_dims,
                total_score=total_score,
                recommendations=["稿件质量优秀，满足优秀门槛"],
            )

        if total_score >= 56:  # 80% of 70
            return GateResult(
                passed=True,
                reason="total_score",
                quality_scores=quality_scores,
                excellent_dimensions=excellent_dims,
                total_score=total_score,
                recommendations=["稿件总分达标"],
            )

        if quality_scores.is_all_developed(6.0):
            return GateResult(
                passed=True,
                reason="all_developed",
                quality_scores=quality_scores,
                excellent_dimensions=excellent_dims,
                total_score=total_score,
                recommendations=["稿件全面发展，各维度均衡"],
            )

        # 未达标
        suggestions = []
        if len(excellent_dims) < 2:
            suggestions.append(
                f"当前{excellent_dims or '无'}维度达到优秀水平（≥8分），"
                "需要至少2个维度达到优秀"
            )
        if total_score < 56:
            suggestions.append(f"当前总分{total_score}，需要达到56分以上")
        if not quality_scores.is_all_developed(6.0):
            weak_dims = [k for k, v in scores.items() if v < 6.0]
            suggestions.append(f"以下维度需要提升至6分以上：{', '.join(weak_dims)}")

        return GateResult(
            passed=False,
            reason="not_meets_threshold",
            quality_scores=quality_scores,
            excellent_dimensions=excellent_dims,
            total_score=total_score,
            recommendations=suggestions,
        )

    def evaluate_with_context(
        self,
        scores: Dict[str, float],
        context: dict
    ) -> GateResult:
        """
        结合上下文的评估

        Args:
            scores: 质量评分
            context: {
                "topic": str,
                "materials_used": bool,
                "criticism_count": int,
                "discussion_rounds": int,
            }
        """
        result = self.evaluate(scores)

        # 根据上下文调整建议
        if not result.passed:
            if context.get("discussion_rounds", 0) >= 5:
                result.recommendations.append(
                    "已达到最大讨论轮次，建议进行重大修订后重新提交"
                )

            if not context.get("materials_used"):
                result.recommendations.append(
                    "建议收集更多素材支撑论点"
                )

        return result


class BatchQualityAnalyzer:
    """批量质量分析器"""

    def __init__(self, gate: QualityGate):
        self.gate = gate

    def analyze_batch(self, results: List[dict]) -> dict:
        """
        分析批量结果的质量统计

        Args:
            results: [{"quality_scores": {...}, "status": "approved/rejected", ...}, ...]

        Returns:
            统计报告
        """
        total = len(results)
        if total == 0:
            return {"total": 0}

        # 按状态分类
        approved = [r for r in results if r.get("status") == "approved"]
        rejected = [r for r in results if r.get("status") == "rejected"]

        # 质量统计
        all_scores = [r.get("quality_scores", {}) for r in results]
        dimension_stats = {}

        for dim in QUALITY_DIMENSIONS.keys():
            dim_scores = [s.get(dim, 0) for s in all_scores if dim in s]
            if dim_scores:
                dimension_stats[dim] = {
                    "avg": sum(dim_scores) / len(dim_scores),
                    "min": min(dim_scores),
                    "max": max(dim_scores),
                }

        return {
            "total": total,
            "approved_count": len(approved),
            "rejected_count": len(rejected),
            "pass_rate": len(approved) / total,
            "dimension_stats": dimension_stats,
            "excellent_rates": {
                dim: sum(1 for s in all_scores if s.get(dim, 0) >= 8.0) / total
                for dim in QUALITY_DIMENSIONS.keys()
            },
        }
