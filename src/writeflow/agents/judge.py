"""Judge Agent - shallow-depth evaluation."""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from writeflow.agents.base import BaseAgent
from writeflow.agents.claude_client import get_claude_client


QUALITY_DIMENSIONS = {
    "新判断": {
        "weight": 0.20,
        "description": "文章是否提出了普通观点之外的新判断",
    },
    "概念克制": {
        "weight": 0.20,
        "description": "文章是否避免用概念堆砌制造深刻假象",
    },
    "句子必要性": {
        "weight": 0.20,
        "description": "文章中的句子是否有推进作用，是否存在删掉反而更强的空话",
    },
    "层次穿透": {
        "weight": 0.20,
        "description": "文章是否穿透第一层解释，说明机制、获益者和代价承担者",
    },
    "方案具体性": {
        "weight": 0.20,
        "description": "文章的解决方案是否具体，是否避免口号化收尾",
    },
}


JUDGE_SYSTEM_PROMPT = """你是 WriteFLow 的 Judge。你的任务不是评价文章“写得好不好”，也不是奖励术语、文采、完整度或姿态。

你只负责判浅：判断文章是否浅、空、概念堆砌、只讲第一层、靠口号收尾。

必须围绕五个问题审稿：
1. 有没有新判断？
2. 有没有概念堆砌？
3. 有没有一句话删掉后文章更强？
4. 有没有每段都只讲到第一层？
5. 解决方案是否只是口号？

评分方式：
- 每项 1-10 分。
- 10 分表示非常扎实，几乎没有对应问题。
- 6 分表示勉强通过。
- 1-5 分表示存在明显浅度问题。

通过条件：
- 五项全部 >= 6 才能通过。
- 任一项 < 6 即失败，pass_reason 必须是 "shallow_dimensions"。
- 全部 >= 6 时，pass_reason 必须是 "depth_passed"。

输出必须是 JSON，不要输出 Markdown，不要解释自己的审稿过程。格式：
{
  "quality_scores": {
    "新判断": 7,
    "概念克制": 6,
    "句子必要性": 6,
    "层次穿透": 7,
    "方案具体性": 6
  },
  "passed": true,
  "pass_reason": "depth_passed",
  "failed_dimensions": [],
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

        evaluation_prompt = self._build_evaluation_prompt(
            topic, content, criticisms, defenses, materials
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
    ) -> str:
        """Build the depth-focused evaluation prompt."""
        prompt = f"""请对下面这篇文章做“判浅”审稿，而不是综合质量评分。

主题：{topic}

文章内容：
{content[:3000]}...

你只需要回答五个判浅问题：
1. 有没有新判断？
2. 有没有概念堆砌？
3. 有没有一句话删掉后文章更强？
4. 有没有每段都只讲到第一层？
5. 解决方案是否只是口号？

请用这五个维度给出 1-10 分：
- 新判断
- 概念克制
- 句子必要性
- 层次穿透
- 方案具体性
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
输出 JSON。不要因为语言顺、术语多、结构完整就给高分；只看它是否真正不浅。"""
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
        result["passed"] = not failed
        result["pass_reason"] = "depth_passed" if not failed else "shallow_dimensions"
        result.setdefault("key_issues", [])
        result.setdefault("recommendations", [])
        return result

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
