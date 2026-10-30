"""统一命令行入口：两种实现使用相同问题、配置和错误处理。"""

import argparse
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv
from openai import APIConnectionError, APIStatusError, APITimeoutError

from . import direct_api, langchain_api
from .config import Settings
from .messages import DEFAULT_QUESTION

STATUS_HINTS = {
    400: "请求参数不被支持；核对模型的 messages 和 max_completion_tokens 支持情况。",
    401: "认证失败；检查本地密钥及其对应的服务地址。",
    403: "访问被拒绝；检查账号、模型权限及供应商限制。",
    404: "接口或模型不存在；核对基础地址与模型 ID。",
    429: "请求被限流或额度不足；查看供应商控制台，不要直接无限重试。",
}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="S1-01：对比直接 HTTP 与 LangChain 模型调用")
    parser.add_argument("--backend", choices=["direct", "langchain"], default="direct")
    parser.add_argument("--question", default=DEFAULT_QUESTION)
    args = parser.parse_args(argv)
    # 无论从哪里调用，读取的都是本项目目录内的 .env；系统环境变量优先。
    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
    try:
        settings = Settings.from_env()
        ask = direct_api.ask if args.backend == "direct" else langchain_api.ask
        # Client 在本次命令内复用连接，命令完成后关闭。
        with httpx.Client(timeout=settings.timeout) as client:
            answer = ask(settings, args.question, client)
    except (httpx.HTTPStatusError, APIStatusError) as exc:
        status = exc.response.status_code
        hint = STATUS_HINTS.get(status, "服务端或网关返回错误；稍后重试并检查供应商状态。")
        print(f"HTTP {status}：{hint}", file=sys.stderr)
        return 1
    except (httpx.TimeoutException, APITimeoutError):
        print("请求超时；检查网络或调高 LLM_TIMEOUT_SECONDS。", file=sys.stderr)
        return 1
    except (httpx.RequestError, APIConnectionError):
        print("连接失败；检查基础地址、网络、代理和证书配置。", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"配置、输入或响应错误：{exc}", file=sys.stderr)
        return 1
    print(f"backend={args.backend}, model={settings.model}")
    print(answer)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
