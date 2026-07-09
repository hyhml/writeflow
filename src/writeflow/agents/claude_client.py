"""
Backward-compatible import path.

Older agents import get_claude_client from this module. The implementation now
returns the provider selected by WRITEFLOW_PROVIDER, so DeepSeek and MiniMax work
without changing every agent file.
"""
from __future__ import annotations

from typing import Optional

from writeflow.agents.llm_client import ModelClient, get_model_client


ClaudeClient = ModelClient


def get_claude_client(
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    provider: Optional[str] = None,
) -> ModelClient:
    return get_model_client(api_key=api_key, model=model, provider=provider)
