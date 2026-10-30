"""S1-02：同一个进程内的多轮对话，支持查看和清空上下文。"""

import argparse
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv
from openai import APIConnectionError, APIStatusError, APITimeoutError

from .cli import STATUS_HINTS
from .config import Settings
from .conversation import Conversation
from .langchain_api import create_model


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="S1-02：消息、上下文与有限轮次多轮对话")
    parser.add_argument("--keep-turns", type=int, default=3, help="保留最近多少轮成功对话，默认 3")
    args = parser.parse_args(argv)
    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
    try:
        conversation = Conversation(args.keep_turns)
        settings = Settings.from_env()
    except ValueError as exc:
        print(f"配置错误：{exc}", file=sys.stderr)
        return 1
    print("输入问题开始对话；/history 查看当前上下文，/reset 清空，/exit 退出。")
    print(f"仅在本进程保留最近 {args.keep_turns} 轮成功对话；不写入磁盘。")
    with httpx.Client(timeout=settings.timeout) as client:
        model = create_model(settings, client)
        while True:
            try:
                question = input("你 > ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n会话结束。")
                return 0
            if question == "/exit":
                return 0
            if question == "/reset":
                conversation.reset()
                print("已清空对话，保留 system 指令。")
                continue
            if question == "/history":
                for item in conversation.messages:
                    print(f"[{item['role']}] {item['content']}")
                continue
            try:
                reply = conversation.turn(question, model)
            except APIStatusError as exc:
                print(f"HTTP {exc.status_code}：" + STATUS_HINTS.get(exc.status_code, "服务或网关错误。"))
                continue
            except APITimeoutError:
                print("请求超时，本轮未保存；供应商仍可能已处理请求并计费。")
                continue
            except APIConnectionError:
                print("连接失败，本轮未保存；检查网络、代理和服务地址。")
                continue
            except ValueError as exc:
                print(f"输入或响应错误：{exc}")
                continue
            print(f"助手 > {reply.content}")
            usage = reply.usage_metadata
            if usage:
                print(f"[本次用量] 输入={usage.get('input_tokens')}，输出={usage.get('output_tokens')}，合计={usage.get('total_tokens')}")
            else:
                print("[本次用量] 服务未返回用量，不能按 0 Token 计算。")


if __name__ == "__main__":
    raise SystemExit(main())
