"""S2-02: Pydantic, JSON Schema, and validated structured output."""

import argparse
import json
import sys
from typing import Literal

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from app.lesson03 import build_model


class FilterCondition(BaseModel):
    """A typed filter description; it is not executable SQL."""

    model_config = ConfigDict(extra="forbid", strict=True)

    column: str = Field(description="列名，只能描述用户明确提到的筛选字段")
    operator: Literal["eq", "ne", "gt", "gte", "lt", "lte", "contains", "in"] = Field(
        description="比较操作符"
    )
    value: str = Field(description="筛选值；多个 in 值用逗号分隔")


class DatabaseQueryIntent(BaseModel):
    """A validated business-level description of a database query request."""

    model_config = ConfigDict(extra="forbid", strict=True)

    action: Literal["query", "clarify"] = Field(
        description="需求足够明确时为 query；缺少必要信息时为 clarify"
    )
    metric: str = Field(description="用户希望查询的对象或指标，例如订单数、销售额")
    time_range: str = Field(description="用户提供的时间范围；未说明时填写未指定")
    filters: list[FilterCondition] = Field(
        description="用户明确提出的筛选条件；没有筛选条件时返回空数组"
    )
    questions: list[str] = Field(
        description="需要向用户澄清的问题；action=query 时必须为空数组"
    )

    @field_validator("metric", "time_range")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("该字段不能为空或只包含空白字符")
        return value

    @field_validator("questions")
    @classmethod
    def questions_must_not_be_blank(cls, value: list[str]) -> list[str]:
        cleaned = [question.strip() for question in value]
        if any(not question for question in cleaned):
            raise ValueError("questions 中不能包含空问题")
        return cleaned

    @model_validator(mode="after")
    def validate_action_consistency(self):
        if self.action == "query":
            if self.metric.casefold() in {"未提供", "未知", "unknown", "not provided"}:
                raise ValueError("action=query 时必须提供明确的 metric")
            if self.questions:
                raise ValueError("action=query 时 questions 必须为空数组")
        elif not self.questions:
            raise ValueError("action=clarify 时至少需要一个澄清问题")
        return self


SYSTEM_PROMPT = """你是一个 Database Agent 的需求解析模块。
你只负责把用户的自然语言需求转换成结构化的查询意图，不负责执行查询。

规则：
1. 严格按照提供的结构化 Schema 返回结果。
2. action 只能是 query 或 clarify。
3. 用户没有明确说明的时间范围填写“未指定”，不要自行推算日期。
4. filters 只能记录用户明确提出的筛选条件，不要擅自补充条件。
5. 如果指标不明确，或无法形成可执行的查询需求，选择 clarify，并提出具体问题。
6. action=query 时 questions 必须为空数组；action=clarify 时 questions 至少包含一个问题。
7. 不生成 SQL，不连接数据库，不编造数据库表、字段或查询结果。
"""


def build_structured_model(model: BaseChatModel):
    """Bind a Pydantic schema to the model using native JSON Schema output."""
    return model.with_structured_output(
        DatabaseQueryIntent,
        method="json_schema",
        strict=True,
    )


def validate_json(raw_json: str) -> DatabaseQueryIntent:
    """Parse JSON text and run Pydantic field and cross-field validation."""
    if not isinstance(raw_json, str) or not raw_json.strip():
        raise ValueError("JSON 输入不能为空。")
    return DatabaseQueryIntent.model_validate_json(raw_json)


def validate_payload(payload: dict) -> DatabaseQueryIntent:
    """Validate an already-decoded Python dictionary."""
    return DatabaseQueryIntent.model_validate(payload)


def extract_query_intent(
    model: BaseChatModel,
    user_text: str,
) -> DatabaseQueryIntent:
    """Ask the model for a structured intent and return a validated Pydantic object."""
    if not isinstance(user_text, str) or not user_text.strip():
        raise ValueError("用户输入不能为空。")

    structured_model = build_structured_model(model)
    result = structured_model.invoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=user_text.strip()),
    ])

    if not isinstance(result, DatabaseQueryIntent):
        raise TypeError("模型没有返回 DatabaseQueryIntent，请检查模型供应商的结构化输出支持。")

    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="S2-02：Pydantic、JSON Schema 与结构化输出校验"
    )
    parser.add_argument(
        "mode",
        choices=["schema", "validate", "extract"],
        help="schema 查看 Schema；validate 离线校验 JSON；extract 调用真实模型",
    )
    parser.add_argument(
        "value",
        nargs="?",
        help="validate 模式传入 JSON 字符串；extract 模式传入用户需求",
    )
    args = parser.parse_args(argv)

    try:
        if args.mode == "schema":
            if args.value is not None:
                parser.error("schema 模式不需要第二个参数。")
            print(json.dumps(
                DatabaseQueryIntent.model_json_schema(),
                ensure_ascii=False,
                indent=2,
            ))
            return 0

        if not args.value or not args.value.strip():
            parser.error(f"{args.mode} 模式必须提供非空参数。")

        if args.mode == "validate":
            result = validate_json(args.value)
        else:
            result = extract_query_intent(build_model(), args.value)

        print(result.model_dump_json(indent=2))
        return 0

    except ValidationError as exc:
        print(
            json.dumps(exc.errors(include_input=False), ensure_ascii=False, indent=2),
            file=sys.stderr,
        )
        return 1
    except Exception as exc:
        print(
            f"执行失败（{type(exc).__name__}）。请检查输入、模型配置、网络或模型服务。",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
