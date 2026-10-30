SYSTEM_PROMPT = (
    "你是数据库学习助手。用中文、面向熟悉 Python 和 MySQL 的开发者回答。"
    "当前未接入数据库；不要声称已经查询或修改了真实数据。"
)
DEFAULT_QUESTION = "用三句话解释什么是只读数据库账号。"


def build_messages(question: str) -> list[dict[str, str]]:
    if not question.strip():
        raise ValueError("问题不能为空。")
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question.strip()},
    ]


def require_text(content) -> str:
    # 本节仅支持普通文本；工具调用和多模态将在后续课程处理。
    if not isinstance(content, str) or not content.strip():
        raise ValueError("没有收到非空文本；检查返回格式、拒绝信息和输出 Token 上限。")
    return content
