"""S2-03：超时、重试、错误分类和模型适配的离线测试。"""

import json

import httpx
import pytest
from fastapi.testclient import TestClient
from langchain_openai import ChatOpenAI
from openai import AuthenticationError, BadRequestError, InternalServerError, RateLimitError
from pydantic import ValidationError

from app.config import Settings
from app.lesson05 import DatabaseQueryIntent
from app.lesson06 import (
    ErrorCategory,
    LangChainQueryIntentAdapter,
    ModelCallError,
    ReliableQueryService,
    RetryPolicy,
    build_chat_model,
    classify_error,
    invoke_with_retry,
)
from app.lesson06_api import app, get_service


def valid_payload() -> dict:
    return {
        "action": "query",
        "metric": "订单数",
        "time_range": "上个月",
        "filters": [],
        "questions": [],
    }


def completion(payload: dict) -> httpx.Response:
    return httpx.Response(200, json={
        "id": "offline",
        "object": "chat.completion",
        "created": 0,
        "model": "offline-test",
        "choices": [{
            "index": 0,
            "finish_reason": "stop",
            "message": {
                "role": "assistant",
                "content": json.dumps(payload, ensure_ascii=False),
            },
        }],
    })


def model_for(handler) -> ChatOpenAI:
    return ChatOpenAI(
        model="offline-test",
        api_key="offline-test-key",
        base_url="https://example.invalid/v1",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        timeout=2,
        max_retries=0,
        use_responses_api=False,
    )


def provider_error(error_type, status_code: int):
    request = httpx.Request("POST", "https://example.invalid/v1/chat/completions")
    response = httpx.Response(
        status_code,
        request=request,
        json={"error": {"message": "provider detail must not reach the client"}},
    )
    return error_type(
        "provider detail must not reach the client",
        response=response,
        body={"error": {"message": "provider detail must not reach the client"}},
    )


def test_timeout_and_connection_errors_are_retryable():
    timeout = classify_error(httpx.ReadTimeout("read timed out"))
    connection = classify_error(httpx.ConnectError("connection refused"))

    assert timeout.category == ErrorCategory.TIMEOUT
    assert timeout.retryable is True
    assert connection.category == ErrorCategory.CONNECTION
    assert connection.retryable is True


def test_rate_limit_and_server_errors_are_retryable():
    rate_limit = classify_error(provider_error(RateLimitError, 429))
    server = classify_error(provider_error(InternalServerError, 503))

    assert rate_limit.category == ErrorCategory.RATE_LIMIT
    assert rate_limit.retryable is True
    assert server.category == ErrorCategory.SERVER
    assert server.retryable is True


def test_authentication_error_is_not_retryable():
    error = classify_error(provider_error(AuthenticationError, 401))

    assert error.category == ErrorCategory.AUTHENTICATION
    assert error.retryable is False


def test_invalid_request_and_output_validation_are_not_retryable():
    request_error = classify_error(provider_error(BadRequestError, 400))
    with pytest.raises(ValidationError) as caught:
        DatabaseQueryIntent.model_validate({"action": "query"})

    output_error = classify_error(caught.value)

    assert request_error.category == ErrorCategory.INVALID_REQUEST
    assert request_error.retryable is False
    assert output_error.category == ErrorCategory.OUTPUT_VALIDATION
    assert output_error.retryable is False


def test_unknown_errors_fail_closed_without_retry():
    result = classify_error(RuntimeError("unexpected"))

    assert result.category == ErrorCategory.UNKNOWN
    assert result.retryable is False


def test_retry_succeeds_after_two_transient_failures():
    calls = 0
    delays = []

    def operation():
        nonlocal calls
        calls += 1
        if calls < 3:
            raise httpx.ReadTimeout("temporary timeout")
        return "success"

    result = invoke_with_retry(
        operation,
        RetryPolicy(
            max_attempts=3,
            base_delay_seconds=0.5,
            max_delay_seconds=4,
            jitter_seconds=0.1,
        ),
        sleep=delays.append,
        random_value=lambda: 0,
    )

    assert result == "success"
    assert calls == 3
    assert delays == [0.5, 1.0]


def test_retry_stops_after_max_attempts():
    calls = 0

    def operation():
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("temporary timeout")

    with pytest.raises(ModelCallError) as caught:
        invoke_with_retry(
            operation,
            RetryPolicy(
                max_attempts=3,
                base_delay_seconds=0,
                max_delay_seconds=0,
                jitter_seconds=0,
            ),
            sleep=lambda _: None,
        )

    assert calls == 3
    assert caught.value.attempts == 3
    assert caught.value.category == ErrorCategory.TIMEOUT


def test_non_retryable_authentication_error_is_attempted_only_once():
    calls = 0
    error = provider_error(AuthenticationError, 401)

    def operation():
        nonlocal calls
        calls += 1
        raise error

    with pytest.raises(ModelCallError) as caught:
        invoke_with_retry(
            operation,
            RetryPolicy(max_attempts=4),
            sleep=lambda _: None,
        )

    assert calls == 1
    assert caught.value.category == ErrorCategory.AUTHENTICATION
    assert caught.value.attempts == 1


@pytest.mark.parametrize("kwargs", [
    {"max_attempts": 0},
    {"max_attempts": 1, "base_delay_seconds": -1},
    {"max_attempts": 1, "base_delay_seconds": 2, "max_delay_seconds": 1},
    {"max_attempts": 1, "jitter_seconds": float("nan")},
])
def test_invalid_retry_policy_is_rejected(kwargs):
    with pytest.raises(ValueError):
        RetryPolicy(**kwargs)


def test_build_chat_model_uses_timeout_and_disables_sdk_retries(monkeypatch):
    captured = {}

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("app.lesson06.ChatOpenAI", FakeChatOpenAI)
    settings = Settings(
        api_key="test-key",
        model="test-model",
        base_url="https://example.invalid/v1",
        timeout=7.5,
        max_completion_tokens=512,
    )

    model = build_chat_model(settings)

    assert isinstance(model, FakeChatOpenAI)
    assert captured["timeout"] == 7.5
    assert captured["max_retries"] == 0
    assert captured["max_completion_tokens"] == 512
    assert captured["base_url"] == "https://example.invalid/v1"


def test_adapter_uses_strict_json_schema_and_returns_pydantic_object():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        captured["response_format"] = body["response_format"]
        return completion(valid_payload())

    adapter = LangChainQueryIntentAdapter(model_for(handler))
    service = ReliableQueryService(
        adapter,
        RetryPolicy(max_attempts=1),
    )

    result = service.extract("统计上个月订单数")

    response_format = captured["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["strict"] is True
    assert isinstance(result, DatabaseQueryIntent)
    assert result.metric == "订单数"


def test_blank_input_is_rejected_before_adapter_call():
    class NeverCalledAdapter:
        def extract(self, user_text):
            pytest.fail("空输入不应调用 adapter")

    service = ReliableQueryService(NeverCalledAdapter())

    with pytest.raises(ValueError, match="用户输入不能为空"):
        service.extract("   ")


def test_api_returns_validated_query_intent():
    class StaticAdapter:
        def extract(self, user_text):
            return DatabaseQueryIntent.model_validate(valid_payload())

    service = ReliableQueryService(
        StaticAdapter(),
        RetryPolicy(max_attempts=1),
    )
    app.dependency_overrides[get_service] = lambda: service
    try:
        with TestClient(app) as client:
            response = client.post("/intent", json={"message": "统计上个月订单数"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["metric"] == "订单数"


def test_api_returns_normalized_timeout_error_without_provider_details():
    class TimeoutAdapter:
        def extract(self, user_text):
            raise httpx.ReadTimeout("provider detail must not reach the client")

    service = ReliableQueryService(
        TimeoutAdapter(),
        RetryPolicy(
            max_attempts=2,
            base_delay_seconds=0,
            max_delay_seconds=0,
            jitter_seconds=0,
        ),
        sleep=lambda _: None,
    )
    app.dependency_overrides[get_service] = lambda: service
    try:
        with TestClient(app) as client:
            response = client.post("/intent", json={"message": "统计订单数"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 504
    assert response.json() == {
        "error": {
            "code": "timeout",
            "message": "模型服务响应超时，请稍后重试。",
            "attempts": 2,
        }
    }
    assert "provider detail" not in response.text


def test_api_rejects_blank_message():
    with TestClient(app) as client:
        response = client.post("/intent", json={"message": "   "})

    assert response.status_code == 422
