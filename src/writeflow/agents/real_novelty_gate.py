"""Real Novelty Gate Agent - one-vote veto for genuine novelty."""
from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional

from writeflow.agents.base import BaseAgent
from writeflow.agents.claude_client import get_claude_client


NOVELTY_TYPES = {"case", "structure", "solution"}


REAL_NOVELTY_SYSTEM_PROMPT = """你是 WriteFLow 的 Real Novelty Gate。

你不打分，只做一票否决：这篇文章是否至少拥有一个真实的新意资产。

只承认三类真实新意：
1. case：案例新意。参考对象、地点、场景或当事人经验和常见讨论不同。
2. structure：结构新意。解释了事物发展结构、利益机制或约束条件的新差异。
3. solution：方案新意。给出了足够具体、不同于口号的解决方案。

不要奖励抽象姿态、术语堆砌、价值立场或普通“应该重视”。没有真实资产就失败。

输出必须是 JSON：
{
  "passed": true,
  "pass_reason": "real_novelty_present",
  "novelty_assets": [
    {
      "type": "case/structure/solution",
      "claim": "新意资产本身",
      "why_different": "它和陈词滥调有什么不同",
      "evidence_hint": "支撑它的证据方向",
      "must_preserve": "写作时不能丢掉的细节"
    }
  ],
  "missing_reason": "",
  "recommendations": []
}"""


class RealNoveltyGateAgent(BaseAgent):
    """Reject theses that lack case, structural, or solution novelty."""

    def __init__(self, model: Optional[str] = None, api_key: Optional[str] = None):
        self.client = get_claude_client(api_key=api_key, model=model)
        super().__init__("real_novelty_gate", self.client.model)

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        topic = input_data.get("topic", "")
        response = await self.client.generate(
            messages=[{"role": "user", "content": self._build_prompt(input_data)}],
            system_prompt=REAL_NOVELTY_SYSTEM_PROMPT,
            max_tokens=2048,
            temperature=0.2,
        )
        result = self._parse_gate_result(response.get("content", ""))
        result["usage"] = response.get("usage", {})
        result["model"] = self.model
        result["topic"] = topic
        return result

    def _build_prompt(self, input_data: Dict[str, Any]) -> str:
        return f"""请判断下面的核心判断是否拥有真实新意。

主题：{input_data.get("topic", "")}

【人类观察】
{json.dumps(input_data.get("observation_brief", {}), ensure_ascii=False, indent=2)}

【本地真实声音】
{json.dumps(input_data.get("local_voice_brief", {}), ensure_ascii=False, indent=2)}

【参考素材】
{json.dumps(input_data.get("materials", []), ensure_ascii=False, indent=2)}

【Thesis Architect 简报】
{json.dumps(input_data.get("thesis", {}), ensure_ascii=False, indent=2)}

【运行中人工补充】
{json.dumps(input_data.get("human_interventions", []), ensure_ascii=False, indent=2)}

请只判断三类资产：case、structure、solution。
只要三类中有任意一个真实成立，就 passed=true；三类都没有，则 passed=false，pass_reason="no_real_novelty"。"""

    def _parse_gate_result(self, content: str) -> Dict[str, Any]:
        json_match = re.search(r"\{.*\}", content, re.DOTALL)
        if json_match:
            try:
                parsed = json.loads(json_match.group())
                return self._normalize_gate_result(parsed)
            except json.JSONDecodeError:
                pass

        return {
            "passed": False,
            "pass_reason": "parse_error",
            "novelty_assets": [],
            "missing_reason": "Real Novelty Gate output was not valid JSON.",
            "recommendations": ["重新生成 thesis，并明确 case/structure/solution 中至少一种真实新意。"],
        }

    def _normalize_gate_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        assets = self._normalize_assets(result.get("novelty_assets", []))
        passed = bool(result.get("passed")) and bool(assets)
        if not assets:
            passed = False

        return {
            "passed": passed,
            "pass_reason": (
                "real_novelty_present"
                if passed
                else result.get("pass_reason") or "no_real_novelty"
            ),
            "novelty_assets": assets,
            "missing_reason": "" if passed else (
                result.get("missing_reason") or "no_real_novelty"
            ),
            "recommendations": self._string_list(result.get("recommendations", [])),
        }

    def _normalize_assets(self, assets: Any) -> list[dict[str, str]]:
        if not isinstance(assets, list):
            return []

        normalized: list[dict[str, str]] = []
        for asset in assets:
            if not isinstance(asset, dict):
                continue
            asset_type = str(asset.get("type", "")).strip().lower()
            if asset_type not in NOVELTY_TYPES:
                continue
            claim = self._string(asset.get("claim"))
            why_different = self._string(asset.get("why_different"))
            evidence_hint = self._string(asset.get("evidence_hint"))
            must_preserve = self._string(asset.get("must_preserve"))
            if not (claim and (why_different or evidence_hint or must_preserve)):
                continue
            normalized.append(
                {
                    "type": asset_type,
                    "claim": claim,
                    "why_different": why_different,
                    "evidence_hint": evidence_hint,
                    "must_preserve": must_preserve,
                }
            )
        return normalized

    @staticmethod
    def _string(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, (list, tuple)):
            return "; ".join(str(item).strip() for item in value if str(item).strip())
        if isinstance(value, dict):
            return json.dumps(value, ensure_ascii=False)
        return str(value).strip()

    @classmethod
    def _string_list(cls, value: Any) -> list[str]:
        if isinstance(value, list):
            return [cls._string(item) for item in value if cls._string(item)]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        return []
