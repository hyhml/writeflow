# CODEX.md

This file is for Codex sessions working on WriteFLow.

## Project Summary

WriteFLow is a Python multi-agent writing workflow. The app is run from a
terminal or an AI coding agent, but model credentials must come from `.env` or
environment variables.

Supported providers:

- `deepseek`
- `minimax`
- `anthropic`
- `openai_compatible`

## Useful Commands

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
writeflow start
python3 write.py "测试主题"
python3 -m compileall -q write.py src tests
python3 -m pytest -q
```

On Windows PowerShell, use:

```powershell
python -m compileall -q write.py src
```

## Safety Rules

- Never commit `.env` or API keys.
- Do not commit `.venv`, `__pycache__`, or generated outputs.
- Before work: `git status`.
- Before pushing shared work: `git pull` when network is available.
- After meaningful work: compile, commit, and push if requested.
