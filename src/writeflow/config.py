"""
配置管理模块

API Key从环境变量读取，Claude Code运行时自动继承。
"""
import os


def get_api_key() -> str:
    """从环境变量获取API Key"""
    return os.environ.get("ANTHROPIC_API_KEY", "")


def get_model() -> str:
    """获取模型名称"""
    return os.environ.get("CLAUDE_MODEL", "claude-opus-4-8")


def get_max_tokens() -> int:
    """获取最大Token数"""
    return int(os.environ.get("CLAUDE_MAX_TOKENS", "8192"))


def get_temperature() -> float:
    """获取温度参数"""
    return float(os.environ.get("CLAUDE_TEMPERATURE", "0.7"))
