"""S3-01: Function Calling / Tool Calling execution mechanism."""

import argparse
import json
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool, tool

from app.lesson06 import ModelConfigurationError, build_chat_model


SYSTEM_PROMPT = """你是一个严谨的数据库助手。
用户询问指标定义或计算口径时，优先调用 lookup_metric_definition 工具。
工具返回的是指标元数据，不是数据库查询结果。
不要声称已经连接数据库、执行 SQL 或取得真实业务数据。
读取工具结果后，用中文向用户解释；如果工具返回错误，说明当前不支持该指标。
"""

METRIC_CATALOG: dict[str, dict[str, str]] = {
    "订单数": {
        "metric": "订单数",
        "description": "符合筛选条件的订单记录数量。",
        "calculation": "COUNT(orders.id)",
        "source_table": "orders",
    },
    "销售额": {
        "metric": "销售额",
        "description": "符合筛选条件的订单金额总和。",
        "calculation": "SUM(orders.amount)",
        "source_table": "orders",
    },
}

METRIC_ALIASES = {
    "订单数量": "订单数",
    "订单总数": "订单数",
    "营收": "销售额",
    "销售收入": "销售额",
}


@tool
def lookup_metric_definition(metric: str) -> str:
    """查询业务指标的定义、计算口径和来源表。metric 示例：订单数、销售额。"""
    normalized_metric = metric.strip() if isinstance(metric, str) else ""
    normalized_metric = METRIC_ALIASES.get(normalized_metric, normalized_metric)

    definition = METRIC_CATALOG.get(normalized_metric)
    if definition is None:
        return json.dumps(
            {
                "ok": False,
                "error": "unsupported_metric",
                "message": "当前指标目录中没有该指标。",
                "available_metrics": list(METRIC_CATALOG),
            },
            ensure_ascii=False,
        )

    return json.dumps(
        {"ok": True, **definition},
        ensure_ascii=False,
    )


DEFAULT_TOOLS: tuple[BaseTool, ...] = (lookup_metric_definition,)
DEFAULT_TOOL_REGISTRY: dict[str, BaseTool] = {
    selected_tool.name: selected_tool for selected_tool in DEFAULT_TOOLS
}


@dataclass(frozen=True)
class ToolCallingResult:
    """One tool-calling round and the model's final response."""

    initial_message: AIMessage
    tool_messages: tuple[ToolMessage, ...]
    final_message: AIMessage

    @property
    def answer(self) -> str:
        content = self.final_message.content
        if isinstance(content, str):
            return content
        return "".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and isinstance(block.get("text"), str)
        )


def _serialize_tool_result(result: Any) -> str:
    if isinstance(result, str):
        return result
    return json.dumps(result, ensure_ascii=False, default=str)


def execute_tool_calls(
    ai_message: AIMessage,
    tool_registry: Mapping[str, BaseTool] | None = None,
) -> list[ToolMessage]:
    """Execute only tools present in the application's explicit allowlist."""
    registry = tool_registry or DEFAULT_TOOL_REGISTRY
    tool_messages: list[ToolMessage] = []

    for tool_call in ai_message.tool_calls:
        tool_name = tool_call.get("name", "")
        tool_call_id = tool_call.get("id")
        tool_args = tool_call.get("args", {})

        if not isinstance(tool_call_id, str) or not tool_call_id:
            raise ValueError("工具调用缺少有效的 tool_call_id。")

        selected_tool = registry.get(tool_name)
        if selected_tool is None:
            result = {
                "ok": False,
                "error": "unknown_tool",
                "message": "应用程序未授权执行该工具。",
            }
        elif not isinstance(tool_args, dict):
            result = {
                "ok": False,
                "error": "invalid_arguments",
                "message": "工具参数必须是对象。",
            }
        else:
            try:
                result = selected_tool.invoke(tool_args)
            except Exception as exc:
                # Keep internal exception details out of the model-visible result.
                result = {
                    "ok": False,
                    "error": "tool_execution_failed",
                    "message": "工具执行失败，请检查参数或服务状态。",
                    "exception_type": type(exc).__name__,
                }

        tool_messages.append(
            ToolMessage(
                content=_serialize_tool_result(result),
                tool_call_id=tool_call_id,
                name=tool_name or None,
            )
        )

    return tool_messages


def run_tool_call_demo(model: Any, question: str) -> ToolCallingResult:
    """Run exactly one tool round: model request -> Python tool -> model answer.

    This deliberately does not implement an agent loop. The loop and its
    termination conditions are covered in S3-03.
    """
    if not isinstance(question, str) or not question.strip():
        raise ValueError("用户输入不能为空。")

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=question.strip()),
    ]

    model_with_tools = model.bind_tools(list(DEFAULT_TOOLS))
    initial_message = model_with_tools.invoke(messages)

    if not isinstance(initial_message, AIMessage):
        raise TypeError("模型第一次调用没有返回 AIMessage。")

    if not initial_message.tool_calls:
        return ToolCallingResult(
            initial_message=initial_message,
            tool_messages=(),
            final_message=initial_message,
        )

    tool_messages = execute_tool_calls(initial_message)
    follow_up_messages = [
        *messages,
        initial_message,
        *tool_messages,
    ]

    # Send the tool result back to the model so it can interpret it for the user.
    final_message = model.invoke(follow_up_messages)
    if not isinstance(final_message, AIMessage):
        raise TypeError("模型处理工具结果后没有返回 AIMessage。")

    return ToolCallingResult(
        initial_message=initial_message,
        tool_messages=tuple(tool_messages),
        final_message=final_message,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="S3-01：Function Calling / Tool Calling 执行机制"
    )
    parser.add_argument("question", help="例如：查询订单数的定义和计算口径")
    args = parser.parse_args(argv)

    if not args.question.strip():
        print("输入错误：用户输入不能为空。", file=sys.stderr)
        return 2

    try:
        model = build_chat_model()
        result = run_tool_call_demo(model, args.question)

        print("========== Model tool calls ==========")
        print(
            json.dumps(
                result.initial_message.tool_calls,
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )

        print("========== Tool messages ==========")
        for tool_message in result.tool_messages:
            print(
                json.dumps(
                    {
                        "name": tool_message.name,
                        "tool_call_id": tool_message.tool_call_id,
                        "content": tool_message.content,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )

        print("========== Final answer ==========")
        print(result.answer)
        return 0
    except ModelConfigurationError as exc:
        print(f"配置错误：{exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"输入错误：{exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(
            f"执行失败（{type(exc).__name__}），请检查模型配置、网络和服务状态。",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
