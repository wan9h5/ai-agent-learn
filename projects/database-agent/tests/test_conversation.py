"""只替换 HTTP 响应；多轮逻辑和真实 LangChain / SDK 均实际运行。"""

import json

import httpx
import pytest
from openai import AuthenticationError

from app.conversation import Conversation
from app.langchain_api import create_model
from test_model_calls import SETTINGS, completion


def test_second_request_contains_first_complete_turn():
    requests = []
    def handler(request):
        payload = json.loads(request.content)
        requests.append(payload["messages"])
        return httpx.Response(200, json=completion(f"回答{len(requests)}"))
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        model = create_model(SETTINGS, client)
        chat = Conversation()
        chat.turn(" 我使用的是 MySQL。 ", model)
        reply = chat.turn("我使用的是什么数据库？", model)
    assert [m["role"] for m in requests[1]] == ["system", "user", "assistant", "user"]
    assert requests[1][1]["content"] == "我使用的是 MySQL。"
    assert requests[1][2]["content"] == "回答1"
    assert reply.usage_metadata["input_tokens"] == 10
    assert len(chat.messages) == 5


def test_trimming_keeps_recent_complete_pairs_and_system():
    requests = []
    def handler(request):
        requests.append(json.loads(request.content)["messages"])
        return httpx.Response(200, json=completion(f"回答{len(requests)}"))
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        model = create_model(SETTINGS, client)
        chat = Conversation(keep_turns=1)
        for question in ("问题1", "问题2", "问题3"):
            chat.turn(question, model)
    assert [m["role"] for m in requests[2]] == ["system", "user", "assistant", "user"]
    assert [m["content"] for m in requests[2][1:]] == ["问题2", "回答2", "问题3"]
    assert [m["content"] for m in chat.messages[1:]] == ["问题3", "回答3"]


@pytest.mark.parametrize("kind", ["401", "empty", "length", "timeout"])
def test_failed_turn_does_not_change_committed_history(kind):
    calls = []
    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(200, json=completion("已有成功回答"))
        if kind == "401":
            return httpx.Response(401, json={"error": {"message": "bad key"}})
        if kind == "timeout":
            raise httpx.ReadTimeout("timeout", request=request)
        return httpx.Response(200, json=completion("" if kind == "empty" else "部分回答", "length" if kind == "length" else "stop"))
    from openai import APITimeoutError
    expected = {"401": AuthenticationError, "timeout": APITimeoutError}.get(kind, ValueError)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        model = create_model(SETTINGS, client)
        chat = Conversation()
        chat.turn("成功的问题", model)
        before = chat.messages
        with pytest.raises(expected):
            chat.turn("失败的问题", model)
        assert chat.messages == before


def test_reset_and_session_isolation():
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=completion()))) as client:
        first, second = Conversation(), Conversation()
        first.turn("只有第一个会话的问题", create_model(SETTINGS, client))
        assert len(first.messages) == 3
        assert len(second.messages) == 1
        system = first.messages[0]
        first.reset()
        assert first.messages == [system]


def test_message_snapshot_cannot_mutate_state():
    chat = Conversation()
    copy = chat.messages
    copy[0]["content"] = "被意外覆盖"
    copy.append({"role": "user", "content": "意外追加"})
    assert len(chat.messages) == 1
    assert chat.messages[0]["content"] != "被意外覆盖"


def test_blank_question_never_calls_model():
    def handler(_):
        pytest.fail("空输入不得调用模型")
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        chat = Conversation()
        with pytest.raises(ValueError, match="问题不能为空"):
            chat.turn(" ", create_model(SETTINGS, client))
        assert len(chat.messages) == 1


@pytest.mark.parametrize("value", [0, -1, True, 1.5])
def test_invalid_turn_limit(value):
    with pytest.raises(ValueError):
        Conversation(value)
