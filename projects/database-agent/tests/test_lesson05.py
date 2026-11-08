"""S2-02：Pydantic、JSON Schema 与结构化输出的离线测试。"""

import json

import httpx
import pytest
from langchain_openai import ChatOpenAI
from pydantic import ValidationError

from app.lesson05 import (
    DatabaseQueryIntent,
    extract_query_intent,
    validate_json,
    validate_payload,
)


def valid_payload() -> dict:
    return {
        "action": "query",
        "metric": "订单数",
        "time_range": "上个月",
        "filters": [
            {"column": "status", "operator": "eq", "value": "paid"}
        ],
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
        max_retries=0,
        use_responses_api=False,
    )


def test_valid_json_becomes_a_pydantic_object():
    result = validate_json(json.dumps(valid_payload(), ensure_ascii=False))

    assert isinstance(result, DatabaseQueryIntent)
    assert result.action == "query"
    assert result.metric == "订单数"
    assert result.filters[0].column == "status"


def test_model_json_schema_requires_every_field_and_forbids_extra_fields():
    schema = DatabaseQueryIntent.model_json_schema()

    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {
        "action", "metric", "time_range", "filters", "questions"
    }
    filter_schema = schema["$defs"]["FilterCondition"]
    assert filter_schema["additionalProperties"] is False
    assert set(filter_schema["required"]) == {"column", "operator", "value"}


def test_missing_field_is_rejected():
    payload = valid_payload()
    payload.pop("metric")

    with pytest.raises(ValidationError):
        validate_payload(payload)


def test_strict_mode_rejects_wrong_field_type():
    payload = valid_payload()
    payload["metric"] = 123

    with pytest.raises(ValidationError):
        validate_payload(payload)


def test_extra_top_level_field_is_rejected():
    payload = valid_payload()
    payload["sql"] = "SELECT * FROM orders"

    with pytest.raises(ValidationError):
        validate_payload(payload)


def test_extra_nested_filter_field_is_rejected():
    payload = valid_payload()
    payload["filters"][0]["table"] = "orders"

    with pytest.raises(ValidationError):
        validate_payload(payload)


def test_query_action_cannot_contain_clarification_questions():
    payload = valid_payload()
    payload["questions"] = ["你要查询哪个时间范围？"]

    with pytest.raises(ValidationError, match="questions 必须为空数组"):
        validate_payload(payload)


def test_clarify_action_requires_at_least_one_question():
    payload = valid_payload()
    payload["action"] = "clarify"
    payload["questions"] = []

    with pytest.raises(ValidationError, match="至少需要一个澄清问题"):
        validate_payload(payload)


def test_blank_metric_is_rejected():
    payload = valid_payload()
    payload["metric"] = "   "

    with pytest.raises(ValidationError):
        validate_payload(payload)


def test_model_uses_native_strict_json_schema_and_returns_pydantic_object():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        captured["response_format"] = body["response_format"]
        return completion(valid_payload())

    result = extract_query_intent(
        model_for(handler),
        "统计上个月已支付订单数",
    )

    response_format = captured["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["strict"] is True
    assert response_format["json_schema"]["schema"]["additionalProperties"] is False
    assert isinstance(result, DatabaseQueryIntent)
    assert result.metric == "订单数"


def test_model_output_that_breaks_business_rules_is_rejected():
    invalid_payload = valid_payload()
    invalid_payload["action"] = "clarify"
    invalid_payload["questions"] = []

    with pytest.raises(ValidationError, match="至少需要一个澄清问题"):
        extract_query_intent(
            model_for(lambda request: completion(invalid_payload)),
            "查一下订单",
        )


def test_empty_user_input_is_rejected_before_model_call():
    class NeverCalledModel:
        def with_structured_output(self, *args, **kwargs):
            raise AssertionError("空输入不应该调用模型")

    with pytest.raises(ValueError, match="用户输入不能为空"):
        extract_query_intent(NeverCalledModel(), "   ")
