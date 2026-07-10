"""Judge Agent - shallow-depth evaluation."""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from writeflow.agents.base import BaseAgent
from writeflow.agents.claude_client import get_claude_client


QUALITY_DIMENSIONS = {
    "概念克制": {
        "weight": 0.25,
        "description": "文章是否避免用概念堆砌制造深刻假象",
    },
    "句子必要性": {
        "weight": 0.25,
        "description": "文章中的句子是否有推进作用，是否存在删掉反而更强的空话",
    },
    "层次穿透": {
        "weight": 0.25,
        "description": "文章是否穿透第一层解释，说明机制、获益者和代价承担者",
    },
    "方案具体性": {
        "weight": 0.25,
        "description": "文章的解决方案是否具体，是否避免口号化收尾",
    },
}


JUDGE_SYSTEM_PROMPT = """你是 WriteFLow 的 Judge。你的任务不是评价文章“写得好不好”，也不是奖励术语、文采、完整度或姿态。

你只负责判浅：判断文章是否浅、空、概念堆砌、只讲第一层、靠口号收尾。
文章是否有真实新意已经由 Real Novelty Gate 一票否决，你不要再给“新判断”打分。

必须围绕四个判浅问题审稿：
1. 有没有概念堆砌？
2. 有没有一句话删掉后文章更强？
3. 有没有每段都只讲到第一层？
4. 解决方案是否只是口号？

同时你必须围绕 novelty_assets 逐条提出 depth_questions，追问它是否真的被讲透：
- case：具体案例的地点、矛盾、独特条件是否讲透？
- structure：结构机制、获益者、代价承担者是否讲清？
- solution：具体方案的利益冲突、代价、执行阻力是否讲清？
- mechanism/counterargument：机制和最危险反驳是否被正面处理？

评分方式：
- 每项 1-10 分。
- 10 分表示非常扎实，几乎没有对应问题。
- 6 分表示勉强通过。
- 1-5 分表示存在明显浅度问题。

通过条件：
- 四项全部 >= 6 才能通过。
- 任一项 < 6 即失败，pass_reason 必须是 "shallow_dimensions"。
- 即使四项 >= 6，只要任何关键 depth_questions 的 status 是 "missing" 或 "not_deep_enough"，也不能通过。
- 全部 >= 6 且关键问题均 answered 时，pass_reason 必须是 "depth_passed"。

输出必须是 JSON，不要输出 Markdown，不要解释自己的审稿过程。格式：
{
  "quality_scores": {
    "概念克制": 6,
    "句子必要性": 6,
    "层次穿透": 7,
    "方案具体性": 6
  },
  "passed": true,
  "pass_reason": "depth_passed",
  "failed_dimensions": [],
  "depth_questions": [
    {
      "target": "case/structure/solution/mechanism/counterargument",
      "question": "必须回答的具体问题",
      "why_it_matters": "为什么关系到文章深度",
      "status": "answered/not_deep_enough/missing",
      "required_revision": "Writer 下一轮必须怎么改"
    }
  ],
  "verdict": "通过/需要修改/拒绝",
  "key_issues": ["主要浅度问题"],
  "recommendations": ["具体修改建议"]
}"""


class JudgeAgent(BaseAgent):
    """Judge Agent focused on shallow-depth rejection."""

    def __init__(self, model: Optional[str] = None, api_key: Optional[str] = None):
        self.client = get_claude_client(api_key=api_key, model=model)
        super().__init__("judge", self.client.model)
        self.dimensions = QUALITY_DIMENSIONS

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        content = input_data.get("content", "")
        topic = input_data.get("topic", "")
        criticisms = input_data.get("criticisms", [])
        defenses = input_data.get("defenses", "")
        materials = input_data.get("materials", [])
        thesis = input_data.get("thesis", {})
        novelty_assets = input_data.get("novelty_assets", [])

        evaluation_prompt = self._build_evaluation_prompt(
            topic, content, criticisms, defenses, materials, thesis, novelty_assets
        )

        response = await self.client.generate(
            messages=[{"role": "user", "content": evaluation_prompt}],
            system_prompt=JUDGE_SYSTEM_PROMPT,
            max_tokens=4096,
            temperature=0.3,
        )

        return self._parse_evaluation(response["content"])

    def _build_evaluation_prompt(
        self,
        topic: str,
        content: str,
        criticisms: List[dict],
        defenses: str,
        materials: List[dict],
        thesis: Optional[dict] = None,
        novelty_assets: Optional[List[dict]] = None,
    ) -> str:
        """Build the depth-focused evaluation prompt."""
        prompt = f"""请对下面这篇文章做“判浅”审稿，而不是综合质量评分。

主题：{topic}

【核心判断】
{json.dumps(thesis or {}, ensure_ascii=False, indent=2)}

【真实新意资产】
{json.dumps(novelty_assets or [], ensure_ascii=False, indent=2)}

文章内容：
{content[:3000]}...

你只需要回答四个判浅问题：
1. 有没有概念堆砌？
2. 有没有一句话删掉后文章更强？
3. 有没有每段都只讲到第一层？
4. 解决方案是否只是口号？

请用这四个维度给出 1-10 分：
- 概念克制
- 句子必要性
- 层次穿透
- 方案具体性

同时必须输出 depth_questions，逐条绑定 novelty_assets，提出 Writer 下一轮必须回答的具体问题。
例如：深圳地形和交通节点的关系讲透了吗？为什么微更新不够，机制讲清了吗？
划转车道的利益冲突、代价、执行阻力讲了吗？有没有段落只是重复“算法压迫”和“底层困境”？
"""

        if criticisms:
            prompt += "\n【质疑摘要】\n"
            for index, criticism in enumerate(criticisms[:5], 1):
                question = criticism.get("question", criticism.get("content", ""))
                prompt += f"{index}. {question}\n"

        if defenses:
            prompt += f"\n【作者辩护回应】\n{defenses[:500]}...\n"

        if materials:
            prompt += "\n【可用素材概况】\n"
            for index, material in enumerate(materials[:5], 1):
                prompt += f"{index}. {material.get('content', '')}\n"

        prompt += """
输出 JSON。不要因为语言顺、术语多、结构完整就给高分；只看它是否真正不浅，是否把真实新意资产讲透。"""
        return prompt

    def _parse_evaluation(self, content: str) -> Dict[str, Any]:
        """Parse judge JSON and normalize scores to the five depth dimensions."""
        json_match = re.search(r"\{.*\}", content, re.DOTALL)
        if json_match:
            try:
                result = json.loads(json_match.group())
                return self._normalize_evaluation(result)
            except (json.JSONDecodeError, TypeError, ValueError):
                pass

        scores = {dimension: 0.0 for dimension in QUALITY_DIMENSIONS}
        return {
            "quality_scores": scores,
            "total_score": 0.0,
            "passed": False,
            "pass_reason": "parse_error",
            "failed_dimensions": list(QUALITY_DIMENSIONS),
            "excellent_dimensions": [],
            "depth_questions": [],
            "parse_error": "Failed to parse evaluation",
        }

    def _normalize_evaluation(self, result: Dict[str, Any]) -> Dict[str, Any]:
        raw_scores = result.get("quality_scores", {})
        scores = {
            dimension: self._coerce_score(raw_scores.get(dimension, 0))
            for dimension in QUALITY_DIMENSIONS
        }
        failed = [dimension for dimension, score in scores.items() if score < 6]
        total = sum(scores.values())

        result["quality_scores"] = scores
        result["total_score"] = total
        result["failed_dimensions"] = failed
        result["excellent_dimensions"] = []
        depth_questions = self._normalize_depth_questions(result.get("depth_questions", []))
        blocking_questions = [
            question
            for question in depth_questions
            if question.get("status") in {"missing", "not_deep_enough"}
        ]
        result["depth_questions"] = depth_questions
        result["passed"] = not failed and not blocking_questions
        if failed:
            result["pass_reason"] = "shallow_dimensions"
        elif blocking_questions:
            result["pass_reason"] = "unanswered_depth_questions"
        else:
            result["pass_reason"] = "depth_passed"
        result.setdefault("key_issues", [])
        recommendations = result.get("recommendations", [])
        if not isinstance(recommendations, list):
            recommendations = [str(recommendations)]
        recommendations.extend(
            question["required_revision"]
            for question in blocking_questions
            if question.get("required_revision")
        )
        result["recommendations"] = recommendations
        return result

    def _normalize_depth_questions(self, questions: Any) -> List[Dict[str, str]]:
        if not isinstance(questions, list):
            return []

        normalized: List[Dict[str, str]] = []
        valid_statuses = {"answered", "not_deep_enough", "missing"}
        valid_targets = {"case", "structure", "solution", "mechanism", "counterargument"}
        for question in questions:
            if not isinstance(question, dict):
                continue
            status = str(question.get("status", "missing")).strip()
            target = str(question.get("target", "mechanism")).strip()
            normalized.append(
                {
                    "target": target if target in valid_targets else "mechanism",
                    "question": str(question.get("question", "")).strip(),
                    "why_it_matters": str(question.get("why_it_matters", "")).strip(),
                    "status": status if status in valid_statuses else "missing",
                    "required_revision": str(
                        question.get("required_revision", "")
                    ).strip(),
                }
            )
        return [question for question in normalized if question["question"]]

    @staticmethod
    def _coerce_score(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def calculate_weighted_score(self, scores: Dict[str, float]) -> float:
        """Return a percentage-like score for reporting compatibility."""
        total = 0.0
        for dimension, config in self.dimensions.items():
            total += (self._coerce_score(scores.get(dimension, 0)) / 10) * config["weight"]
        return total * 100
