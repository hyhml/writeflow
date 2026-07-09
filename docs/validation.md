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
