"""Installed CLI entry point for WriteFLow."""
from __future__ import annotations

import asyncio
import argparse
import sys
from pathlib import Path

from writeflow import __version__
from writeflow.agents.llm_client import ModelClientError
from writeflow.config import get_settings, validate_runtime_settings
from writeflow.progress import ProgressReporter
from writeflow.writeflow import WriteFlow


def print_help() -> None:
    print(
        """
WriteFLow - 批判性深度稿件多 Agent 生产系统

用法: writeflow <命令> [选项]

命令:
  start               检查当前运行配置
  submit <主题>        立即生成一个新稿件
  web                 启动本地 Web 工作台
  status <任务ID>      查看任务状态
  list                列出所有任务

示例:
  writeflow start
  writeflow submit "当代资本主义的结构性矛盾"
  writeflow submit "深圳电动车治理" --observation "我看到的本地反常现象..." --live
  writeflow web --port 8765
  writeflow status abc123-def456

更多帮助: writeflow --help
""".strip()
    )


async def main() -> int:
    args = sys.argv[1:]

    if not args or args[0] in {"--help", "-h"}:
        print_help()
        return 0

    command = args[0]
    if command == "--version":
        print(f"writeflow {__version__}")
        return 0

    try:
        if command == "start":
            return await cmd_start(args[1:])
        if command == "submit":
            return await cmd_submit(args[1:])
        if command == "web":
            return await cmd_web(args[1:])
        if command == "status":
            return await cmd_status(args[1:])
        if command == "list":
            return await cmd_list(args[1:])
    except ValueError as exc:
        print(f"配置错误: {exc}")
        return 1
    except ModelClientError as exc:
        print(f"模型调用失败: {exc}")
        return 1

    print(f"Unknown command: {command}")
    print_help()
    return 1


async def cmd_start(args: list[str]) -> int:
    """Print runtime configuration status."""

    settings = get_settings()
    issues = validate_runtime_settings(settings)

    print("WriteFLow 配置检查")
    print("-" * 40)
    print(f"环境: {settings.app_env}")
    print(f"Provider: {settings.provider}")
    print(f"模型: {settings.model}")
    print(f"Base URL: {settings.base_url or '(provider default)'}")
    print(f"API Key: {'已设置' if settings.api_key else '未设置'}")
    print(f"最大轮次: {settings.max_rounds}")

    if issues:
        print("\n需要处理的问题:")
        for issue in issues:
            print(f"  - {issue}")
        print("\n配置完成后可运行: writeflow submit <主题>")
    else:
        print("\n配置可用。可以运行: writeflow submit <主题>")

    return 0


async def cmd_submit(args: list[str]) -> int:
    """Submit and process one local writing task."""

    if not args:
        print("错误: 需要提供主题")
        print("用法: writeflow submit <主题> [--observation 文本] [--observation-file path.txt]")
        return 1

    parser = argparse.ArgumentParser(prog="writeflow submit")
    parser.add_argument("topic", nargs="+")
    parser.add_argument("--observation", default="")
    parser.add_argument("--observation-file", default="")
    parser.add_argument("--live", action="store_true")
    parsed = parser.parse_args(args)

    settings = get_settings()
    issues = validate_runtime_settings(settings)
    if issues:
        print("配置未完成，无法生成稿件:")
        for issue in issues:
            print(f"  - {issue}")
        print("可以先执行 `writeflow start` 查看当前配置。")
        return 1

    try:
        human_observation = _read_observation_input(
            parsed.observation,
            parsed.observation_file,
        )
    except OSError as exc:
        print(f"观察文件读取失败: {exc}")
        return 1

    topic = " ".join(parsed.topic)
    print(f"提交任务: {topic}")
    print(f"Provider: {settings.provider} | Model: {settings.model}")

    wf = WriteFlow()
    result = await wf.write(
        topic,
        context={"human_observation": human_observation},
        progress_callback=ProgressReporter(live=True) if parsed.live else None,
    )

    print("\n任务完成!")
    print(f"判浅评分: {result.scores.to_dict()}")
    print(f"Gate 结果: {result.passed}")
    print(f"原因: {result.pass_reason}")
    print(f"\n最终内容 ({len(result.content)} 字符):")
    print("-" * 60)
    print(result.content[:1000])
    if len(result.content) > 1000:
        print("... (省略)")
    return 0


async def cmd_web(args: list[str]) -> int:
    """Start the built-in local web UI."""

    parser = argparse.ArgumentParser(prog="writeflow web")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8765, type=int)
    parsed = parser.parse_args(args)

    from writeflow.web import serve

    serve(host=parsed.host, port=parsed.port)
    return 0


async def cmd_status(args: list[str]) -> int:
    if not args:
        print("错误: 需要提供任务 ID")
        return 1

    task_id = args[0]
    print(f"查看任务状态: {task_id}")
    print("(当前版本为本地同步执行模式，尚未启用后台队列。)")
    return 0


async def cmd_list(args: list[str]) -> int:
    print("任务列表:")
    print("(当前版本为本地同步执行模式，尚未启用后台队列。)")
    return 0


def cli_main() -> None:
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("\n已取消。")
        sys.exit(130)
    except Exception as exc:
        print(f"错误: {exc}")
        sys.exit(1)


def _read_observation_input(observation: str = "", observation_file: str = "") -> str:
    if observation_file:
        return Path(observation_file).read_text(encoding="utf-8").strip()
    return observation.strip()


if __name__ == "__main__":
    cli_main()
