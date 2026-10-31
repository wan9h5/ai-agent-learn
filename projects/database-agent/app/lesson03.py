"""S1-03: real LangChain streaming and validated structured output."""

import argparse
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ConfigDict, Field


class QueryIntent(BaseModel):
    """Extract a data request; this object never executes a database query."""

    model_config = ConfigDict(extra="forbid", strict=True)

    action: Literal["query", "clarify"] = Field(description="需求完整用 query，否则用 clarify")
    metric: str = Field(description="用户想查询的对象或指标；未说明则写未提供")
    time_range: str = Field(description="原文中的时间范围；未说明则写未提供")
    questions: list[str] = Field(description="需要追问的问题；需求完整时返回空列表")


def build_model() -> ChatOpenAI:
    # app/lesson03.py -> projects/database-agent/.env
    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
    api_key = os.getenv("LLM_API_KEY", "").strip()
    model_name = os.getenv("LLM_MODEL", "").strip()
    if not api_key or not model_name:
        raise ValueError("请在原项目 .env 中配置 LLM_API_KEY 和 LLM_MODEL")
    return ChatOpenAI(
        model=model_name,
        api_key=api_key,
        base_url=os.getenv("LLM_BASE_URL", "").strip() or None,
        max_completion_tokens=2048,
        timeout=60,
        max_retries=0,
        use_responses_api=False,
    )


def chat_messages(text: str) -> list[BaseMessage]:
    return [
        SystemMessage(content="你是数据库助手，用中文解释问题；不要编造数据库查询结果。"),
        HumanMessage(content=text),
    ]


def stream_text(model: ChatOpenAI, messages: list[BaseMessage]) -> Iterator[str]:
    for chunk in model.stream(messages):
        # Some chunks contain metadata only, so text can be empty.
        if chunk.text:
            yield chunk.text


def extract_intent(
    model: ChatOpenAI,
    text: str,
    method: Literal["json_schema", "function_calling"] = "json_schema",
) -> QueryIntent:
    options = {"strict": True} if method == "json_schema" else {}
    structured_model = model.with_structured_output(
        QueryIntent, method=method, **options
    )
    result = structured_model.invoke([
        SystemMessage(content=(
            "提取用户的数据查询需求，不生成 SQL，不连接数据库，不编造数据。"
            "对象或指标、时间范围缺失时，action 为 clarify，questions 写明追问。"
            "需求完整时 action 为 query，questions 为空列表。"
            "time_range 保留用户原文，不自行计算具体日期。"
            "如果用户要求写入、修改或删除数据，返回 clarify 并说明本助手仅处理查询需求。"
        )),
        HumanMessage(content=text),
    ])
    if not isinstance(result, QueryIntent):
        raise ValueError("模型未返回可用的结构化结果，请检查拒绝、截断或模型兼容性")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="S1-03 流式输出与结构化输出")
    parser.add_argument("mode", choices=["stream", "intent"])
    parser.add_argument("text")
    parser.add_argument("--method", choices=["json_schema", "function_calling"], default="json_schema")
    args = parser.parse_args()
    try:
        model = build_model()
        if args.mode == "stream":
            for text in stream_text(model, chat_messages(args.text)):
                print(text, end="", flush=True)
            print()
        else:
            result = extract_intent(model, args.text, args.method)
            print(result.model_dump_json(indent=2))
    except Exception as exc:
        # Do not print provider response bodies, credentials, or raw request details.
        parser.exit(1, f"\n请求未完成（{type(exc).__name__}）；请检查配置、网络与模型能力。\n")


if __name__ == "__main__":
    main()
