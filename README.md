# WriteFLow

WriteFLow 是一个本地运行的多 Agent 深度稿件生成工具。它把人的观察、真实声音、素材整理、核心判断、真实新意门槛、判浅重写、反方质疑和最终编辑串成一条可追踪的写作流程。

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

启动本地 Web 工作台：

```bash
writeflow web --port 8765
```

打开 `http://127.0.0.1:8765` 后，可以在网页上填写主题、回答 Observation Interview、生成补充追问、启动写作任务，并实时查看工作规划、当前进度、中间 trace 和最终稿。

保存为 Markdown 文件：

```bash
python3 write.py "技术进步与社会不平等" -o
```

提供人的本地观察：

```bash
python3 write.py "深圳电动车治理" -o --observation "我在本地看到的反常现象..."
python3 write.py "深圳电动车治理" -o --observation-file observation.txt
```

交互式观察访谈：
```bash
python3 write.py "中考分流" -o --interview
python3 write.py "深圳电动车治理" -o --interview --live
```

`--interview` 会在正式生成前先在终端里询问反常现象、案例差异、问题根源、具体方案和不可丢失细节，再根据回答追问 2-3 个问题。回答会合并成 `human_observation` 传给 Observation Interviewer。

显示实时进度：

```bash
python3 write.py "中考分流" -o
python3 write.py "中考分流" -o --live
python3 write.py "深圳电动车治理" -o --observation-file observation.txt --live
```

使用 `-o` 保存时会默认显示进度，并在 `outputs/` 下生成 `.md` 稿件、对应的 `_scores.json` 判浅记录和进度状态文件。

从 v0.2.3 开始，使用 `-o` 保存时还会生成同名 `_trace/` 文件夹，用来查看每个 Agent 的工作过程：

```text
outputs/主题_时间.md
outputs/主题_时间_scores.json
outputs/主题_时间_interview.json
outputs/主题_时间_interview.md
outputs/主题_时间_trace/
outputs/主题_时间_status.json
outputs/主题_时间_status.jsonl
```

`_trace/` 中会包含 Observation Interviewer、Local Voice Collector、Researcher 素材、Thesis Architect 核心判断、Real Novelty Gate、Writer 初稿、Judge 初检、Devil Advocate 质疑、Writer 修订、Judge 终检、Editor 原始输出和清洗后的最终稿。

从 v0.2.4 开始，Researcher 和 Writer 之间新增 Thesis Architect。它不会写正文，只输出一份核心判断简报，回答：文章最想证明的一句话是什么、它和普通观点有什么冲突、如果成立会推翻什么常识、最强证据是什么、最危险的反驳是什么。v0.2.8 后，这份简报会保存到 `_trace/04_thesis_architect_brief.json`。

从 v0.2.5 开始，Writer 会采用“主轴推进”写法：少写几个层面，但每个主要层面都要回答机制是什么、谁获益、谁承担代价、常见解释为什么错，以及能否被具体例子证明。

从 v0.2.6 开始，Judge 不再使用旧的 7 维术语化评分。v0.2.8 后，真实新意由 Real Novelty Gate 一票否决；Depth Judge 只保留 4 项判浅标准：概念克制、句子必要性、层次穿透、方案具体性，并额外输出 `depth_questions` 追问真实新意有没有被讲透。

从 v0.2.7 开始，Judge 会驱动重写，而不是只做终局评分：Writer 初稿会先经过 Judge 初检，浅稿直接退回重写；只有通过初检后才进入 Devil Advocate；修订稿还会再经过 Judge 终检，通过后才交给 Editor。

从 v0.2.8 开始，流程前移到人的观察和真实声音：Observation Interviewer 整理用户本地观察；Local Voice Collector 标准化搜索或外部输入的真实声音；Thesis Architect 生成候选 `novelty_assets`；Real Novelty Gate 只认 case、structure、solution 三类真实新意，缺失时会退回 Thesis Architect 重建一次，仍失败则不进入 Writer。

从 v0.2.9 开始，`--live` 会在终端实时显示每个 Agent 的进度，并在使用 `-o` 时保存 `_status.json` 和 `_status.jsonl`。v0.2.10 开始，`-o` 会默认开启进度显示和状态文件。Novelty Gate 第一次失败、退回 Thesis Architect、第二次失败停止等状态都会显示出来；retry trace 也会保存为独立文件，不再覆盖初次结果。

从 v0.2.11 开始，`--interview` 可以在 Claude Code / WSL 终端里进行交互式 Observation Interview。系统会先问人类观察，再把问答保存为 `_interview.json` / `_interview.md`，最后把合并后的观察材料传入正式写作流程。

从 v0.2.12 开始，新增本地 Web 工作台 `writeflow web`，可以在浏览器里查看完整工作规划、实时进度、中间输出和最终稿；同时降低 Depth Judge 默认门槛，四项判浅维度从全部 >= 6 调整为全部 >= 5，`depth_questions` 中的 `not_deep_enough` 改为改进建议，只有 `missing` 会阻断通过。

从 v0.2.13 开始，如果达到最大轮次后仍未通过 Depth Judge，系统会保存评分最高的候选稿，而不是只保留最后一轮稿件；候选稿正文末尾会追加“未通过原因”，列出最高评分、失败阶段、未达标维度、关键追问和修改建议。

从 v0.2.14 开始，Web 工作台的中间输出按轮次、Agent 和 stage 分段显示；每个 Agent 输出后会打开 5 秒人工补充窗口，开始输入后会等待提交。Observation Interviewer 会保留用户原始输入和硬性写作要求，Thesis Architect、Writer、Judge、Devil Advocate 和 Editor 都会读取这些要求，避免第一部分的写作方向被后续 Agent 摘要化后抹掉。

## 开发与测试

v0.2.2 开始，项目包含不依赖真实 API Key 的自动化测试。安装开发依赖后运行：

```bash
pip install -e ".[dev]"
python -m compileall -q write.py src tests
python -m pytest -q
```

这些测试通过 mock 验证配置、输出文件、Quality Gate 和 OpenAI-compatible API 解析逻辑，不会消耗 MiniMax、DeepSeek 或 Anthropic 额度。

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

## 搜索配置

v0.2.8 先提供可 mock 的搜索抽象。默认不开启搜索，也不会编造本地引语：

```env
WRITEFLOW_SEARCH_PROVIDER=none
# TAVILY_API_KEY=
# SERPAPI_API_KEY=
```

你也可以在代码里通过 `WriteFlow.write(topic, context={"search_results": [...]})` 传入已经采集好的搜索结果。

## Claude Code 启动开发

在 WSL 项目目录中运行：

```bash
cd ~/projects/WriteFLow
source .venv/bin/activate
claude
```

建议给 Claude Code 的开场指令：

```text
先 git status 和 git pull。修改前不要提交 .env、.venv、__pycache__。完成后运行 python3 -m compileall -q write.py src tests、python3 -m pytest -q，并给出清晰 commit message。
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

- 9 个 Agent：Observation Interviewer、Local Voice Collector、Researcher、Thesis Architect、Real Novelty Gate、Writer、Devil Advocate、Judge、Editor
- `WriteFlow.write(topic, context={"human_observation": "...", "search_results": [...]})`
- `WriteFlow.write(..., progress_callback=callback)` 实时接收 Agent 进度事件
- `WriteFlow.write(..., trace_callback=callback)` 实时接收 Agent 中间输出
- `writeflow web --port 8765` 启动本地 Web 工作台
- `--observation` / `--observation-file` 输入人的本地观察
- `--interview` 在终端里逐题收集人的观察并生成补充追问
- Web 工作台支持按 Agent/轮次查看中间输出，并在 Agent 输出后插入人工补充
- `-o` 默认显示终端进度并保存 `_status.json` / `_status.jsonl`；`--live` 可在不保存文件时显式显示进度
- Writer 围绕 `core_claim` 主轴推进，避免主题综述式浅层覆盖
- Real Novelty Gate 对 case / structure / solution 三类真实新意做一票否决
- Judge 驱动的多轮重写与质疑流程
- 4 项判浅标准、`depth_questions` 与更宽松的 Quality Gate
- 达到最大轮次仍失败时，保存最高评分候选稿并附失败原因
- `.env` 配置读取
- DeepSeek / MiniMax / Anthropic / 通用 OpenAI-compatible 后端选择
- `python3 write.py "主题" -o` 保存 `.md` 稿件和 `_scores.json` 判浅记录
- Agent 工作过程 `_trace/` 导出，便于查看每一步如何生成
- Novelty Gate retry trace 独立保存，避免覆盖第一次失败原因
- 自动清理最终稿中的 `<think>`、模型自检说明和编辑过程文本
- pytest 自动化测试与 GitHub Actions CI
- WSL 下可安装、可导入、可通过 CLI 检查配置

## 当前限制

- Researcher 目前是让模型整理素材，不是真正联网检索。
- Local Voice Collector 默认不联网；没有搜索配置或外部 `search_results` 时只标记 `not_configured`，不会编造引语。
- 尚未支持读取 PDF、Word、TXT 用户资料。
- 尚未支持导出 `.docx` 或 `.pdf`，当前可输出到终端或保存 `.md`。
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
