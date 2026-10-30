"""环境变量与业务代码分离；这里不加载或打印真实密钥。"""

import math
import os
from dataclasses import dataclass, field
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Settings:
    api_key: str = field(repr=False)
    model: str
    base_url: str
    timeout: float = 60.0
    max_completion_tokens: int = 2048

    @classmethod
    def from_env(cls):
        key = os.getenv("LLM_API_KEY", "").strip()
        model = os.getenv("LLM_MODEL", "").strip()
        base = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").strip().rstrip("/")
        if not key or key == "replace-with-your-api-key":
            raise ValueError("请在本地 .env 中填写 LLM_API_KEY。")
        if not model or model == "replace-with-your-model-id":
            raise ValueError("请填写你有权限调用的 LLM_MODEL。")
        url = urlsplit(base)
        if url.scheme not in {"http", "https"} or not url.netloc:
            raise ValueError("LLM_BASE_URL 必须是 http(s) API 基础地址。")
        if url.query or url.fragment or url.username or url.password:
            raise ValueError("LLM_BASE_URL 不应包含凭据、查询参数或片段。")
        if url.path.endswith("/chat/completions"):
            raise ValueError("LLM_BASE_URL 应是基础地址，不要附加 /chat/completions。")
        try:
            timeout = float(os.getenv("LLM_TIMEOUT_SECONDS", "60"))
            limit = int(os.getenv("LLM_MAX_COMPLETION_TOKENS", "2048"))
        except ValueError:
            raise ValueError("超时应为数字，输出 Token 上限应为整数。") from None
        if not math.isfinite(timeout) or timeout <= 0 or limit <= 0:
            raise ValueError("超时和输出 Token 上限必须为正数。")
        return cls(key, model, base, timeout, limit)
