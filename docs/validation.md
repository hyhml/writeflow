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

## v0.2.6 (2026-07-09)

**环境**：Windows Codex workspace, Python 3.14.6

**目标**：替换原有 7 维术语化 Judge 标准，改为 5 项判浅标准：新判断、概念克制、句子必要性、层次穿透、方案具体性。

**验证命令**：
```bash
python -m compileall -q write.py src tests
python -m pytest -q
python -m ruff check .
```

**运行结果**：
| 项目 | 状态 |
|------|------|
| 版本号 | 0.2.6 |
| 编译检查 | ✅ 通过 |
| pytest | ✅ 37 passed |
| ruff | ✅ All checks passed |

**结论**：v0.2.6 不新增 Agent，直接替换原 Judge 和 Quality Gate。任一判浅维度低于 6 分都会失败，不再因为总分高、术语多或个别维度高分而放行。

## v0.2.7 (2026-07-10)

**环境**：Windows Codex workspace, Python 3.14.6

**目标**：调整多 Agent 工作流顺序，让 Depth Judge 驱动重写。Writer 初稿先经过 Judge 初检，浅稿退回重写；通过初检后才进入 Devil Advocate；Writer 修订后再由 Judge 终检，通过后才进入 Editor。

**验证命令**：
```bash
python -m compileall -q write.py src tests
python -m pytest -q
python -m ruff check .
```

**运行结果**：
| 项目 | 状态 |
|------|------|
| 版本号 | 0.2.7 |
| 编译检查 | ✅ 通过 |
| pytest | ✅ 40 passed |
| ruff | ✅ All checks passed |

**新增流程**：
```text
Researcher -> Thesis Architect -> Writer Draft -> Judge Precheck
  -> 浅稿：Writer Rewrite
  -> 通过：Devil Advocate -> Writer Revision -> Judge Final -> Editor
```

**结论**：v0.2.7 不新增 Agent，但把 Judge 从终局评分器改成了重写压力源。主流程不再调用 Writer defense，而是让 Writer 根据 Judge 和 Devil Advocate 的反馈直接修订正文。

## v0.2.8 (2026-07-10)

**环境**：Windows Codex workspace, Python 3.14.6

**目标**：重构上游生产方式，新增人类观察、真实声音和真实新意门槛。Observation Interviewer 整理用户本地观察，Local Voice Collector 标准化真实声音，Thesis Architect 产出候选 `novelty_assets`，Real Novelty Gate 对 case / structure / solution 三类新意做一票否决；Depth Judge 改为 4 项判浅标准，并用 `depth_questions` 追问新意是否被讲透。

**验证命令**：
```bash
python -m compileall -q write.py src tests
python -m pytest -q
python -m ruff check .
```

**运行结果**：
| 项目 | 状态 |
|------|------|
| 版本号 | 0.2.8 |
| 编译检查 | ✅ 通过 |
| pytest | ✅ 51 passed |
| ruff | ✅ All checks passed |

**新增流程**：
```text
Observation Interviewer
-> Local Voice Collector
-> Researcher
-> Thesis Architect
-> Real Novelty Gate
   -> 失败：退回 Thesis Architect 重建一次；仍失败则停止
   -> 通过：Writer Draft
-> Depth Judge Precheck
   -> 失败：Writer Rewrite
   -> 通过：Devil Advocate
-> Writer Revision
-> Depth Judge Final
-> Editor
-> Final Article
```

**新增 trace 文件**：
```text
01_observation_interviewer.json
02_local_voice_collector.json
03_researcher_materials.json
04_thesis_architect_brief.json
05_real_novelty_gate.json
```

**结论**：v0.2.8 把“真实新意”前移到写作前。系统不再期待 AI 凭空发明本地经验；没有用户观察或搜索结果时，trace 会明确标记缺失，不编造直接言论。

## v0.2.9 (2026-07-10)

**环境**：Windows Codex workspace, Python 3.14.6

**目标**：新增 Live Progress 进度显示，让 Claude Code / WSL 运行生成任务时能看到当前 Agent、Novelty Gate 是否退回、Judge 是否打回重写；同时修复 v0.2.8 中 Novelty retry trace 被覆盖的问题。

**验证命令**：
```bash
python -m compileall -q write.py src tests
python -m pytest -q
python -m ruff check .
```

**运行结果**：
| 项目 | 状态 |
|------|------|
| 版本号 | 0.2.9 |
| 编译检查 | ✅ 通过 |
| pytest | ✅ 57 passed |
| ruff | ✅ All checks passed |

**新增用法**：
```bash
python3 write.py "中考分流" -o --live
python3 write.py "深圳电动车治理" -o --observation-file observation.txt --live
```

**新增输出**：
```text
outputs/<主题>_<时间>_status.json
outputs/<主题>_<时间>_status.jsonl
```

**retry trace 修复**：
```text
04_thesis_architect_brief.json
05_real_novelty_gate.json
04_thesis_architect_brief_retry_01.json
05_real_novelty_gate_retry_01.json
```

**结论**：v0.2.9 让长流程运行状态可见，也让 Novelty Gate 退回过程可追踪。第一次失败原因、退回后的 Thesis 和第二次 Gate 结果都会分别保存。

## v0.2.10 (2026-07-10)

**目标**：修复用户运行 `python3 write.py "主题" -o` 时仍看不到进度的问题。`-o` 现在默认开启 live progress，并保存 `_status.json` / `_status.jsonl`；`--live` 仍可用于不保存文件时显式显示进度。

**验证命令**：
```bash
python -m compileall -q write.py src tests
python -m pytest -q
python -m ruff check .
```

**运行结果**：
| 项目 | 状态 |
|------|------|
| 版本号 | 0.2.10 |
| 编译检查 | ✅ 通过 |
| pytest | ✅ 57 passed |
| ruff | ✅ All checks passed |

**结论**：`python3 write.py "中考分流" -o` 不再需要额外加 `--live`，即可打印进度并写入状态文件。

## v0.2.11 (2026-07-11)

**目标**：新增 `--interview` 交互式 Observation Interview，让 Claude Code / WSL 终端可以在正式生成前先向用户询问本地观察，再根据回答生成 2-3 个补充追问，并把合并后的观察材料传入 `WriteFlow.write(context={"human_observation": ...})`。

**验证命令**：
```bash
python -m compileall -q write.py src tests
python -m pytest -q
python -m ruff check .
```

**运行结果**：
| 项目 | 状态 |
|------|------|
| 版本号 | 0.2.11 |
| 编译检查 | 通过 |
| pytest | 64 passed |
| ruff | All checks passed |

**新增用法**：
```bash
python3 write.py "中考分流" -o --interview
python3 write.py "深圳电动车治理" -o --interview --live
```

**新增输出**：
```text
outputs/<主题>_<时间>_interview.json
outputs/<主题>_<时间>_interview.md
```

**结论**：v0.2.11 只改输入界面层，不改 Depth Judge 或 Writer loop。`--interview` 会先收集人类观察，全部空答时停止生成，避免在缺少观察材料时继续空转。
