# WriteFLow 版本验证记录

## v0.2.1 (2026-07-09)

**环境**：WSL Ubuntu 22.04, Python 3.10.12

**模型提供商**：MiniMax (MiniMax-M1)

**验证命令**：

```bash
python3 write.py "中考分流制度" -o
```

**运行结果**：

| 项目 | 状态 |
|------|------|
| Provider | minimax |
| Model | MiniMax-M1 |
| 讨论轮次 | 1 |
| 质量Gate | ✅ 通过 |

**7维质量评分**：

| 维度 | 分数 |
|------|------|
| 批判锋芒 | 8 |
| 理论深度 | 7 |
| 洞察力度 | 8 |
| 论证严谨性 | 6 |
| 社会关联度 | 8 |
| 文字穿透力 | 7 |
| 学术规范性 | 6 |
| **总分** | **50** |

**Gate 通过原因**：`excellent_dimensions`（至少 2 个维度 ≥ 8 分）

**输出**：`outputs/中考分流制度_*.md` + `outputs/中考分流制度_*_scores.json`

**结论**：v0.2.1 在 WSL 环境下使用 MiniMax API Key 完整运行通过，多 Agent 写作流程和质量 Gate 均正常工作。

## v0.2.2 (2026-07-09)

**环境**：Windows Codex workspace, Python 3.14.6

**目标**：增加自动化测试、统一版本号、加强 CLI/API 错误提示，并加入 GitHub Actions CI。

**验证命令**：

```bash
python -m compileall -q write.py src tests
python -m pytest -q
python write.py "测试主题"
```

**运行结果**：

| 项目 | 状态 |
|------|------|
| 版本号 | 0.2.2 |
| 编译检查 | ✅ 通过 |
| pytest | ✅ 21 passed |
| 无 API Key 场景 | ✅ 返回清晰配置提示 |
| 真实 API 调用 | 未执行，本版本自动化测试全部 mock，不消耗额度 |

**结论**：v0.2.2 已补齐基础测试与 CI 配置，并将导出路径、评分 JSON 保存、模型响应解析等稳定性逻辑纳入自动化验证。

## v0.2.3 (2026-07-09)

**环境**：Windows Codex workspace, Python 3.14.6

**目标**：增加 Agent 工作过程导出，并修复最终稿混入 `<think>`、模型自检结果、编辑说明的问题。

**验证命令**：

```bash
python -m compileall -q write.py src tests
python -m pytest -q
python -m ruff check .
```

**运行结果**：

| 项目 | 状态 |
|------|------|
| 版本号 | 0.2.3 |
| 编译检查 | ✅ 通过 |
| pytest | ✅ 25 passed |
| ruff | ✅ All checks passed |

**新增输出**：

```text
outputs/<主题>_<时间>.md
outputs/<主题>_<时间>_scores.json
outputs/<主题>_<时间>_trace/
```

**结论**：v0.2.3 让最终稿和 Agent 过程分离，最终 `.md` 默认保存清洗后的正文，原始 Editor 输出保存在 `_trace/final_editor_raw.md` 便于排查。

## v0.2.4 (2026-07-09)

**环境**：Windows Codex workspace, Python 3.14.6

**目标**：新增 Thesis Architect，在 Researcher 和 Writer 之间先产出核心判断简报，减少正文泛泛覆盖主题、浅尝辄止的问题。

**验证命令**：
```bash
python -m compileall -q write.py src tests
python -m pytest -q
python -m ruff check .
```

**运行结果**：
| 项目 | 状态 |
|------|------|
| 版本号 | 0.2.4 |
| 编译检查 | ✅ 通过 |
| pytest | ✅ 28 passed |
| ruff | ✅ All checks passed |

**新增流程**：
```text
Researcher -> Thesis Architect -> Writer -> Devil Advocate -> Judge -> Editor
```

**新增 trace 文件**：
```text
outputs/<主题>_<时间>_trace/02_thesis_architect_brief.json
```

**结论**：v0.2.4 已把“先立论再写作”接入主流程，Writer 会围绕 Thesis Architect 产出的 `core_claim` 写正文，trace 中也能查看这一步的完整结构化输出。

## v0.2.5 (2026-07-09)

**环境**：Windows Codex workspace, Python 3.14.6

**目标**：把 Writer 从“完整覆盖主题”的写法改成“围绕一个主轴推进”，要求每个主要层面回答机制、获益者、代价承担者、常见解释的问题和具体例子。

**验证命令**：
```bash
python -m compileall -q write.py src tests
python -m pytest -q
python -m ruff check .
```

**运行结果**：
| 项目 | 状态 |
|------|------|
| 版本号 | 0.2.5 |
| 编译检查 | ✅ 通过 |
| pytest | ✅ 31 passed |
| ruff | ✅ All checks passed |

**结论**：v0.2.5 保持既有 Agent 流程和 trace 输出不变，只强化 Writer 的初稿任务：不再写主题综述，而是围绕 `core_claim` 做少层面、深机制的推进式论证。
