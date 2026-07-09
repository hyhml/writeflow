"""
Configuration for WriteFLow.

The project can run under Claude Code, Codex, or a normal terminal. The coding
agent starts the process, but model credentials come from environment variables
or a local .env file.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


SUPPORTED_PROVIDERS = {"deepseek", "minimax", "anthropic", "openai_compatible"}

DEFAULT_MODELS = {
    "deepseek": "deepseek-v4-pro",
    "minimax": "MiniMax-M1",
    "anthropic": "claude-sonnet-4-5",
    "openai_compatible": "gpt-4o-mini",
}

DEFAULT_BASE_URLS = {
    "deepseek": "https://api.deepseek.com",
    "minimax": "https://api.minimax.chat/v1",
    "openai_compatible": "",
}

PLACEHOLDER_KEYS = {
    "sk-your-deepseek-key",
    "your-minimax-key",
    "your-api-key",
    "sk-ant-your-key",
    "sk-ant-xxxxx",
}


@dataclass(frozen=True)
class Settings:
    """Runtime settings loaded from environment variables and .env."""

    app_env: str
    provider: str
    model: str
    api_key: str
    base_url: str
    max_tokens: int
    temperature: float
    request_timeout: float
    max_retries: int
    max_rounds: int
    min_rounds: int
    quality_threshold_excellent: float
    quality_threshold_pass: float
    quality_threshold_reject: float
    quality_total_threshold: float
    quality_developed_protection: float

    @property
    def claude_model(self) -> str:
        """Backward-compatible alias used by older CLI code."""
        return self.model


_settings: Optional[Settings] = None
_dotenv_loaded = False


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _strip_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def load_dotenv(path: Optional[Path] = None, override: bool = False) -> None:
    """
    Load simple KEY=VALUE lines from a .env file without extra dependencies.

    Existing process environment variables win by default, so secrets exported
    by the shell or an agent are not overwritten by local files.
    """
    dotenv_path = path or (Path.cwd() / ".env")
    if not dotenv_path.exists():
        return

    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        if key in os.environ and not override:
            continue
        os.environ[key] = _strip_quotes(value)


def ensure_dotenv_loaded() -> None:
    global _dotenv_loaded
    if _dotenv_loaded:
        return

    # Load the project .env first, then the current working directory .env.
    # This covers both `python write.py` from the repo and installed commands.
    load_dotenv(_project_root() / ".env")
    cwd_env = Path.cwd() / ".env"
    if cwd_env != _project_root() / ".env":
        load_dotenv(cwd_env)

    _dotenv_loaded = True


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _env_int(name: str, default: int) -> int:
    value = _env(name)
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    value = _env(name)
    if not value:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _detect_provider() -> str:
    configured = _env("WRITEFLOW_PROVIDER").lower()
    if configured:
        if configured not in SUPPORTED_PROVIDERS:
            raise ValueError(
                "WRITEFLOW_PROVIDER must be one of: "
                + ", ".join(sorted(SUPPORTED_PROVIDERS))
            )
        return configured

    if _env("DEEPSEEK_API_KEY"):
        return "deepseek"
    if _env("MINIMAX_API_KEY"):
        return "minimax"
    if _env("ANTHROPIC_API_KEY"):
        return "anthropic"
    return "deepseek"


def _provider_key(provider: str) -> str:
    explicit = _env("WRITEFLOW_API_KEY")
    if explicit:
        return _normalize_secret(explicit)

    if provider == "deepseek":
        return _normalize_secret(_env("DEEPSEEK_API_KEY"))
    if provider == "minimax":
        return _normalize_secret(_env("MINIMAX_API_KEY"))
    if provider == "anthropic":
        return _normalize_secret(_env("ANTHROPIC_API_KEY"))
    return _normalize_secret(_env("OPENAI_API_KEY"))


def _normalize_secret(value: str) -> str:
    if value.strip().lower() in PLACEHOLDER_KEYS:
        return ""
    return value


def _provider_model(provider: str) -> str:
    model = _env("WRITEFLOW_MODEL") or _env(f"{provider.upper()}_MODEL")
    if model:
        return model
    if provider == "anthropic" and _env("CLAUDE_MODEL"):
        return _env("CLAUDE_MODEL")
    return DEFAULT_MODELS[provider]


def _provider_base_url(provider: str) -> str:
    return (
        _env("WRITEFLOW_BASE_URL")
        or _env(f"{provider.upper()}_BASE_URL")
        or DEFAULT_BASE_URLS.get(provider, "")
    ).rstrip("/")


def get_settings(refresh: bool = False) -> Settings:
    """Return cached runtime settings."""
    global _settings
    if _settings is not None and not refresh:
        return _settings

    ensure_dotenv_loaded()
    provider = _detect_provider()

    _settings = Settings(
        app_env=_env("WRITEFLOW_ENV", _env("APP_ENV", "development")),
        provider=provider,
        model=_provider_model(provider),
        api_key=_provider_key(provider),
        base_url=_provider_base_url(provider),
        max_tokens=_env_int("WRITEFLOW_MAX_TOKENS", _env_int("CLAUDE_MAX_TOKENS", 8192)),
        temperature=_env_float(
            "WRITEFLOW_TEMPERATURE", _env_float("CLAUDE_TEMPERATURE", 0.7)
        ),
        request_timeout=_env_float("WRITEFLOW_TIMEOUT", 120.0),
        max_retries=_env_int("WRITEFLOW_MAX_RETRIES", 3),
        max_rounds=_env_int("MAX_ROUND", _env_int("WRITEFLOW_MAX_ROUNDS", 5)),
        min_rounds=_env_int("MIN_ROUND", _env_int("WRITEFLOW_MIN_ROUNDS", 2)),
        quality_threshold_excellent=_env_float("QUALITY_THRESHOLD_EXCELLENT", 8.0),
        quality_threshold_pass=_env_float("QUALITY_THRESHOLD_PASS", 4.5),
        quality_threshold_reject=_env_float("QUALITY_THRESHOLD_REJECT", 4.0),
        quality_total_threshold=_env_float("QUALITY_TOTAL_THRESHOLD", 56.0),
        quality_developed_protection=_env_float(
            "QUALITY_DEVELOPED_PROTECTION", 6.0
        ),
    )
    return _settings


def reset_settings_cache() -> None:
    """Test helper for reloading environment changes."""
    global _settings, _dotenv_loaded
    _settings = None
    _dotenv_loaded = False


def get_api_key() -> str:
    return get_settings().api_key


def get_model() -> str:
    return get_settings().model


def get_provider() -> str:
    return get_settings().provider


def get_base_url() -> str:
    return get_settings().base_url


def get_max_tokens() -> int:
    return get_settings().max_tokens


def get_temperature() -> float:
    return get_settings().temperature
