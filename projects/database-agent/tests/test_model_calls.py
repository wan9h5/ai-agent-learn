"""用真实 ChatOpenAI 和 SDK，只在 HTTP 传输边界返回测试响应。"""

import json

import httpx
import pytest
from openai import AuthenticationError, RateLimitError, APITimeoutError

from app import cli, direct_api, langchain_api
from app.config import Settings

BACKENDS = [direct_api.ask, langchain_api.ask]
SETTINGS = Settings("test-key-not-real", "test-model", "https://example.invalid/v1")


def completion(content="只读账号仅被授予读取权限。", finish_reason="stop"):
    return {
        "id": "chatcmpl-test", "object": "chat.completion", "created": 0,
        "model": "test-model",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content},
                     "finish_reason": finish_reason}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 8, "total_tokens": 18},
    }


@pytest.mark.parametrize("ask", BACKENDS)
def test_real_request_contract(ask):
    def handler(request):
        assert str(request.url) == "https://example.invalid/v1/chat/completions"
        assert request.method == "POST"
        assert request.headers["Authorization"] == "Bearer test-key-not-real"
        payload = json.loads(request.content)
        assert payload["model"] == "test-model"
        assert payload["max_completion_tokens"] == 2048
        assert [m["role"] for m in payload["messages"]] == ["system", "user"]
        assert payload["messages"][1]["content"] == "什么是只读账号？"
        assert "未接入数据库" in payload["messages"][0]["content"]
        return httpx.Response(200, json=completion())

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert ask(SETTINGS, " 什么是只读账号？ ", client) == "只读账号仅被授予读取权限。"


@pytest.mark.parametrize("ask", BACKENDS)
@pytest.mark.parametrize("content,reason", [(None, "stop"), ("", "stop"), ("部分回答", "length")])
def test_empty_or_truncated_response(ask, content, reason):
    with httpx.Client(transport=httpx.MockTransport(
        lambda _: httpx.Response(200, json=completion(content, reason))
    )) as client:
        with pytest.raises(ValueError):
            ask(SETTINGS, "问题", client)


@pytest.mark.parametrize("ask", BACKENDS)
def test_blank_input_never_calls_api(ask):
    def handler(_):
        pytest.fail("空白问题不应发送到 API")
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError, match="问题不能为空"):
            ask(SETTINGS, "  ", client)


@pytest.mark.parametrize("ask,error", [(direct_api.ask, httpx.HTTPStatusError),
                                      (langchain_api.ask, AuthenticationError)])
def test_authentication_failure(ask, error):
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(
        401, json={"error": {"message": "Invalid API key", "type": "invalid_request_error"}}
    ))) as client:
        with pytest.raises(error):
            ask(SETTINGS, "问题", client)


@pytest.mark.parametrize("ask,error", [(direct_api.ask, httpx.HTTPStatusError),
                                      (langchain_api.ask, RateLimitError)])
def test_rate_limit_is_not_automatically_retried(ask, error):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(429, json={"error": {"message": "Rate limited"}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(error):
            ask(SETTINGS, "问题", client)
    assert len(calls) == 1


@pytest.mark.parametrize("ask,error", [(direct_api.ask, httpx.ReadTimeout),
                                      (langchain_api.ask, APITimeoutError)])
def test_timeout(ask, error):
    def handler(request):
        raise httpx.ReadTimeout("test timeout", request=request)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(error):
            ask(SETTINGS, "问题", client)


def test_missing_key_does_not_print_secret(monkeypatch, capsys):
    monkeypatch.setattr(cli, "load_dotenv", lambda *a, **kw: None)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    assert cli.main([]) == 1
    assert "LLM_API_KEY" in capsys.readouterr().err


@pytest.mark.parametrize("name,value", [("LLM_TIMEOUT_SECONDS", "nan"),
                                       ("LLM_MAX_COMPLETION_TOKENS", "0"),
                                       ("LLM_BASE_URL", "https://example.invalid/v1/chat/completions")])
def test_invalid_config(monkeypatch, name, value):
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError):
        Settings.from_env()
