from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path

from writeflow import config

ROOT = Path(__file__).resolve().parents[1]


def load_write_module():
    spec = importlib.util.spec_from_file_location("write_entry", ROOT / "write.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_write_py_exits_cleanly_without_api_key(monkeypatch, capsys):
    monkeypatch.setenv("WRITEFLOW_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-your-deepseek-key")
    monkeypatch.delenv("WRITEFLOW_API_KEY", raising=False)
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(sys, "argv", ["write.py", "测试主题"])
    config.reset_settings_cache()
    monkeypatch.setattr(config, "_dotenv_loaded", True)

    module = load_write_module()
    exit_code = asyncio.run(module.main())
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "API Key" in output
