#!/usr/bin/env python3
"""
WriteFlow命令行入口

用法:
    python write.py <主题> [-o <输出路径>]

示例:
    python write.py 技术进步与社会不平等
    python write.py "全球化与民族国家的矛盾" -o
    python write.py "全球化与民族国家的矛盾" --output outputs/custom.md
"""
import argparse
import asyncio
import json
import re
import sys
import os
from datetime import datetime

# 添加src到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from writeflow import WriteFlow
from writeflow.config import get_settings


def slugify(text: str, max_len: int = 40) -> str:
    """将中文主题转换为安全的文件名片段"""
    # 保留中文字符和字母数字，其他替换为下划线
    slug = re.sub(r'[^\w一-鿿-]', '_', text).strip('_')
    if len(slug) > max_len:
        slug = slug[:max_len]
    return slug or "article"


def save_output(content: str, scores, passed: bool, pass_reason: str, rounds: int,
                filepath: str) -> str:
    """保存稿件到文件"""
    os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"\n稿件已保存到: {filepath}")
    return filepath


async def main():
    parser = argparse.ArgumentParser(
        description="WriteFlow - 批判性深度稿件多Agent生产系统",
    )
    parser.add_argument(
        "topic",
        nargs='+',
        help="写作主题（支持多词，如: 中考分流制度）",
    )
    parser.add_argument(
        "-o", "--output",
        nargs='?',
        const='__auto__',
        default=None,
        help="保存稿件到文件。不带参数时自动命名到 outputs/ 目录",
        metavar="PATH",
    )

    args = parser.parse_args()

    topic = " ".join(args.topic)
    settings = get_settings()

    if not settings.api_key:
        print("未找到模型 API Key。")
        print("请在 .env 中配置，或在终端 export 对应变量：")
        print("  DeepSeek: WRITEFLOW_PROVIDER=deepseek + DEEPSEEK_API_KEY")
        print("  MiniMax:  WRITEFLOW_PROVIDER=minimax + MINIMAX_API_KEY")
        print("  通用接口: WRITEFLOW_PROVIDER=openai_compatible + WRITEFLOW_API_KEY + WRITEFLOW_BASE_URL")
        sys.exit(1)

    # 确定输出路径
    output_path = None
    if args.output == '__auto__':
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{slugify(topic)}_{timestamp}.md"
        output_path = os.path.join(os.path.dirname(__file__) or '.', 'outputs', filename)
    elif args.output:
        output_path = args.output

    print(f"正在为主题「{topic}」创作批判性文章...")
    print(f"Provider: {settings.provider} | Model: {settings.model}")
    if output_path:
        print(f"输出文件: {output_path}")
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

    # 保存到文件
    if output_path:
        save_output(result.content, scores, result.passed, result.pass_reason,
                    result.rounds, output_path)
        # 同时保存评分 JSON
        json_path = output_path.rsplit('.', 1)[0] + '_scores.json'
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump({
                "topic": topic,
                "pass": result.passed,
                "pass_reason": result.pass_reason,
                "rounds": result.rounds,
                "scores": {
                    "批判锋芒": scores.批判锋芒,
                    "理论深度": scores.理论深度,
                    "洞察力度": scores.洞察力度,
                    "论证严谨性": scores.论证严谨性,
                    "社会关联度": scores.社会关联度,
                    "文字穿透力": scores.文字穿透力,
                    "学术规范性": scores.学术规范性,
                    "total": scores.total(),
                },
            }, f, ensure_ascii=False, indent=2)
        print(f"评分已保存到: {json_path}")


if __name__ == "__main__":
    asyncio.run(main())
