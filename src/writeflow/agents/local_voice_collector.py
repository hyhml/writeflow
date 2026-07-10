"""Local Voice Collector Agent - normalizes real voices from search context."""
from __future__ import annotations

from typing import Any, Dict, Optional

from writeflow.agents.base import BaseAgent
from writeflow.config import get_settings


VOICE_FIELDS = [
    "speaker_type",
    "location",
    "direct_quote",
    "paraphrase",
    "pain_point",
    "local_specificity",
    "source_url",
    "confidence",
]


class LocalVoiceCollectorAgent(BaseAgent):
    """Collect and normalize first-hand local voices without inventing quotes."""

    def __init__(self, model: Optional[str] = None, api_key: Optional[str] = None):
        settings = get_settings()
        super().__init__("local_voice_collector", model or settings.model)
        self.search_provider = settings.search_provider

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        topic = input_data.get("topic", "")
        observation_brief = input_data.get("observation_brief", {})
        search_results = input_data.get("search_results") or []
        search_provider = (
            input_data.get("search_provider")
            or getattr(self, "search_provider", "none")
            or "none"
        ).lower()

        if search_results:
            voices = self._voices_from_search_results(search_results)
            return {
                "topic": topic,
                "source_status": "from_context",
                "search_provider": search_provider,
                "observation_used": bool(observation_brief),
                "voices": voices,
                "local_voice_brief": {
                    "summary": self._summarize_voices(voices),
                    "voices": voices,
                    "missing_reason": "" if voices else "search_results contained no usable voices",
                },
            }

        if search_provider in {"", "none", "not_configured"}:
            return {
                "topic": topic,
                "source_status": "not_configured",
                "search_provider": "none",
                "observation_used": bool(observation_brief),
                "voices": [],
                "local_voice_brief": {
                    "summary": "",
                    "voices": [],
                    "missing_reason": "WRITEFLOW_SEARCH_PROVIDER=none; no real local voices collected.",
                },
            }

        return {
            "topic": topic,
            "source_status": "provider_configured_no_results",
            "search_provider": search_provider,
            "observation_used": bool(observation_brief),
            "voices": [],
            "local_voice_brief": {
                "summary": "",
                "voices": [],
                "missing_reason": (
                    "Search provider is configured, but this runtime did not receive "
                    "search_results. No quotes were fabricated."
                ),
            },
        }

    def _voices_from_search_results(self, search_results: list[Any]) -> list[dict[str, Any]]:
        voices: list[dict[str, Any]] = []
        for result in search_results:
            if not isinstance(result, dict):
                continue
            voice = self._normalize_voice(result)
            if voice["direct_quote"] or voice["paraphrase"] or voice["pain_point"]:
                voices.append(voice)
        return voices

    def _normalize_voice(self, result: Dict[str, Any]) -> Dict[str, Any]:
        quote = self._string(result.get("direct_quote") or result.get("quote") or "")
        paraphrase = self._string(
            result.get("paraphrase")
            or result.get("snippet")
            or result.get("content")
            or result.get("text")
            or ""
        )
        return {
            "speaker_type": self._string(result.get("speaker_type") or result.get("speaker") or "unknown"),
            "location": self._string(result.get("location") or ""),
            "direct_quote": quote[:240],
            "paraphrase": paraphrase[:500],
            "pain_point": self._string(result.get("pain_point") or result.get("pain") or "")[:240],
            "local_specificity": self._string(result.get("local_specificity") or "")[:240],
            "source_url": self._string(result.get("source_url") or result.get("url") or ""),
            "confidence": self._coerce_confidence(result.get("confidence", 0.5)),
        }

    def _summarize_voices(self, voices: list[dict[str, Any]]) -> str:
        if not voices:
            return ""
        pain_points = [voice["pain_point"] for voice in voices if voice.get("pain_point")]
        locations = [voice["location"] for voice in voices if voice.get("location")]
        parts = []
        if pain_points:
            parts.append("主要痛点：" + "；".join(pain_points[:3]))
        if locations:
            parts.append("地点线索：" + "、".join(locations[:3]))
        return " ".join(parts)

    @staticmethod
    def _string(value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip()

    @staticmethod
    def _coerce_confidence(value: Any) -> float:
        try:
            score = float(value)
        except (TypeError, ValueError):
            return 0.5
        return max(0.0, min(1.0, score))
