from __future__ import annotations

import os

import pytest

from writeflow import config


ENV_KEYS = [
    "WRITEFLOW_PROVIDER",
    "WRITEFLOW_API_KEY",
    "WRITEFLOW_MODEL",
    "WRITEFLOW_BASE_URL",
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_MODEL",
    "DEEPSEEK_BASE_URL",
    "MINIMAX_API_KEY",
    "MINIMAX_MODEL",
    "MINIMAX_BASE_URL",
    "ANTHROPIC_API_KEY",
    "CLAUDE_MODEL",
    "OPENAI_API_KEY",
]


@pytest.fixture(autouse=True)
def clean_settings(monkeypatch):
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    config.reset_settings_cache()
    monkeypatch.setattr(config, "_dotenv_loaded", True)
    yield
    config.reset_settings_cache()


def test_detects_minimax_provider_from_key(monkeypatch):
    monkeypatch.setenv("MINIMAX_API_KEY", "mini-key")

    settings = config.get_settings(refresh=True)

    assert settings.provider == "minimax"
    assert settings.model == "MiniMax-M1"
    assert settings.base_url == "https://api.minimax.chat/v1"
    assert settings.api_key == "mini-key"
    assert config.validate_runtime_settings(settings) == []


def test_placeholder_key_is_treated_as_missing(monkeypatch):
    monkeypatch.setenv("WRITEFLOW_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-your-deepseek-key")

    settings = config.get_settings(refresh=True)

    assert settings.provider == "deepseek"
    assert settings.api_key == ""
    assert any("API Key" in issue for issue in config.validate_runtime_settings(settings))


def test_explicit_openai_compatible_provider_requires_base_url(monkeypatch):
    monkeypatch.setenv("WRITEFLOW_PROVIDER", "openai_compatible")
    monkeypatch.setenv("WRITEFLOW_API_KEY", "generic-key")

    settings = config.get_settings(refresh=True)

    assert settings.provider == "openai_compatible"
    assert settings.api_key == "generic-key"
    assert any("WRITEFLOW_BASE_URL" in issue for issue in config.validate_runtime_settings(settings))


def test_invalid_provider_raises(monkeypatch):
    monkeypatch.setenv("WRITEFLOW_PROVIDER", "unknown")

    with pytest.raises(ValueError, match="WRITEFLOW_PROVIDER"):
        config.get_settings(refresh=True)


def test_load_dotenv_respects_existing_environment(tmp_path, monkeypatch):
    dotenv = tmp_path / ".env"
    dotenv.write_text("MINIMAX_API_KEY=from-file\nWRITEFLOW_PROVIDER=minimax\n", encoding="utf-8")
    monkeypatch.setenv("MINIMAX_API_KEY", "from-env")

    config.load_dotenv(dotenv)

    assert os.environ["MINIMAX_API_KEY"] == "from-env"
    assert os.environ["WRITEFLOW_PROVIDER"] == "minimax"
