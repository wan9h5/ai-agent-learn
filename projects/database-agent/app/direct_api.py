import httpx

from .config import Settings
from .messages import build_messages, require_text


def ask(settings: Settings, question: str, client: httpx.Client) -> str:
    response = client.post(
        f"{settings.base_url}/chat/completions",
        headers={"Authorization": f"Bearer {settings.api_key}"},
        json={
            "model": settings.model,
            "messages": build_messages(question),
            "max_completion_tokens": settings.max_completion_tokens,
        },
        timeout=settings.timeout,
    )
    response.raise_for_status()
    data = response.json()
    try:
        choice = data["choices"][0]
        if choice.get("finish_reason") == "length":
            raise ValueError("输出因 Token 上限截断；请调高 LLM_MAX_COMPLETION_TOKENS。")
        content = choice["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise ValueError("API 返回格式不符合本节的 Chat Completions 文本约定。") from None
    return require_text(content)
