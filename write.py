#!/usr/bin/env python3
"""Command-line entry point for generating one WriteFLow article."""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from writeflow import WriteFlow
from writeflow.agents.llm_client import ModelClientError
from writeflow.config import get_settings, validate_runtime_settings
from writeflow.output import (
    AUTO_OUTPUT,
    build_output_paths,
    save_article,
    save_scores,
    save_trace,
    slugify_topic,
)


def slugify(text: str, max_len: int = 40) -> str:
    """Backward-compatible wrapper for older scripts/tests."""

    return slugify_topic(text, max_len=max_len)


def save_output(
    content: str,
    scores,
    passed: bool,
    pass_reason: str,
    rounds: int,
    filepath: str,
) -> str:
    """Backward-compatible wrapper for saving article text."""

    saved_path = save_article(filepath, content)
    print(f"\n稿件已保存到: {saved_path}")
    return str(saved_path)


def print_missing_key_help() -> None:
    print("未找到模型 API Key。")
    print("请在 .env 中配置，或在终端 export 对应变量：")
    print("  DeepSeek: WRITEFLOW_PROVIDER=deepseek + DEEPSEEK_API_KEY")
    print("  MiniMax:  WRITEFLOW_PROVIDER=minimax + MINIMAX_API_KEY")
    print("  Anthropic: WRITEFLOW_PROVIDER=anthropic + ANTHROPIC_API_KEY")
    print("  通用接口: WRITEFLOW_PROVIDER=openai_compatible + WRITEFLOW_API_KEY + WRITEFLOW_BASE_URL")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="WriteFlow - 批判性深度稿件多 Agent 生产系统",
    )
    parser.add_argument(
        "topic",
        nargs="+",
        help="写作主题，支持多个词，例如：中考分流制度",
    )
    parser.add_argument(
        "-o",
        "--output",
        nargs="?",
        const=AUTO_OUTPUT,
        default=None,
        help="保存稿件到文件。不带路径时自动命名到 outputs/ 目录",
        metavar="PATH",
    )
    parser.add_argument(
        "--observation",
        default="",
        help="直接提供人的本地观察、直觉问题和具体方案",
    )
    parser.add_argument(
        "--observation-file",
        default="",
        help="从文本文件读取人的观察",
        metavar="PATH",
    )
    return parser


def print_scores(scores) -> None:
    score_data = scores.to_dict() if hasattr(scores, "to_dict") else dict(scores)
    for name, value in score_data.items():
        print(f"{name}: {value}")
    total = scores.total() if hasattr(scores, "total") else sum(score_data.values())
    print(f"\n总分: {total}")


async def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    topic = " ".join(args.topic)
    try:
        human_observation = read_observation_input(
            args.observation,
            args.observation_file,
        )
    except OSError as exc:
        print(f"观察文件读取失败: {exc}")
        return 1

    try:
        settings = get_settings()
    except ValueError as exc:
        print(f"配置错误: {exc}")
        return 1

    issues = validate_runtime_settings(settings)
    if issues:
        if any("API Key" in issue for issue in issues):
            print_missing_key_help()
        else:
            print("配置错误:")
            for issue in issues:
                print(f"  - {issue}")
        return 1

    output_paths = build_output_paths(topic, args.output)
    article_path = output_paths.article
    scores_path = output_paths.scores
    trace_path = output_paths.trace

    print(f"正在为主题《{topic}》创作批判性文章...")
    print(f"Provider: {settings.provider} | Model: {settings.model}")
    if article_path:
        print(f"输出文件: {article_path}")
    print("-" * 50)

    try:
        wf = WriteFlow()
        result = await wf.write(
            topic,
            context={"human_observation": human_observation},
        )
    except ModelClientError as exc:
        print(f"模型调用失败: {exc}")
        return 1
    except ValueError as exc:
        print(f"配置错误: {exc}")
        return 1

    print("\n=== 稿件内容 ===\n")
    print(result.content)

    print("\n=== 4项判浅评分 ===\n")
    print_scores(result.scores)

    print("\n=== 质量 Gate ===")
    print(f"通过: {result.passed}")
    print(f"原因: {result.pass_reason}")

    print("\n=== 讨论轮次 ===")
    print(f"轮数: {result.rounds}")

    if article_path and scores_path and trace_path:
        saved_article = save_article(article_path, result.content)
        saved_scores = save_scores(
            scores_path,
            topic=topic,
            result=result,
            provider=settings.provider,
            model=settings.model,
        )
        saved_trace = save_trace(
            trace_path,
            topic=topic,
            result=result,
            provider=settings.provider,
            model=settings.model,
        )
        print(f"\n稿件已保存到: {saved_article}")
        print(f"评分已保存到: {saved_scores}")
        print(f"Agent 过程已保存到: {saved_trace}")

    return 0


def read_observation_input(observation: str = "", observation_file: str = "") -> str:
    """Read optional human observation from CLI text or a UTF-8 file."""

    if observation_file:
        return Path(observation_file).read_text(encoding="utf-8").strip()
    return observation.strip()


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("\n已取消。")
        sys.exit(130)
