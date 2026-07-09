#!/usr/bin/env python3
"""
WriteFlow命令行入口

用法:
    python write.py <主题>

示例:
    python write.py 技术进步与社会不平等
    python write.py "全球化与民族国家的矛盾"
"""
import asyncio
import sys
import os

# 添加src到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from writeflow import WriteFlow
from writeflow.config import get_settings


async def main():
    if len(sys.argv) < 2:
        print("用法: python write.py <主题>")
        print("示例: python write.py 技术进步与社会不平等")
        sys.exit(1)

    topic = " ".join(sys.argv[1:])
    settings = get_settings()

    if not settings.api_key:
        print("未找到模型 API Key。")
        print("请在 .env 中配置，或在终端 export 对应变量：")
        print("  DeepSeek: WRITEFLOW_PROVIDER=deepseek + DEEPSEEK_API_KEY")
        print("  MiniMax:  WRITEFLOW_PROVIDER=minimax + MINIMAX_API_KEY")
        print("  通用接口: WRITEFLOW_PROVIDER=openai_compatible + WRITEFLOW_API_KEY + WRITEFLOW_BASE_URL")
        sys.exit(1)

    print(f"正在为主题「{topic}」创作批判性文章...")
    print(f"Provider: {settings.provider} | Model: {settings.model}")
    print("-" * 50)

    wf = WriteFlow()
    result = await wf.write(topic)

    print("\n=== 稿件内容 ===\n")
    print(result.content)

    print("\n=== 7维质量评分 ===\n")
    scores = result.scores
    print(f"批判锋芒: {scores.批判锋芒}")
    print(f"理论深度: {scores.理论深度}")
    print(f"洞察力度: {scores.洞察力度}")
    print(f"论证严谨性: {scores.论证严谨性}")
    print(f"社会关联度: {scores.社会关联度}")
    print(f"文字穿透力: {scores.文字穿透力}")
    print(f"学术规范性: {scores.学术规范性}")
    print(f"\n总分: {scores.total()}")

    print(f"\n=== 质量Gate ===")
    print(f"通过: {result.passed}")
    print(f"原因: {result.pass_reason}")

    print(f"\n=== 讨论轮次 ===")
    print(f"轮数: {result.rounds}")


if __name__ == "__main__":
    asyncio.run(main())
