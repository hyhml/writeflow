# CLAUDE.md

This file is for Claude Code sessions working on WriteFLow.

## Project Goal

WriteFLow is a local Python multi-agent writing workflow. It should run in WSL
and support model providers through environment variables:

- `deepseek`
- `minimax`
- `anthropic`
- `openai_compatible`

Do not assume Claude Code credentials are inherited by Python subprocesses. The
Python app needs `.env` or exported environment variables.

## First Commands

```bash
git status
python3 --version
python3 -m compileall -q write.py src
```

If dependencies are needed:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install -e .
```

## Runtime Checks

```bash
writeflow start
python3 write.py "测试主题"
```

If no API key is configured, `write.py` should fail fast with a helpful message.
That is expected and should not be treated as a code failure.

## Environment

Use `.env.example` as the template. Never commit `.env`.

DeepSeek:

```env
WRITEFLOW_PROVIDER=deepseek
DEEPSEEK_API_KEY=...
DEEPSEEK_MODEL=deepseek-v4-pro
```

MiniMax:

```env
WRITEFLOW_PROVIDER=minimax
MINIMAX_API_KEY=...
MINIMAX_MODEL=MiniMax-M1
```

## Git Rules

- Start with `git status` and, when network is available, `git pull`.
- Do not commit `.env`, `.venv`, `__pycache__`, generated outputs, or API keys.
- Keep commits focused and named clearly.
- Run `python3 -m compileall -q write.py src` before committing.

Suggested commit style:

```bash
git add .
git commit -m "v0.2 support deepseek and minimax providers"
```
