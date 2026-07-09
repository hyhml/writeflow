"""
Model client abstraction.

DeepSeek and MiniMax are called through OpenAI-compatible chat completions.
Anthropic is still supported, but imported lazily so DeepSeek/MiniMax users do
not need the Anthropic SDK installed.
"""
from __future__ import annotations

import asyncio
import json
import time
import urllib.error
import urllib.request
from dataclasses import replace
from typing import Any, Dict, List, Optional

from writeflow.config import Settings, get_settings


class ModelClientError(RuntimeError):
    """Raised when the configured model backend cannot complete a request."""


class ModelClient:
    """Unified LLM client used by all agents."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        provider: Optional[str] = None,
        base_url: Optional[str] = None,
        settings: Optional[Settings] = None,
    ):
        base_settings = settings or get_settings()
        self.settings = replace(
            base_settings,
            provider=(provider or base_settings.provider).lower(),
            api_key=api_key or base_settings.api_key,
            model=model or base_settings.model,
            base_url=(base_url or base_settings.base_url).rstrip("/"),
        )
        self.provider = self.settings.provider
        self.model = self.settings.model
        self.max_tokens = self.settings.max_tokens
        self.temperature = self.settings.temperature
        self.timeout = self.settings.request_timeout
        self.max_retries = self.settings.max_retries

    async def generate(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Generate one assistant response."""
        if self.provider == "anthropic":
            return await asyncio.to_thread(
                self._generate_anthropic,
                messages,
                system_prompt,
                max_tokens,
                temperature,
            )

        return await asyncio.to_thread(
            self._generate_openai_compatible,
            messages,
            system_prompt,
            max_tokens,
            temperature,
        )

    def _require_api_key(self) -> str:
        if not self.settings.api_key:
            raise ModelClientError(
                "未找到模型 API Key。请设置 WRITEFLOW_PROVIDER 和对应密钥："
                "DEEPSEEK_API_KEY、MINIMAX_API_KEY、ANTHROPIC_API_KEY，"
                "或 WRITEFLOW_API_KEY。"
            )
        return self.settings.api_key

    def _chat_completions_url(self) -> str:
        if not self.settings.base_url:
            raise ModelClientError(
                "缺少 Base URL。openai_compatible provider 需要设置 "
                "WRITEFLOW_BASE_URL；deepseek/minimax 会使用默认地址。"
            )
        if self.settings.base_url.endswith("/chat/completions"):
            return self.settings.base_url
        return f"{self.settings.base_url}/chat/completions"

    def _with_system_prompt(
        self, messages: List[Dict[str, str]], system_prompt: Optional[str]
    ) -> List[Dict[str, str]]:
        if not system_prompt:
            return messages
        return [{"role": "system", "content": system_prompt}, *messages]

    def _generate_openai_compatible(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str],
        max_tokens: Optional[int],
        temperature: Optional[float],
    ) -> Dict[str, Any]:
        key = self._require_api_key()
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": self._with_system_prompt(messages, system_prompt),
            "max_tokens": max_tokens or self.max_tokens,
            "temperature": self.temperature if temperature is None else temperature,
            "stream": False,
        }

        # DeepSeek supports these optional OpenAI-compatible extra fields.
        if self.provider == "deepseek":
            if self._env_flag("DEEPSEEK_THINKING"):
                payload["thinking"] = {"type": "enabled"}
            reasoning_effort = self._env_text("DEEPSEEK_REASONING_EFFORT")
            if reasoning_effort:
                payload["reasoning_effort"] = reasoning_effort

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        }
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        last_error: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            try:
                req = urllib.request.Request(
                    self._chat_completions_url(),
                    data=data,
                    headers=headers,
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=self.timeout) as response:
                    body = response.read().decode("utf-8")
                return self._parse_openai_response(json.loads(body))
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")
                last_error = ModelClientError(self._format_http_error(exc.code, detail))
                if 400 <= exc.code < 500 and exc.code not in {408, 429}:
                    break
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                last_error = ModelClientError(
                    f"{self.provider} API 请求失败: {exc}"
                )

            if attempt < self.max_retries:
                time.sleep(min(2**attempt, 8))

        if isinstance(last_error, ModelClientError):
            raise last_error
        raise ModelClientError(f"{self.provider} API 请求失败。")

    def _parse_openai_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        choices = response.get("choices") or []
        if choices:
            message = choices[0].get("message") or {}
            content = self._normalize_content(message.get("content"))
        else:
            # Some compatible APIs may use a flatter response in error-free cases.
            content = self._normalize_content(response.get("reply") or response.get("content"))

        if not content.strip():
            raise ModelClientError(
                f"{self.provider} API 返回了空内容，请检查模型名、账号额度或接口响应格式。"
            )

        usage = response.get("usage") or {}
        return {
            "content": content,
            "usage": {
                "input_tokens": usage.get("prompt_tokens", usage.get("input_tokens", 0)),
                "output_tokens": usage.get(
                    "completion_tokens", usage.get("output_tokens", 0)
                ),
                "cache_read_input_tokens": usage.get("cache_read_input_tokens", 0),
            },
            "stop_reason": choices[0].get("finish_reason") if choices else None,
            "model": response.get("model", self.model),
            "provider": self.provider,
        }

    def _format_http_error(self, status_code: int, detail: str) -> str:
        prefix = f"{self.provider} API HTTP {status_code}"
        hint = {
            401: "认证失败，请检查 API Key 是否正确。",
            403: "请求被拒绝，请检查账号权限、模型权限或余额。",
            408: "请求超时，可以稍后重试或调大 WRITEFLOW_TIMEOUT。",
            429: "请求过于频繁或额度不足，请稍后重试。",
        }.get(status_code, "接口请求失败。")
        return f"{prefix}: {hint} 响应: {detail[:1000]}"

    @staticmethod
    def _normalize_content(content: Any) -> str:
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    text = item.get("text") or item.get("content")
                    if isinstance(text, str):
                        parts.append(text)
            return "\n".join(parts)
        return str(content)

    def _generate_anthropic(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str],
        max_tokens: Optional[int],
        temperature: Optional[float],
    ) -> Dict[str, Any]:
        key = self._require_api_key()
        try:
            import anthropic
        except ImportError as exc:
            raise ModelClientError(
                "Anthropic provider selected but the anthropic package is not "
                "installed. Run `pip install '.[anthropic]'` or switch "
                "WRITEFLOW_PROVIDER to deepseek/minimax."
            ) from exc

        client = anthropic.Anthropic(
            api_key=key,
            max_retries=self.max_retries,
            timeout=self.timeout,
        )
        params: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens or self.max_tokens,
            "temperature": self.temperature if temperature is None else temperature,
        }
        if system_prompt:
            params["system"] = system_prompt

        response = client.messages.create(**params)
        usage = response.usage
        content = response.content[0].text if response.content else ""
        if not content.strip():
            raise ModelClientError(
                "Anthropic API 返回了空内容，请检查模型名、账号额度或接口响应格式。"
            )
        return {
            "content": content,
            "usage": {
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "cache_read_input_tokens": getattr(
                    usage, "cache_read_input_tokens", 0
                ),
            },
            "stop_reason": response.stop_reason,
            "model": self.model,
            "provider": self.provider,
        }

    @staticmethod
    def _env_text(name: str) -> str:
        import os

        return os.environ.get(name, "").strip()

    @classmethod
    def _env_flag(cls, name: str) -> bool:
        return cls._env_text(name).lower() in {"1", "true", "yes", "on", "enabled"}

    def calculate_cost(self, usage: Dict[str, int]) -> float:
        """Best-effort rough cost placeholder kept for API compatibility."""
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        return (input_tokens + output_tokens) / 1_000_000


_client: Optional[ModelClient] = None
_client_key: Optional[tuple[str, str, str, str]] = None


def get_model_client(
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    provider: Optional[str] = None,
    base_url: Optional[str] = None,
) -> ModelClient:
    """Return a cached model client unless explicit overrides are supplied."""
    global _client, _client_key
    settings = get_settings()
    next_key = (
        provider or settings.provider,
        model or settings.model,
        api_key or settings.api_key,
        base_url or settings.base_url,
    )
    if _client is None or _client_key != next_key:
        _client = ModelClient(
            api_key=api_key,
            model=model,
            provider=provider,
            base_url=base_url,
            settings=settings,
        )
        _client_key = next_key
    return _client


def reset_model_client() -> None:
    global _client, _client_key
    _client = None
    _client_key = None
