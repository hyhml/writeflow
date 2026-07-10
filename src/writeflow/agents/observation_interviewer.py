"""Observation Interviewer Agent - turns human observation into writing assets."""
from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional

from writeflow.agents.base import BaseAgent
from writeflow.agents.claude_client import get_claude_client


OBSERVATION_QUESTIONS = [
    "你在本地看到的反常现象是什么？",
    "这个地方或案例和常见讨论有什么不一样？",
    "你直觉上觉得真正的问题根源是什么？",
    "你想到的具体解决方案是什么？",
    "有哪些细节一旦丢掉，文章就会变成陈词滥调？",
]


OBSERVATION_SYSTEM_PROMPT = """你是 WriteFLow 的 Observation Interviewer。

你的任务不是替用户编造本地经验，而是把用户提供的人类观察整理成可供后续 Agent 使用的 observation_brief。

必须追问或整理五类内容：
1. 反常现象
2. 案例差异
3. 直觉问题根源
4. 具体解决方案
5. 不可丢失细节

要求：
- 如果用户已经提供观察，只整理、提炼、保留锋利细节，不要擅自添加事实。
- 如果用户没有提供观察，输出 observation_questions，不要编造本地经验。
- 只输出 JSON，不要输出 Markdown。"""


class ObservationInterviewerAgent(BaseAgent):
    """Prepare human observation before research and thesis building."""

    def __init__(self, model: Optional[str] = None, api_key: Optional[str] = None):
        self.client = get_claude_client(api_key=api_key, model=model)
        super().__init__("observation_interviewer", self.client.model)

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        topic = input_data.get("topic", "")
        human_observation = str(input_data.get("human_observation") or "").strip()

        if not human_observation:
            return self._missing_observation_result(topic)

        response = await self.client.generate(
            messages=[
                {
                    "role": "user",
                    "content": self._build_prompt(topic, human_observation),
                }
            ],
            system_prompt=OBSERVATION_SYSTEM_PROMPT,
            max_tokens=2048,
            temperature=0.25,
        )
        result = self._parse_observation_result(response.get("content", ""), topic)
        result["usage"] = response.get("usage", {})
        result["model"] = self.model
        return result

    def _build_prompt(self, topic: str, human_observation: str) -> str:
        return f"""请把下面的人类观察整理成 observation_brief。

主题：{topic}

用户观察：
{human_observation}

请输出 JSON：
{{
  "missing_observation": false,
  "observation_brief": {{
    "abnormal_phenomenon": "反常现象",
    "case_difference": "这个案例和常见讨论的差异",
    "intuitive_root_cause": "用户直觉中的真正问题根源",
    "concrete_solution": "用户想到的具体解决方案",
    "must_preserve_details": ["不可丢失细节"]
  }},
  "observation_questions": [],
  "must_preserve": ["后续写作必须保留的细节"]
}}"""

    def _parse_observation_result(self, content: str, topic: str) -> Dict[str, Any]:
        json_match = re.search(r"\{.*\}", content, re.DOTALL)
        if json_match:
            try:
                parsed = json.loads(json_match.group())
                return self._normalize_observation(parsed, topic)
            except json.JSONDecodeError:
                pass

        return {
            **self._missing_observation_result(topic),
            "parse_warning": "Model output was not valid JSON; no observation was fabricated.",
            "raw_content": content[:1000],
        }

    def _normalize_observation(self, parsed: Dict[str, Any], topic: str) -> Dict[str, Any]:
        brief = parsed.get("observation_brief") or {}
        if not isinstance(brief, dict):
            brief = {"raw_observation": str(brief)}

        normalized_brief = {
            "abnormal_phenomenon": self._stringify(brief.get("abnormal_phenomenon", "")),
            "case_difference": self._stringify(brief.get("case_difference", "")),
            "intuitive_root_cause": self._stringify(brief.get("intuitive_root_cause", "")),
            "concrete_solution": self._stringify(brief.get("concrete_solution", "")),
            "must_preserve_details": self._string_list(
                brief.get("must_preserve_details", parsed.get("must_preserve", []))
            ),
        }

        has_brief = any(
            value for key, value in normalized_brief.items() if key != "must_preserve_details"
        ) or bool(normalized_brief["must_preserve_details"])

        return {
            "missing_observation": not has_brief,
            "topic": topic,
            "observation_brief": normalized_brief if has_brief else {},
            "observation_questions": [] if has_brief else list(OBSERVATION_QUESTIONS),
            "must_preserve": normalized_brief["must_preserve_details"],
            "source_status": "user_provided" if has_brief else "missing_human_observation",
        }

    @staticmethod
    def _missing_observation_result(topic: str) -> Dict[str, Any]:
        return {
            "missing_observation": True,
            "topic": topic,
            "observation_brief": {},
            "observation_questions": list(OBSERVATION_QUESTIONS),
            "must_preserve": [],
            "source_status": "missing_human_observation",
        }

    @staticmethod
    def _stringify(value: Any) -> str:
        if isinstance(value, str):
            return value.strip()
        if value is None:
            return ""
        if isinstance(value, (list, tuple)):
            return "; ".join(str(item).strip() for item in value if str(item).strip())
        if isinstance(value, dict):
            return json.dumps(value, ensure_ascii=False)
        return str(value).strip()

    @classmethod
    def _string_list(cls, value: Any) -> list[str]:
        if isinstance(value, list):
            return [cls._stringify(item) for item in value if cls._stringify(item)]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        return []
