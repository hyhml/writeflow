# WriteFLow

WriteFLow 是一个本地运行的多 Agent 深度稿件生成工具。它把一个写作主题交给多个 Agent 协作处理：素材整理、初稿写作、反方质疑、质量评分、最终编辑。

当前版本支持以下模型后端：

- DeepSeek：OpenAI-compatible API，默认模型 `deepseek-v4-pro`
- MiniMax：OpenAI-compatible API，默认模型 `MiniMax-M1`
- Anthropic：可选，需要额外安装 `.[anthropic]`
- 其他 OpenAI-compatible 服务：通过 `WRITEFLOW_BASE_URL` 自定义

> Claude Code 和 Codex 都可以用来开发这个项目。项目运行本身不依赖某个代码助手，而是依赖 `.env` 里的模型 API Key。

## WSL 快速开始

推荐在 WSL 的 Linux 文件系统中开发：

```bash
mkdir -p ~/projects
cd ~/projects
git clone https://github.com/hyhml/writeflow.git WriteFLow
cd WriteFLow
```

创建虚拟环境并安装：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install -e .
```

复制配置文件：

```bash
cp .env.example .env
nano .env
```

检查配置：

```bash
writeflow start
```

运行：

```bash
python3 write.py "技术进步与社会不平等"
```

也可以使用安装后的命令：

```bash
writeflow submit "技术进步与社会不平等"
```

## DeepSeek 配置

在 `.env` 中填入：

```env
WRITEFLOW_PROVIDER=deepseek
DEEPSEEK_API_KEY=你的DeepSeek密钥
DEEPSEEK_MODEL=deepseek-v4-pro
DEEPSEEK_BASE_URL=https://api.deepseek.com
```

## MiniMax 配置

在 `.env` 中填入：

```env
WRITEFLOW_PROVIDER=minimax
MINIMAX_API_KEY=你的MiniMax密钥
MINIMAX_MODEL=MiniMax-M1
MINIMAX_BASE_URL=https://api.minimax.chat/v1
```

如果你的 MiniMax 控制台给了不同模型名或 base URL，以控制台为准，改 `MINIMAX_MODEL` 或 `MINIMAX_BASE_URL` 即可。

## 通用 OpenAI-compatible 配置

```env
WRITEFLOW_PROVIDER=openai_compatible
WRITEFLOW_API_KEY=你的API密钥
WRITEFLOW_MODEL=你的模型名
WRITEFLOW_BASE_URL=https://your-provider.example/v1
```

## Claude Code 启动开发

在 WSL 项目目录中运行：

```bash
cd ~/projects/WriteFLow
source .venv/bin/activate
claude
```

建议给 Claude Code 的开场指令：

```text
先 git status 和 git pull。修改前不要提交 .env、.venv、__pycache__。完成后运行 python3 -m compileall -q write.py src，并给出清晰 commit message。
```

## Codex 启动开发

用 Codex 打开本仓库目录，或在 Codex CLI/桌面环境中选择这个项目作为工作区。进入后同样遵守：

```bash
git status
git pull
python3 -m compileall -q write.py src
```

两个 AI 共同开发时，把 GitHub 当作唯一同步中心：

```bash
git pull
# 修改代码
git add .
git commit -m "v0.2 support deepseek and minimax providers"
git push
```

## 当前功能

- 5 个 Agent：Researcher、Writer、Devil Advocate、Judge、Editor
- 多轮写作与质疑流程
- 7 维质量评分与 Quality Gate
- `.env` 配置读取
- DeepSeek / MiniMax / Anthropic / 通用 OpenAI-compatible 后端选择
- WSL 下可安装、可导入、可通过 CLI 检查配置

## 当前限制

- Researcher 目前是让模型整理素材，不是真正联网检索。
- 尚未支持读取 PDF、Word、TXT 用户资料。
- 尚未支持导出 `.docx` 或 `.pdf`，当前主要输出到终端。
- 后台队列相关代码仍是预留能力，默认运行路径是本地同步执行。
- 不要把真实 `.env` 或 API Key 提交到 GitHub。

## 版本管理

推荐每个可用阶段打一个 tag：

```bash
git tag v0.2
git push origin v0.2
```

如果某次更新不好，优先用安全回退：

```bash
git log --oneline
git revert 提交ID
git push
```
