"""S1-02：显式管理纯文本对话；只保存成功的完整轮次。"""

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage

from .messages import SYSTEM_PROMPT, require_text


class Conversation:
    def __init__(self, keep_turns: int = 3):
        if not isinstance(keep_turns, int) or isinstance(keep_turns, bool) or keep_turns < 1:
            raise ValueError("keep_turns 必须是大于 0 的整数。")
        self.keep_turns = keep_turns
        self._messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    @property
    def messages(self) -> list[dict[str, str]]:
        # 给调用者副本，防止查看历史时意外改坏内部状态。
        return [message.copy() for message in self._messages]

    def reset(self):
        self._messages = [self._messages[0].copy()]

    def turn(self, question: str, model: BaseChatModel) -> AIMessage:
        if not question.strip():
            raise ValueError("问题不能为空。")
        pending = [*self.messages, {"role": "user", "content": question.strip()}]
        reply = model.invoke(pending)
        if reply.response_metadata.get("finish_reason") == "length":
            raise ValueError("输出已截断；本轮未保存，请增加输出 Token 预算后重试。")
        if reply.tool_calls:
            raise ValueError("本节仅处理纯文本对话，不执行或保存工具调用。")
        answer = require_text(reply.content)
        # 只有模型调用和正文校验都成功，才一起提交 user + assistant。
        completed = [*pending[1:], {"role": "assistant", "content": answer}]
        self._messages = [pending[0], *completed[-2 * self.keep_turns:]]
        return reply
