"""Thesis Architect Agent - builds the core argumentative thesis."""
from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional

from writeflow.agents.base import BaseAgent
from writeflow.agents.claude_client import get_claude_client


THESIS_ARCHITECT_SYSTEM_PROMPT = """你是 Thesis Architect，不写正文，只负责把一个写作主题压缩成有冲突、有证据、有风险的核心判断。

你的目标不是给出稳妥摘要，而是帮助后续 Writer 找到一条值得证明的主张。

必须回答五个问题：
1. 这篇文章最想证明的一句话是什么？
2. 这句话和普通观点有什么冲突？
3. 如果这句话成立，会推翻什么常识？
4. 最强证据是什么？
5. 最危险的反驳是什么？

要求：
- core_claim 必须是一句可争辩的判断，不要写成“需要加强”“应该重视”“要辩证看待”。
- 不要直接写文章段落。
- 不要输出 Markdown。
- 只输出 JSON。"""


REQUIRED_THESIS_FIELDS = [
    "core_claim",
    "conflict_with_common_view",
    "common_sense_overturned",
    "strongest_evidence",
    "most_dangerous_counterargument",
]


class ThesisArchitectAgent(BaseAgent):
    """Agent that turns materials into a focused thesis brief."""

    def __init__(self, model: Optional[str] = None, api_key: Optional[str] = None):
        self.client = get_claude_client(api_key=api_key, model=model)
        super().__init__("thesis_architect", self.client.model)

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        topic = input_data.get("topic", "")
        materials = input_data.get("materials", [])

        response = await self.client.generate(
            messages=[{"role": "user", "content": self._build_prompt(topic, materials)}],
            system_prompt=THESIS_ARCHITECT_SYSTEM_PROMPT,
            max_tokens=2048,
            temperature=0.45,
        )

        thesis = self._parse_thesis_result(response.get("content", ""), topic)
        thesis["usage"] = response.get("usage", {})
        thesis["model"] = self.model
        return thesis

    def _build_prompt(self, topic: str, materials: list[dict[str, Any]]) -> str:
        materials_context = self._build_materials_context(materials)
        return f"""请为下面的写作任务生成“核心判断简报”。

主题：{topic}

参考素材：
{materials_context}

请只输出 JSON，字段必须完全包含：
{{
  "core_claim": "一句最想证明的判断",
  "conflict_with_common_view": "它和普通观点的冲突",
  "common_sense_overturned": "如果成立，会推翻什么常识",
  "strongest_evidence": "最强证据或论据方向",
  "most_dangerous_counterargument": "最危险的反驳"
}}"""

    def _build_materials_context(self, materials: list[dict[str, Any]]) -> str:
        if not materials:
            return "无素材，请基于主题独立提出一个可争辩的核心判断。"

        lines = []
        for index, material in enumerate(materials[:8], 1):
            content = str(material.get("content", "")).strip()
            source = str(material.get("source", "未知来源")).strip()
            material_type = str(material.get("material_type", "material")).strip()
            if content:
                lines.append(f"{index}. [{material_type}] {content} (来源: {source})")
        return "\n".join(lines) if lines else "素材为空，请基于主题独立判断。"

    def _parse_thesis_result(self, content: str, topic: str) -> Dict[str, Any]:
        json_match = re.search(r"\{.*\}", content, re.DOTALL)
        if json_match:
            try:
                parsed = json.loads(json_match.group())
                return self._normalize_thesis(parsed, topic, content)
            except json.JSONDecodeError:
                pass

        return self._fallback_thesis(topic, content)

    def _normalize_thesis(
        self,
        parsed: Dict[str, Any],
        topic: str,
        raw_content: str,
    ) -> Dict[str, Any]:
        thesis = {}
        for field in REQUIRED_THESIS_FIELDS:
            value = parsed.get(field, "")
            thesis[field] = self._stringify_value(value)

        missing = [field for field in REQUIRED_THESIS_FIELDS if not thesis[field].strip()]
        if missing:
            fallback = self._fallback_thesis(topic, raw_content)
            for field in missing:
                thesis[field] = fallback[field]
            thesis["parse_warning"] = f"Missing fields filled by fallback: {', '.join(missing)}"

        return thesis

    def _fallback_thesis(self, topic: str, raw_content: str) -> Dict[str, Any]:
        summary = raw_content.strip()[:500]
        return {
            "core_claim": f"{topic} 的关键问题不是是否需要治理，而是谁有权定义问题本身。",
            "conflict_with_common_view": "普通观点通常把它看成技术、管理或资源分配问题。",
            "common_sense_overturned": "如果这个判断成立，许多看似中立的解决方案其实是在延续既有权力分配。",
            "strongest_evidence": summary or "需要从制度安排、利益结构和具体个案中寻找证据。",
            "most_dangerous_counterargument": "反对者可以指出这种判断过度政治化，忽视了现实执行中的复杂约束。",
            "parse_warning": "Model output was not valid JSON; fallback thesis was generated.",
        }

    @staticmethod
    def _stringify_value(value: Any) -> str:
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, (list, tuple)):
            return "; ".join(str(item).strip() for item in value if str(item).strip())
        if isinstance(value, dict):
            return json.dumps(value, ensure_ascii=False)
        return str(value).strip() if value is not None else ""
