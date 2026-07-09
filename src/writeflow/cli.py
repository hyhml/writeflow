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
        return await cmd_start(args[1:])
    elif command == "submit":
        return await cmd_submit(args[1:])
    elif command == "status":
        return await cmd_status(args[1:])
    elif command == "list":
        return await cmd_list(args[1:])
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
  start               检查当前运行配置
  submit <主题>        立即生成一个新稿件
  status <任务ID>     查看任务状态
  list                列出所有任务

示例:
  writeflow start
  writeflow submit "当代资本主义的结构性矛盾"
  writeflow status abc123-def456

更多帮助: writeflow --help
""")


async def cmd_start(args):
    """启动服务"""
    settings = get_settings()
    print("WriteFLow 配置检查")
    print("-" * 40)
    print(f"环境: {settings.app_env}")
    print(f"Provider: {settings.provider}")
    print(f"模型: {settings.model}")
    print(f"Base URL: {settings.base_url or '(provider default)'}")
    print(f"API Key: {'已设置' if settings.api_key else '未设置'}")
    print(f"最大轮次: {settings.max_rounds}")
    print("\n使用 'writeflow submit <主题>' 立即生成稿件。")
    return 0


async def cmd_submit(args):
    """提交任务"""
    if not args:
        print("错误: 需要提供主题")
        print("用法: writeflow submit <主题>")
        return 1

    topic = " ".join(args)
    settings = get_settings()
    if not settings.api_key:
        print("错误: 未找到模型 API Key")
        print("请设置 DEEPSEEK_API_KEY、MINIMAX_API_KEY 或 WRITEFLOW_API_KEY。")
        print("可以先执行 `writeflow start` 查看当前配置。")
        return 1

    print(f"提交任务: {topic}")
    print(f"Provider: {settings.provider} | Model: {settings.model}")

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
    return 0


async def cmd_list(args):
    """列出任务"""
    print("任务列表:")
    print("(当前版本为本地同步执行模式，尚未启用后台队列)")
    return 0


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
