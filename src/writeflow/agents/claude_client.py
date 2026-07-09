"""
Claude API客户端

API Key从环境变量读取，无需额外配置。
Claude Code运行时ANTHROPIC_API_KEY已存在，子进程自动继承。
"""
import os
from typing import Optional, List, Dict, Any

import anthropic
from anthropic.types import Message


class ClaudeClient:
    """Claude API客户端"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ):
        # 优先使用传入的api_key，其次环境变量
        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.client = anthropic.Anthropic(
            api_key=key,
            max_retries=3,
            timeout=120.0,
        )
        self.model = model or os.environ.get("CLAUDE_MODEL", "claude-opus-4-8")
        self.max_tokens = int(os.environ.get("CLAUDE_MAX_TOKENS", "8192"))
        self.temperature = float(os.environ.get("CLAUDE_TEMPERATURE", "0.7"))

    async def generate(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> Dict[str, Any]:
        """生成响应"""
        params = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens or self.max_tokens,
            "temperature": temperature or self.temperature,
        }

        if system_prompt:
            params["system"] = system_prompt

        response: Message = self.client.messages.create(**params)

        return {
            "content": response.content[0].text,
            "usage": {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "cache_read_input_tokens": getattr(
                    response.usage, "cache_read_input_tokens", 0
                ),
            },
            "stop_reason": response.stop_reason,
        }

    def calculate_cost(self, usage: Dict[str, int]) -> float:
        """计算API调用成本"""
        input_cost_per_m = 5.0
        output_cost_per_m = 25.0
        cache_savings = 0.5

        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        cache_read = usage.get("cache_read_input_tokens", 0)

        cost = (
            input_tokens * input_cost_per_m / 1_000_000
            + output_tokens * output_cost_per_m / 1_000_000
            - cache_read * cache_savings / 1_000_000
        )

        return max(0, cost)


_claude_client: Optional[ClaudeClient] = None
_api_key_override: Optional[str] = None


def get_claude_client(api_key: Optional[str] = None) -> ClaudeClient:
    """获取Claude客户端单例"""
    global _claude_client, _api_key_override
    if api_key is not None:
        _api_key_override = api_key
    if _claude_client is None or _api_key_override is not None:
        _claude_client = ClaudeClient(api_key=_api_key_override)
        _api_key_override = None
    return _claude_client
