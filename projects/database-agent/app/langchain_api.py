import httpx
from langchain_openai import ChatOpenAI

from .config import Settings
from .messages import build_messages, require_text


def create_model(settings: Settings, client: httpx.Client) -> ChatOpenAI:
    """单轮与多轮入口共用同一模型配置。"""
    return ChatOpenAI(
        model=settings.model,
        api_key=settings.api_key,
        base_url=settings.base_url,
        timeout=settings.timeout,
        max_retries=0,
        max_completion_tokens=settings.max_completion_tokens,
        use_responses_api=False,
        http_client=client,
    )


def ask(settings: Settings, question: str, client: httpx.Client) -> str:
    messages = build_messages(question)
    llm = create_model(settings, client)
    message = llm.invoke(messages)
    if message.response_metadata.get("finish_reason") == "length":
        raise ValueError("输出因 Token 上限截断；请调高 LLM_MAX_COMPLETION_TOKENS。")
    return require_text(message.content)
