"""
CLI入口
"""
import asyncio
import sys
from typing import Optional

from writeflow import __version__
from writeflow.config import get_settings
from writeflow.core.orchestrator import Orchestrator


async def main():
    """CLI主入口"""
    args = sys.argv[1:]

    if not args:
        print_help()
        return

    command = args[0]

    if command in ["--help", "-h"]:
        print_help()
        return

    if command == "--version":
        print(f"writeflow {__version__}")
        return

    if command == "start":
        await cmd_start(args[1:])
    elif command == "submit":
        await cmd_submit(args[1:])
    elif command == "status":
        await cmd_status(args[1:])
    elif command == "list":
        await cmd_list(args[1:])
    else:
        print(f"Unknown command: {command}")
        print_help()
        return 1

    return 0


def print_help():
    """打印帮助"""
    print(f"""
WriteFLow - 批判性深度稿件多Agent生产系统

用法: writeflow <命令> [选项]

命令:
  start               启动后台服务
  submit <主题>        提交一个新任务
  status <任务ID>     查看任务状态
  list                列出所有任务

示例:
  writeflow submit "当代资本主义的结构性矛盾"
  writeflow status abc123-def456

更多帮助: writeflow --help
""")


async def cmd_start(args):
    """启动服务"""
    print("启动WriteFLow服务...")
    settings = get_settings()
    print(f"配置: {settings.app_env}")
    print(f"模型: {settings.claude_model}")
    print("服务已启动（后台运行）")
    print("使用 'writeflow submit <主题>' 提交任务")


async def cmd_submit(args):
    """提交任务"""
    if not args:
        print("错误: 需要提供主题")
        print("用法: writeflow submit <主题>")
        return 1

    topic = " ".join(args)
    print(f"提交任务: {topic}")

    orchestrator = Orchestrator()
    task_id = await orchestrator.submit_task(topic)

    print(f"任务已提交: {task_id}")
    print(f"使用 'writeflow status {task_id}' 查看状态")

    # 开始处理
    print("开始处理...")
    result = await orchestrator.process_task(task_id)

    if result["status"] == "completed":
        print(f"\n✅ 任务完成!")
        print(f"质量评分: {result['quality_scores']}")
        print(f"Gate结果: {result['gate_result']['passed']}")
        print(f"\n最终内容 ({len(result['final_content'])} 字符):")
        print("-" * 60)
        print(result["final_content"][:1000])
        if len(result["final_content"]) > 1000:
            print("... (省略)")
    else:
        print(f"\n❌ 任务失败: {result.get('error', '未知错误')}")


async def cmd_status(args):
    """查看状态"""
    if not args:
        print("错误: 需要提供任务ID")
        return 1

    task_id = args[0]
    print(f"查看任务状态: {task_id}")
    print("(需要后台服务运行才能获取实时状态)")


async def cmd_list(args):
    """列出任务"""
    print("任务列表:")
    print("(需要后台服务运行才能获取实时列表)")


def cli_main():
    """CLI入口点"""
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code or 0)
    except KeyboardInterrupt:
        print("\n已取消")
        sys.exit(0)
    except Exception as e:
        print(f"错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    cli_main()
