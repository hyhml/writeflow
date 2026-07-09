# CLAUDE.md - Claude Code调用指南

## 入口

```
D:/AI_Assist/WriteFLow/
├── write.py              # 命令行入口
└── src/writeflow/
    └── writeflow.py      # Python API入口
```

## 调用方式

### 方式1：命令行（推荐）

```bash
cd D:/AI_Assist/WriteFLow
python write.py "写作主题"
```

**无需配置API Key** - Claude Code运行时已继承API凭证。

### 方式2：Python API

```python
import asyncio
import sys
sys.path.insert(0, 'src')
from writeflow import WriteFlow

async def main():
    wf = WriteFlow()
    result = await wf.write("技术进步与社会不平等")
    print(result.content)
    print(result.passed)

asyncio.run(main())
```

## write.py 接口

位置：`D:/AI_Assist/WriteFLow/write.py`

```
python write.py <主题> [主题2] [主题3]
```

**参数**：
- 主题（必须）：字符串，用引号包裹
- 最多3个主题（批量）

**返回**：
- 稿件内容
- 7维质量评分
- 质量Gate结果

## Python API

### WriteFlow.write(topic: str) -> WriteResult

**参数**：
- `topic`: str，写作主题

**返回**：WriteResult对象

**WriteResult属性**：
```python
result.content        # str，最终稿件
result.scores        # QualityScores，7维评分
result.passed        # bool，是否通过Gate
result.pass_reason   # str，通过/拒绝原因
result.rounds        # int，讨论轮次
```

### QualityScores

```python
scores.批判锋芒     # float 0-10
scores.理论深度     # float 0-10
scores.洞察力度     # float 0-10
scores.论证严谨性    # float 0-10
scores.社会关联度    # float 0-10
scores.文字穿透力    # float 0-10
scores.学术规范性    # float 0-10
scores.total()       # float，总分
```

### 质量Gate规则

**通过条件（满足任一）**：
- 至少2个维度≥8分
- 总分≥56
- 5个维度全部≥6分

**拒绝条件**：
- 任何维度<4分

## 示例对话

**用户**："写一篇关于技术进步与社会不平等的文章"

**Claude Code执行**：
```bash
cd D:/AI_Assist/WriteFLow
python write.py "技术进步与社会不平等"
```

**Claude Code展示结果**：
- 展示稿件内容
- 展示质量评分
- 告知是否通过质量Gate
