import json

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.lesson07 import (
    DEFAULT_TOOLS,
    execute_tool_calls,
    lookup_metric_definition,
    run_tool_call_demo,
)


def test_lookup_metric_definition_returns_order_count_metadata():
    raw_result = lookup_metric_definition.invoke({"metric": "订单数量"})
    result = json.loads(raw_result)

    assert result["ok"] is True
    assert result["metric"] == "订单数"
    assert result["calculation"] == "COUNT(orders.id)"
    assert result["source_table"] == "orders"


def test_lookup_metric_definition_returns_supported_metrics_for_unknown_metric():
    raw_result = lookup_metric_definition.invoke({"metric": "用户满意度"})
    result = json.loads(raw_result)

    assert result["ok"] is False
    assert result["error"] == "unsupported_metric"
    assert "订单数" in result["available_metrics"]


def test_execute_tool_calls_returns_tool_message_with_matching_call_id():
    ai_message = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "lookup_metric_definition",
                "args": {"metric": "订单数"},
                "id": "call_metric_001",
                "type": "tool_call",
            }
        ],
    )

    tool_messages = execute_tool_calls(ai_message)

    assert len(tool_messages) == 1
    assert isinstance(tool_messages[0], ToolMessage)
    assert tool_messages[0].name == "lookup_metric_definition"
    assert tool_messages[0].tool_call_id == "call_metric_001"
    assert json.loads(tool_messages[0].content)["ok"] is True


def test_execute_tool_calls_rejects_tools_outside_the_allowlist():
    ai_message = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "delete_all_orders",
                "args": {},
                "id": "call_unknown_001",
                "type": "tool_call",
            }
        ],
    )

    tool_messages = execute_tool_calls(ai_message)
    result = json.loads(tool_messages[0].content)

    assert result["ok"] is False
    assert result["error"] == "unknown_tool"
    assert tool_messages[0].tool_call_id == "call_unknown_001"


class FakeModel:
    def __init__(self, responses):
        self.responses = list(responses)
        self.bound_tools = None
        self.invocations = []

    def bind_tools(self, tools):
        self.bound_tools = tools
        return self

    def invoke(self, messages):
        self.invocations.append(messages)
        return self.responses.pop(0)


def test_run_tool_call_demo_executes_tool_and_returns_final_answer():
    first_response = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "lookup_metric_definition",
                "args": {"metric": "订单数"},
                "id": "call_flow_001",
                "type": "tool_call",
            }
        ],
    )
    final_response = AIMessage(content="订单数表示符合条件的订单记录数量。")
    model = FakeModel([first_response, final_response])

    result = run_tool_call_demo(model, "订单数是什么意思？")

    assert model.bound_tools == list(DEFAULT_TOOLS)
    assert len(model.invocations) == 2
    assert result.initial_message is first_response
    assert len(result.tool_messages) == 1
    assert result.tool_messages[0].tool_call_id == "call_flow_001"
    assert isinstance(model.invocations[1][-1], ToolMessage)
    assert result.answer == "订单数表示符合条件的订单记录数量。"


def test_run_tool_call_demo_returns_direct_answer_without_tool_execution():
    direct_response = AIMessage(content="我可以直接回答这个概念问题。")
    model = FakeModel([direct_response])

    result = run_tool_call_demo(model, "什么是数据库？")

    assert len(model.invocations) == 1
    assert result.tool_messages == ()
    assert result.final_message is direct_response
    assert result.answer == "我可以直接回答这个概念问题。"


def test_run_tool_call_demo_rejects_empty_question():
    model = FakeModel([])

    with pytest.raises(ValueError, match="用户输入不能为空"):
        run_tool_call_demo(model, "   ")

    assert model.invocations == []
