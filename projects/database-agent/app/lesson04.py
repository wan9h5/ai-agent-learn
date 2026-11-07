"""S2-01：System/User Message 与 Prompt Template。"""

import argparse
import sys
from collections.abc import Sequence

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from app.lesson03 import build_model


DEFAULT_DATABASE_CONTEXT = "当前尚未连接真实数据库，也没有读取实际 Schema。"

SYSTEM_PROMPT_TEMPLATE = """你是一个严谨的 Database Agent 需求分析助手。

你的职责：
1. 理解用户希望查询的数据、指标和时间范围。
2. 结合提供的数据库上下文解释你能做什么、还缺少什么信息。
3. 信息不足时提出具体的澄清问题，不要猜测。

当前可用的数据库上下文：
{database_context}

回答语言：{language}

当前项目边界：
- 目前只负责理解和解释查询需求，不连接数据库，也不执行 SQL。
- 不得声称已经查询、验证或读取了真实数据。
- 不得编造数据库表、字段、记录或查询结果。
- 数据库上下文没有提供的信息，应明确说明未知。
"""

USER_PROMPT_TEMPLATE = """用户本轮需求：
{question}

请先说明你对需求的理解；如果缺少必要信息，请提出澄清问题。"""


def build_prompt_template() -> ChatPromptTemplate:
    """创建带有固定角色指令、可选历史和当前用户输入的聊天模板。"""
    return ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT_TEMPLATE),
        MessagesPlaceholder(variable_name="history", optional=True),
        ("human", USER_PROMPT_TEMPLATE),
    ])


def require_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} 不能为空，且必须是字符串。")
    return value.strip()


def normalize_history(
    history: Sequence[BaseMessage] | None,
) -> list[BaseMessage]:
    """只允许把此前的 user / assistant 消息插入历史槽位。"""
    normalized: list[BaseMessage] = []
    for message in history or ():
        if not isinstance(message, (HumanMessage, AIMessage)):
            raise ValueError("history 只能包含 HumanMessage 与 AIMessage。")
        if not isinstance(message.content, str) or not message.content.strip():
            raise ValueError("history 中的消息必须包含非空文本。")
        normalized.append(message)
    return normalized


def history_from_conversation(
    records: Sequence[dict[str, str]],
) -> list[BaseMessage]:
    """把 S1-02 Conversation.messages 转成 Prompt 可使用的消息历史。

    Conversation.messages 的第一条 system 指令由本节模板接管，因此这里跳过它，
    避免一次请求中出现两条职责可能冲突的 system message。
    """
    history: list[BaseMessage] = []
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise ValueError(f"第 {index + 1} 条历史记录格式不正确。")

        role = record.get("role")
        content = record.get("content")

        if role == "system":
            continue
        if not isinstance(content, str) or not content.strip():
            raise ValueError(f"第 {index + 1} 条历史记录缺少文本内容。")

        if role == "user":
            history.append(HumanMessage(content=content))
        elif role == "assistant":
            history.append(AIMessage(content=content))
        else:
            raise ValueError(f"不支持的历史消息角色：{role!r}")

    return history


def format_messages(
    question: str,
    *,
    database_context: str = DEFAULT_DATABASE_CONTEXT,
    language: str = "中文",
    history: Sequence[BaseMessage] | None = None,
) -> list[BaseMessage]:
    """把动态输入填入模板，返回有明确角色的 LangChain 消息列表。"""
    prompt = build_prompt_template()
    return prompt.format_messages(
        database_context=require_text(database_context, "database_context"),
        language=require_text(language, "language"),
        question=require_text(question, "question"),
        history=normalize_history(history),
    )


def invoke_prompt(model: BaseChatModel, messages: Sequence[BaseMessage]) -> str:
    """调用模型并返回纯文本；本节不执行工具调用。"""
    response = model.invoke(list(messages))

    if response.tool_calls:
        raise ValueError("模型返回了工具调用；本节尚未实现工具执行。")
    if not isinstance(response.content, str) or not response.content.strip():
        raise ValueError("模型没有返回可用的文本内容。")

    return response.content.strip()


def print_messages(messages: Sequence[BaseMessage]) -> None:
    """打印最终发给模型的消息，便于在不调用模型时检查 Prompt。"""
    role_names = {
        "system": "SYSTEM",
        "human": "USER",
        "ai": "ASSISTANT",
    }
    for message in messages:
        role = role_names.get(message.type, message.type.upper())
        print(f"[{role}]")
        print(message.content)
        print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="S2-01：System/User Message 与 Prompt Template"
    )
    parser.add_argument("mode", choices=["preview", "ask"])
    parser.add_argument("question")
    parser.add_argument(
        "--database-context",
        default=DEFAULT_DATABASE_CONTEXT,
        help="提供给 Prompt 的数据库背景信息；本参数不会连接数据库。",
    )
    parser.add_argument("--language", default="中文", help="期望的回答语言。")
    args = parser.parse_args(argv)

    try:
        messages = format_messages(
            args.question,
            database_context=args.database_context,
            language=args.language,
        )

        if args.mode == "preview":
            print_messages(messages)
            return 0

        answer = invoke_prompt(build_model(), messages)
        print(answer)
        return 0
    except Exception as exc:
        print(
            f"执行失败（{type(exc).__name__}）。请检查输入、模型配置、网络或模型服务。",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
