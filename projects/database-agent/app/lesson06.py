"""S2-03: timeout, retry, error classification, and model adapters."""

import argparse
import json
import math
import random
import sys
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Literal, Protocol, TypeVar

import httpx
import openai
from dotenv import load_dotenv
from langchain_core.exceptions import OutputParserException
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import ValidationError

from app.config import Settings
from app.lesson05 import DatabaseQueryIntent, SYSTEM_PROMPT


T = TypeVar("T")
StructuredMethod = Literal["json_schema", "function_calling"]


class ErrorCategory(str, Enum):
    """Stable application-level error codes; provider details stay internal."""

    TIMEOUT = "timeout"
    CONNECTION = "connection_error"
    RATE_LIMIT = "rate_limit"
    SERVER = "server_error"
    AUTHENTICATION = "authentication_error"
    INVALID_REQUEST = "invalid_request"
    OUTPUT_VALIDATION = "output_validation"
    UNKNOWN = "unknown_error"


@dataclass(frozen=True)
class ErrorClassification:
    category: ErrorCategory
    retryable: bool
    public_message: str
    status_code: int | None = None


_ERROR_MESSAGES = {
    ErrorCategory.TIMEOUT: "模型服务响应超时，请稍后重试。",
    ErrorCategory.CONNECTION: "无法连接模型服务，请检查网络或服务状态。",
    ErrorCategory.RATE_LIMIT: "模型服务触发限流，请稍后重试。",
    ErrorCategory.SERVER: "模型服务暂时异常，请稍后重试。",
    ErrorCategory.AUTHENTICATION: "模型服务认证失败，请检查 API Key 或账号权限。",
    ErrorCategory.INVALID_REQUEST: "模型服务拒绝了请求，请检查请求参数和模型能力。",
    ErrorCategory.OUTPUT_VALIDATION: "模型返回的数据未通过结构化输出校验。",
    ErrorCategory.UNKNOWN: "模型调用失败，请检查服务配置和日志。",
}


def _classification(
    category: ErrorCategory,
    retryable: bool,
    status_code: int | None = None,
) -> ErrorClassification:
    return ErrorClassification(
        category=category,
        retryable=retryable,
        public_message=_ERROR_MESSAGES[category],
        status_code=status_code,
    )


def _classify_status(status_code: int) -> ErrorClassification:
    if status_code == 408:
        return _classification(ErrorCategory.TIMEOUT, True, status_code)
    if status_code == 429:
        return _classification(ErrorCategory.RATE_LIMIT, True, status_code)
    if status_code in {401, 403}:
        return _classification(ErrorCategory.AUTHENTICATION, False, status_code)
    if status_code >= 500:
        return _classification(ErrorCategory.SERVER, True, status_code)
    return _classification(ErrorCategory.INVALID_REQUEST, False, status_code)


class OutputContractError(ValueError):
    """The adapter received a result that violates its output contract."""


class ModelConfigurationError(RuntimeError):
    """Safe, provider-independent configuration error for CLI and HTTP clients."""


def classify_error(exc: Exception) -> ErrorClassification:
    """Map SDK/transport exceptions to stable categories and retry decisions.

    Only transient failures are retryable. Unknown errors fail closed and are
    not retried automatically.
    """
    if isinstance(exc, (openai.APITimeoutError, httpx.TimeoutException)):
        return _classification(ErrorCategory.TIMEOUT, True)

    if isinstance(exc, (openai.APIConnectionError, httpx.TransportError)):
        return _classification(ErrorCategory.CONNECTION, True)

    if isinstance(exc, openai.RateLimitError):
        return _classification(ErrorCategory.RATE_LIMIT, True, exc.status_code)

    if isinstance(exc, (openai.AuthenticationError, openai.PermissionDeniedError)):
        return _classification(ErrorCategory.AUTHENTICATION, False, exc.status_code)

    if isinstance(exc, openai.BadRequestError):
        return _classification(ErrorCategory.INVALID_REQUEST, False, exc.status_code)

    if isinstance(exc, openai.InternalServerError):
        return _classification(ErrorCategory.SERVER, True, exc.status_code)

    if isinstance(exc, openai.APIStatusError):
        return _classify_status(exc.status_code)

    if isinstance(exc, httpx.HTTPStatusError):
        return _classify_status(exc.response.status_code)

    if isinstance(
        exc,
        (ValidationError, OutputParserException, OutputContractError, json.JSONDecodeError),
    ):
        return _classification(ErrorCategory.OUTPUT_VALIDATION, False)

    return _classification(ErrorCategory.UNKNOWN, False)


@dataclass(frozen=True)
class RetryPolicy:
    """Retry limits. max_attempts includes the original request."""

    max_attempts: int = 3
    base_delay_seconds: float = 0.5
    max_delay_seconds: float = 4.0
    jitter_seconds: float = 0.1

    def __post_init__(self) -> None:
        if isinstance(self.max_attempts, bool) or not isinstance(self.max_attempts, int):
            raise ValueError("max_attempts 必须是整数。")
        if self.max_attempts < 1:
            raise ValueError("max_attempts 至少为 1。")

        values = {
            "base_delay_seconds": self.base_delay_seconds,
            "max_delay_seconds": self.max_delay_seconds,
            "jitter_seconds": self.jitter_seconds,
        }
        for name, value in values.items():
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value < 0
            ):
                raise ValueError(f"{name} 必须是有限的非负数。")

        if self.max_delay_seconds < self.base_delay_seconds:
            raise ValueError("max_delay_seconds 不能小于 base_delay_seconds。")


class ModelCallError(RuntimeError):
    """Sanitized error raised after a model call fails or retries are exhausted."""

    def __init__(self, classification: ErrorClassification, attempts: int):
        self.category = classification.category
        self.retryable = classification.retryable
        self.public_message = classification.public_message
        self.status_code = classification.status_code
        self.attempts = attempts
        super().__init__(
            f"{self.category.value}: {self.public_message} (attempts={attempts})"
        )


def invoke_with_retry(
    operation: Callable[[], T],
    policy: RetryPolicy | None = None,
    *,
    sleep: Callable[[float], None] = time.sleep,
    random_value: Callable[[], float] = random.random,
) -> T:
    """Run an operation with bounded exponential backoff and jitter."""
    retry_policy = policy or RetryPolicy()

    for attempt in range(1, retry_policy.max_attempts + 1):
        try:
            return operation()
        except Exception as exc:
            classification = classify_error(exc)
            if not classification.retryable or attempt >= retry_policy.max_attempts:
                raise ModelCallError(classification, attempts=attempt) from exc

            backoff = min(
                retry_policy.base_delay_seconds * (2 ** (attempt - 1)),
                retry_policy.max_delay_seconds,
            )
            jitter = random_value()
            if not math.isfinite(jitter) or not 0 <= jitter <= 1:
                raise ValueError("random_value 必须返回 0 到 1 之间的有限数值。")
            sleep(backoff + retry_policy.jitter_seconds * jitter)

    raise RuntimeError("unreachable retry state")


class QueryIntentModelAdapter(Protocol):
    """Business-facing interface; callers do not depend on a provider SDK."""

    def extract(self, user_text: str) -> DatabaseQueryIntent:
        ...


class LangChainQueryIntentAdapter:
    """Adapt any compatible LangChain chat model to the query-intent interface."""

    def __init__(
        self,
        model: BaseChatModel,
        *,
        structured_method: StructuredMethod = "json_schema",
    ):
        if structured_method == "json_schema":
            self._structured_model = model.with_structured_output(
                DatabaseQueryIntent,
                method="json_schema",
                strict=True,
            )
        else:
            self._structured_model = model.with_structured_output(
                DatabaseQueryIntent,
                method="function_calling",
            )

    def extract(self, user_text: str) -> DatabaseQueryIntent:
        if not isinstance(user_text, str) or not user_text.strip():
            raise ValueError("用户输入不能为空。")

        result = self._structured_model.invoke([
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=user_text.strip()),
        ])

        if not isinstance(result, DatabaseQueryIntent):
            raise OutputContractError(
                "模型没有返回 DatabaseQueryIntent；请检查供应商的结构化输出能力。"
            )

        return result


class ReliableQueryService:
    """Application service that combines an adapter with bounded retry behavior."""

    def __init__(
        self,
        adapter: QueryIntentModelAdapter,
        retry_policy: RetryPolicy | None = None,
        *,
        sleep: Callable[[float], None] = time.sleep,
        random_value: Callable[[], float] = random.random,
    ):
        self.adapter = adapter
        self.retry_policy = retry_policy or RetryPolicy()
        self.sleep = sleep
        self.random_value = random_value

    def extract(self, user_text: str) -> DatabaseQueryIntent:
        if not isinstance(user_text, str) or not user_text.strip():
            raise ValueError("用户输入不能为空。")

        normalized_text = user_text.strip()
        return invoke_with_retry(
            lambda: self.adapter.extract(normalized_text),
            self.retry_policy,
            sleep=self.sleep,
            random_value=self.random_value,
        )


def load_settings() -> Settings:
    """Load the existing project .env without overwriting process variables."""
    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
    return Settings.from_env()


def build_chat_model(settings: Settings | None = None) -> ChatOpenAI:
    """Build the OpenAI-compatible chat model with app-owned retry behavior."""
    try:
        resolved = settings or load_settings()
    except ValueError as exc:
        raise ModelConfigurationError(
            "模型服务配置不完整或无效，请检查本地 .env 中的模型配置。"
        ) from exc

    return ChatOpenAI(
        model=resolved.model,
        api_key=resolved.api_key,
        base_url=resolved.base_url,
        max_completion_tokens=resolved.max_completion_tokens,
        timeout=resolved.timeout,
        # Retry is controlled by invoke_with_retry; avoid hidden SDK retries.
        max_retries=0,
        use_responses_api=False,
    )


def build_service(
    settings: Settings | None = None,
    retry_policy: RetryPolicy | None = None,
) -> ReliableQueryService:
    model = build_chat_model(settings)
    adapter = LangChainQueryIntentAdapter(model)
    return ReliableQueryService(adapter, retry_policy)


def http_status_for_error(category: ErrorCategory) -> int:
    """Translate upstream failures to stable HTTP status codes."""
    return {
        ErrorCategory.TIMEOUT: 504,
        ErrorCategory.CONNECTION: 503,
        ErrorCategory.RATE_LIMIT: 429,
        ErrorCategory.SERVER: 503,
        ErrorCategory.AUTHENTICATION: 502,
        ErrorCategory.INVALID_REQUEST: 502,
        ErrorCategory.OUTPUT_VALIDATION: 502,
        ErrorCategory.UNKNOWN: 502,
    }[category]


def public_error_payload(error: ModelCallError) -> dict:
    """Return a safe response; never expose provider response bodies or secrets."""
    return {
        "error": {
            "code": error.category.value,
            "message": error.public_message,
            "attempts": error.attempts,
        }
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="S2-03：超时、重试、错误分类与模型适配"
    )
    parser.add_argument("question", help="要解析的自然语言查询需求")
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=3,
        help="最多尝试次数，包含第一次请求；默认 3",
    )
    args = parser.parse_args(argv)

    if not args.question.strip():
        print("输入错误：用户输入不能为空。", file=sys.stderr)
        return 2

    try:
        policy = RetryPolicy(max_attempts=args.max_attempts)
        service = build_service(retry_policy=policy)
        result = service.extract(args.question)
        print(result.model_dump_json(indent=2))
        return 0
    except ModelCallError as exc:
        print(
            json.dumps(public_error_payload(exc), ensure_ascii=False, indent=2),
            file=sys.stderr,
        )
        return 1
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
