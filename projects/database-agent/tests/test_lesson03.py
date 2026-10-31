"""Offline tests replace HTTP transport, not the LangChain implementation."""

import json

import httpx
import pytest
from fastapi.testclient import TestClient
from langchain_openai import ChatOpenAI
from pydantic import ValidationError

from app.lesson03 import QueryIntent, chat_messages, extract_intent, stream_text
from app.lesson03_api import app, get_model


def model_for(handler):
    return ChatOpenAI(
        model="offline-test",
        api_key="offline-test-key",
        base_url="https://example.invalid/v1",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        max_retries=0,
        use_responses_api=False,
    )


def completion(payload):
    return httpx.Response(200, json={
        "id": "offline", "object": "chat.completion", "created": 0,
        "model": "offline-test",
        "choices": [{"index": 0, "finish_reason": "stop", "message": {
            "role": "assistant", "content": json.dumps(payload, ensure_ascii=False),
        }}],
    })


def chunk(text, finish=None):
    data = {
        "id": "offline", "object": "chat.completion.chunk", "created": 0,
        "model": "offline-test", "choices": [{
            "index": 0, "delta": {"content": text}, "finish_reason": finish,
        }],
    }
    return ("data: " + json.dumps(data, ensure_ascii=False) + "\n\n").encode()


def normal_stream(request):
    assert json.loads(request.content)["stream"] is True
    return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=(
        chunk("你好") + chunk("\n世界") + chunk("", "stop") + b"data: [DONE]\n\n"
    ))


class BrokenStream(httpx.SyncByteStream):
    def __iter__(self):
        yield chunk("半截答案")
        raise httpx.ReadError("offline interrupted stream")


def broken_stream(request):
    return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=BrokenStream())


def test_stream_returns_deltas_and_skips_empty_text():
    assert list(stream_text(model_for(normal_stream), chat_messages("你好"))) == ["你好", "\n世界"]


def test_stream_failure_is_not_silently_successful():
    chunks = stream_text(model_for(broken_stream), chat_messages("你好"))
    assert next(chunks) == "半截答案"
    with pytest.raises(Exception):
        next(chunks)


def test_intent_uses_native_schema_and_returns_validated_object():
    payload = {"action": "query", "metric": "订单数", "time_range": "上个月", "questions": []}

    def handler(request):
        fmt = json.loads(request.content)["response_format"]
        assert fmt["type"] == "json_schema"
        assert fmt["json_schema"]["strict"] is True
        assert fmt["json_schema"]["schema"]["additionalProperties"] is False
        return completion(payload)

    result = extract_intent(model_for(handler), "统计上个月订单数")
    assert isinstance(result, QueryIntent)
    assert result.model_dump() == payload


@pytest.mark.parametrize("changes", [
    {"action": "delete"}, {"questions": "没有"}, {"unexpected": "extra"},
])
def test_invalid_model_output_is_rejected(changes):
    payload = {"action": "query", "metric": "订单数", "time_range": "上个月", "questions": []}
    payload.update(changes)
    with pytest.raises(ValidationError):
        extract_intent(model_for(lambda request: completion(payload)), "统计订单数")


def test_api_stream_frames_text_and_signals_completion():
    app.dependency_overrides[get_model] = lambda: model_for(normal_stream)
    try:
        with TestClient(app) as client:
            response = client.post("/chat/stream", json={"message": "你好"})
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        assert 'event: delta\ndata: {"text": "你好"}\n\n' in response.text
        assert 'data: {"text": "\\n世界"}' in response.text
        assert response.text.endswith("event: done\ndata: {}\n\n")
    finally:
        app.dependency_overrides.clear()


def test_api_interruption_has_error_without_done():
    app.dependency_overrides[get_model] = lambda: model_for(broken_stream)
    try:
        with TestClient(app) as client:
            response = client.post("/chat/stream", json={"message": "你好"})
        assert "半截答案" in response.text
        assert "event: error" in response.text
        assert "event: done" not in response.text
    finally:
        app.dependency_overrides.clear()


def test_api_invalid_structured_output_returns_502():
    app.dependency_overrides[get_model] = lambda: model_for(lambda request: completion({"action": "delete"}))
    try:
        with TestClient(app) as client:
            response = client.post("/intent", json={"message": "统计订单数"})
        assert response.status_code == 502
    finally:
        app.dependency_overrides.clear()
