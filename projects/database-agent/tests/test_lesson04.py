"""S2-01：Prompt 模板、角色边界和历史消息的离线测试。"""

import json

import httpx
import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.lesson04 import (
    DEFAULT_DATABASE_CONTEXT,
    format_messages,
    history_from_conversation,
    invoke_prompt,
)


def completion(text: str) -> httpx.Response:
    return httpx.Response(200, json={
        "id": "offline",
        "object": "chat.completion",
        "created": 0,
        "model": "offline-test",
        "choices": [{
            "index": 0,
            "finish_reason": "stop",
            "message": {"role": "assistant", "content": text},
        }],
    })


def test_prompt_keeps_system_and_user_messages_separate():
    messages = format_messages(
        "统计上个月订单数",
        database_context="MySQL 8.0；orders(id, created_at, amount)",
    )

    assert [message.type for message in messages] == ["system", "human"]
    assert "MySQL 8.0" in messages[0].content
    assert "orders(id, created_at, amount)" in messages[0].content
    assert "统计上个月订单数" in messages[1].content
    assert "统计上个月订单数" not in messages[0].content


def test_template_variables_are_injected_as_values_not_reparsed():
    question = "请分析 {orders} 表中的订单数"
    messages = format_messages(question)

    assert question in messages[-1].content
    assert "{orders}" in messages[-1].content
    assert "{orders}" not in messages[0].content


def test_optional_history_is_inserted_between_system_and_current_user():
    history = [
        HumanMessage(content="我们使用 MySQL 8.0。"),
        AIMessage(content="明白，后续按 MySQL 8.0 的语法讨论。"),
    ]
    messages = format_messages("统计上个月订单数", history=history)

    assert [message.type for message in messages] == [
        "system", "human", "ai", "human"
    ]
    assert messages[1].content == "我们使用 MySQL 8.0。"
    assert messages[2].content == "明白，后续按 MySQL 8.0 的语法讨论。"


def test_history_can_be_omitted():
    messages = format_messages("查一下订单")
    assert [message.type for message in messages] == ["system", "human"]


def test_s1_02_conversation_history_skips_old_system_message():
    records = [
        {"role": "system", "content": "旧版固定 system prompt"},
        {"role": "user", "content": "我们使用 PostgreSQL。"},
        {"role": "assistant", "content": "明白。"},
    ]

    history = history_from_conversation(records)

    assert [message.type for message in history] == ["human", "ai"]
    assert history[0].content == "我们使用 PostgreSQL。"
    assert history[1].content == "明白。"


def test_unknown_conversation_role_is_rejected():
    with pytest.raises(ValueError, match="不支持的历史消息角色"):
        history_from_conversation([
            {"role": "tool", "content": "工具返回值"},
        ])


def test_system_message_cannot_be_passed_as_conversation_history():
    with pytest.raises(ValueError, match="只能包含 HumanMessage 与 AIMessage"):
        format_messages(
            "统计订单数",
            history=[SystemMessage(content="另一条 system 指令")],
        )


def test_blank_question_is_rejected_before_model_call():
    with pytest.raises(ValueError, match="question 不能为空"):
        format_messages("   ")


def test_model_receives_role_separated_formatted_messages():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        captured["messages"] = payload["messages"]
        return completion("我理解你希望统计上个月的订单数量。")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        model = ChatOpenAI(
            model="offline-test",
            api_key="offline-test-key",
            base_url="https://example.invalid/v1",
            http_client=client,
            max_retries=0,
            use_responses_api=False,
        )
        messages = format_messages(
            "统计上个月订单数",
            database_context="MySQL 8.0；orders 表",
        )
        answer = invoke_prompt(model, messages)

    assert answer == "我理解你希望统计上个月的订单数量。"
    assert [message["role"] for message in captured["messages"]] == [
        "system", "user"
    ]
    assert "MySQL 8.0" in captured["messages"][0]["content"]
    assert "统计上个月订单数" in captured["messages"][1]["content"]
