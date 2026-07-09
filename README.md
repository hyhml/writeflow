# WriteFLow - 批判性深度稿件工具

## 一句话说明

WriteFLow帮助完成**意识形态批判，社会揭露、理论分析**类深度稿件的创作。

## 快速开始

```bash
cd D:/AI_Assist/WriteFLow
pip install -e .
python write.py "技术进步与社会不平等"
```

**无需配置API Key** - Claude Code运行时已自动继承API凭证。

## 使用方式

在终端执行：

```bash
python write.py "你的写作主题"
```

## 返回结果

- 稿件内容
- 7维质量评分
- 质量Gate通过/拒绝

## 命令行参数

```bash
python write.py <主题>     # 单篇
python write.py "主题1" "主题2" "主题3"  # 批量（最多3篇）
```

---

**详细API文档见 CLAUDE.md**
