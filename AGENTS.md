# AGENTS.md

Shared instructions for AI coding agents working on WriteFLow.

## What This Project Must Support

- Run in WSL with `python3`.
- Install with `pip install -e .`.
- Select model backend through `.env` or environment variables.
- Support DeepSeek and MiniMax keys without requiring Anthropic credentials.
- Keep Claude Code and Codex workflows compatible through normal Git commands.

## Provider Configuration

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

Generic OpenAI-compatible:

```env
WRITEFLOW_PROVIDER=openai_compatible
WRITEFLOW_API_KEY=...
WRITEFLOW_MODEL=...
WRITEFLOW_BASE_URL=...
```

## Verification

Run at least:

```bash
python3 -m compileall -q write.py src
writeflow start
```

If no real key is available, do not make a live generation call. Verify the
missing-key path with:

```bash
python3 write.py "测试主题"
```

It should fail with a helpful API-key message.

## Git Hygiene

Do not commit:

- `.env`
- `.venv/`
- `__pycache__/`
- generated `.docx` / `.pdf`
- real API keys or tokens
