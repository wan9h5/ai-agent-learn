# S1-03：Streaming（流式输出）与 Structured Output（结构化输出）

> 延续项目：`ai-agent-learn/projects/database-agent`。这是一节增量课程：沿用前两节的虚拟环境、`.env` 和多轮对话代码，新建本节模块即可。讲义内含完整源码，可以直接复制进原项目，不需要每节下载一份项目 ZIP。

## 1. 学习目标与前置知识

第一节解决了“如何真正调用模型，以及 LangChain 帮忙封装什么”；第二节解决了“消息角色、提示词、Token 与上下文，以及如何把最近几轮对话重新发给模型”。第三节解决两个产品问题：

1. 一段解释要生成较长时间，用户怎样尽早看到已有内容？
2. 后端怎样把用户的话转换为固定字段，供下一段程序读取？

完成本节，你可以运行流式命令行、提取经过 Pydantic 校验的查询意图，并用 FastAPI 对外提供流式和 JSON 两种接口。本节只整理需求，不访问业务数据库。

前置条件：前两节的真实模型调用可用；Python 3.10+；已配置可访问的模型 API。结构化输出需要所选模型与网关支持对应能力；“兼容 OpenAI 接口”不表示支持全部能力。

本节建议分两次学习：先看第 3 节和命令行 streaming，再看第 4 节与 intent；最后完成 FastAPI 与测试。无需一次记住所有代码。

## 2. 核心术语

| 英文 | 中文 | 在本节中的作用 |
|---|---|---|
| Streaming | 流式输出 | 生成过程中分段交付结果 |
| Chunk | 数据片段 | 一次收到的一段内容，可能只有元数据 |
| Iterator / Generator | 迭代器 / 生成器 | Python 中逐次取得数据的机制 |
| Time to First Token（TTFT） | 首 Token 延迟 | 模型开始输出所需的时间；页面首次看到文字还受后续链路影响 |
| Server-Sent Events（SSE） | 服务器发送事件 | 本节后端向客户端传输 delta/done/error 事件的格式 |
| Structured Output | 结构化输出 | 将模型结果约束为约定的数据结构 |
| JSON Schema | JSON 结构规范 | 描述字段、类型、枚举和必填项 |
| Pydantic | Python 数据校验库 | 将解析结果校验为 Python 对象 |
| Validation | 校验 | 检查字段是否满足声明的约束 |

## 3. Streaming：先看产品问题，再看原理

假设用户问：“解释一下数据库索引，并举三个例子。”模型需要一段时间生成完整说明。

`invoke()` 的使用方式是等待完整回答，再一次拿到结果；`stream()` 则允许调用方迭代读取生成过程中的片段。你以前用 Node.js 的 Stream 或 `ReadableStream` 时接触过类似思想：保持一次请求，在过程中持续消费数据。

```python
# 两种调用各自会发起请求。这里只是比较，不要为了展示同一回答同时调用两次。
answer = model.invoke(messages)
print(answer.text)

for chunk in model.stream(messages):
    print(chunk.text, end="", flush=True)
```

### 3.1 这三行实际做了什么？

1. 将消息交给模型服务，请求流式返回。
2. 模型服务持续传回内容，LangChain 把它转换为 `AIMessageChunk`。
3. `for` 取得下一个 chunk；如果尚未到达，它会等待。这里的同步循环仍会阻塞当前调用线程。
4. `chunk.text` 提取可展示的文本，空文本片段可跳过。
5. `end=""` 避免每片段都换行；`flush=True` 及时刷新终端输出缓冲。

一个 chunk 不保证是一个字、一个词或一个 Token，也不能当作网络底层分包边界。它可能包含一段文字，也可能只包含结束状态或用量等元数据。不要对所有 `chunk.content` 直接做字符串拼接，因为消息内容也可能是内容块列表。

流式改善的是“多久开始看到结果”和等待体验，不保证整个回答生成得更快，也不必然减少 Token 或费用。先 `invoke()` 拿完整答案，再用 `sleep()` 逐字打印，是页面播放效果，没有获得生成过程中的提前交付。

### 3.2 四个常见方法

| 方法 | 同步 / 异步 | 取得什么 |
|---|---|---|
| `invoke()` | 同步 | 完整消息 |
| `stream()` | 同步 | 可迭代的消息片段 |
| `ainvoke()` | 异步 | `await` 取得完整消息 |
| `astream()` | 异步 | `async for` 取得消息片段 |

使用 `async` 不等于使用流式；`ainvoke()` 依然返回完整结果。流式也不要求必须使用 WebSocket。普通 HTTP 流、SSE 等都可承载单向输出；双向实时通信才可能需要进一步考虑 WebSocket。

### 3.3 多轮历史怎样处理？

第二节已经管理了最近几轮历史。传给 `stream_text(model, messages)` 的 `messages` 可以直接使用那套历史消息。`.stream()` 不会自动记住历史，也不会改变上下文窗口大小。

在原来的多轮代码中，应先在局部变量里收集流式答案，成功结束后再把用户消息与完整助手消息一起写入历史。若中途报错，页面可保留内容并标记“未完成”，正式历史暂不提交这一轮，保持第二节“失败不写入历史”的约定。不要在收到第一片段时就把整轮对话标记成功。

本节新 CLI 与 FastAPI 为单轮演示入口，保留原来的 `app.chat_cli`；暂不把服务端多用户会话存到全局列表中。

## 4. Structured Output：让下一段代码读得懂

假设用户输入：“统计上个月订单数。”自由文本回答可能是“你希望统计上个月的订单数量，我会先确认订单数据……”。人能读懂，程序却不适合依赖自然语言拆词。

我们希望得到如下数据；这是预期形状示例，具体措辞可能随模型变化：

```json
{
  "action": "query",
  "metric": "订单数",
  "time_range": "上个月",
  "questions": []
}
```

前端可以把它画成需求确认卡片，后端可以检查是否还需追问。下一阶段接入 Tool Calling 后，程序才会进一步决定可执行的操作。

如果用户只说“查一下订单”，模型应返回 `action="clarify"`，并在 `questions` 里询问时间范围与统计指标；这是一项需要用真实模型验证的业务要求。

### 4.1 四层能力要分清

| 方案 | 做了什么 | 仍需注意什么 |
|---|---|---|
| Prompt 里写“请返回 JSON” | 用文字表达格式要求 | 可能出现说明文字、代码围栏或不符合字段约定 |
| JSON mode | 服务商提供合法 JSON 格式能力 | 合法 JSON 不等于满足所有业务字段约定 |
| JSON Schema 原生结构化输出 | 支持该能力的服务商按声明的 Schema 约束输出 | 支持的 Schema 范围、模型拒绝与截断等仍需处理 |
| Pydantic 本地校验 | 检查解析后的字段、类型和明确声明的约束 | 不会自动判断全部业务含义和事实是否正确 |

本节选择“原生 JSON Schema + Pydantic 校验”，显式设置 `method="json_schema"`，避免依赖框架默认值。

### 4.2 Pydantic 类不是普通数据容器

```python
class QueryIntent(BaseModel):
    action: Literal["query", "clarify"]
    metric: str
    time_range: str
    questions: list[str]
```

`Literal` 限制 `action` 的可选值，`list[str]` 声明问题列表的类型。完整代码还通过 `ConfigDict(extra="forbid", strict=True)` 拒绝额外字段与不符合严格类型约束的输入。

这个类有两项职责：可以生成 JSON Schema，告诉模型返回的格式；也可以在本地校验解析结果。`Field(description=...)` 的文字帮助模型理解字段，却不是业务判断代码。例如 description 说“缺少时间时要追问”，不会自动生成强制执行这条规则的 Python 校验器。

模型返回 `action="delete"` 或 `questions="没有"` 会被拒绝；但若它把“上个月”误写成“本月”，两者都是字符串，字段类型检查通常无法发现错误。因此本节输出用于需求展示与后续检查，不直接作为执行授权。更详细的字段间校验、业务规则和重试会在第二周展开。

### 4.3 关键调用与执行链路

```python
structured_model = model.with_structured_output(
    QueryIntent,
    method="json_schema",
    strict=True,
)
result = structured_model.invoke(messages)
print(result.action)
print(result.model_dump())
```

`with_structured_output()` 创建一个带输出约束和解析逻辑的调用对象；这一行没有请求模型。执行 `invoke()` 时才发起请求。服务商收到消息与 Schema，返回模型结果，LangChain 再将其解析、交给 Pydantic 校验。本例成功时拿到的是 `QueryIntent` 对象，可通过属性读取，或用 `model_dump()` / `model_dump_json()` 导出。

所选网关不支持 `json_schema`、但支持 Tool Calling 时，可以显式选择 `function_calling`；本节实现提供了这个参数。它用工具调用的参数格式承载结构化结果，没有定义或执行数据库工具。若两者都不支持，需要更换有对应能力的模型，或另行设计“提示词 + JSON 解析 + 校验”方案；框架不会凭空补上供应商能力。

### 4.4 流式与结构化可以一起用吗？

可以组合，但“逐渐拼出来的 JSON 文本”和“已经通过完整校验的业务对象”是不同阶段。中途的 `{"action":` 不能作为最终结果解析并执行。不同模型、Schema 类型与解析器对增量结构化输出的支持也不同。

这一节先分别实现：流式接口交付解释文字，结构化接口等待校验完成再返回 JSON。这样能清楚观察两条链路，也便于识别错误。

## 5. 增量文件与依赖配置

在原项目中新增这些文件，保留已有文件：

| 路径 | 用途 |
|---|---|
| `projects/database-agent/app/lesson03.py` | 流式调用、查询意图与命令行入口 |
| `projects/database-agent/app/lesson03_api.py` | FastAPI SSE 与 JSON 接口 |
| `projects/database-agent/app/lesson03_client.py` | 可选：观察流式接口的终端客户端 |
| `projects/database-agent/tests/test_lesson03.py` | 不消耗模型额度的 HTTP 边界测试 |
| `projects/database-agent/requirements-s1-03.txt` | 本节验证使用的直接依赖版本 |
| `courses/week-01/S1-03-streaming-structured-output.md` | 本讲义建议在仓库中的位置 |

`app` 已在前两节建立；如果你从空目录单独试验，需要创建 `app/__init__.py`。从 `projects/database-agent` 目录运行下面所有命令，避免找不到 `app` 模块。

沿用当前已激活的虚拟环境。本节补齐依赖即可，不用删除或重新创建环境。下面版本已在 Python 3.12 验证；这是直接依赖清单，并非包含全部传递依赖的完整 lock 文件。

### 5.1 `requirements-s1-03.txt`

```text
langchain-openai==1.7.3
langchain-core==1.7.3
openai==3.41.0
pydantic==2.14.2
python-dotenv==1.2.4
fastapi==0.162.0
uvicorn==0.54.0
httpx==0.28.1
pytest==9.2.0
```

```powershell
python -m pip install -r requirements-s1-03.txt
```

本节继续读取原项目 `.env` 的三个变量：

```dotenv
LLM_API_KEY=你现有的密钥
LLM_MODEL=你已能调用的模型名
LLM_BASE_URL=你现有的兼容API地址
```

这只是变量示意。保留原来有效的值，不要用占位文字覆盖。`LLM_BASE_URL` 空白时由 SDK 使用默认地址；自建网关地址是否包含 `/v1` 取决于你原有服务。`.env` 不提交到 Git。

本节显式传入这些自定义变量，因此不要求把它们改名为 `OPENAI_API_KEY`。`load_dotenv(..., override=False)` 也会保留启动进程中已经设置的同名环境变量。

## 6. 完整可运行代码

先只创建并运行 `lesson03.py`。理解它以后，再创建 API 模块与测试。

### 6.1 `app/lesson03.py`

```python
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
```

### 6.2 关键实现解析

- `build_model()`：复用第一节的模型、密钥、地址配置；设置超时与输出上限。`max_retries=0` 让错误先显现，第三周之前不引入隐式重试；`use_responses_api=False` 延续现有 Chat Completions 接口。
- `stream_text()`：自己是生成器。调用它先取得迭代器；消费者开始迭代时才会执行函数内部的循环与请求。每次 `yield` 交出文本，下一次迭代继续执行。
- `extract_intent()`：先构造结构化调用对象，再发起真实模型请求。Schema 由 `QueryIntent` 提供，结果还要经过本地校验。
- `strict=True` 有两个不同位置：`ConfigDict` 配置 Pydantic 的本地严格类型规则；`with_structured_output` 中的参数配置供应商支持的严格 Schema 输出。这两项不是同一个开关。
- `function_calling` 分支未强制传入供应商的 strict 参数，方便显式适配支持工具调用的兼容服务；本地 Pydantic 校验依然存在。这不是所有供应商都能使用的保证。
- CLI 最外层异常捕获返回非零退出码，表示这一轮没有正常完成；不会打印包含上游请求细节的原始异常正文。

### 6.3 `app/lesson03_api.py`

```python
"""Local FastAPI adapter for S1-03; conversations are stateless here."""

import json
import logging
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ConfigDict, Field

from app.lesson03 import QueryIntent, build_model, chat_messages, extract_intent, stream_text

app = FastAPI(title="Database Agent - S1-03")
logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=4000)


class IntentRequest(ChatRequest):
    method: Literal["json_schema", "function_calling"] = "json_schema"


def get_model() -> ChatOpenAI:
    try:
        return build_model()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail="模型配置不完整") from exc


ModelDep = Annotated[ChatOpenAI, Depends(get_model)]


def sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


@app.post("/chat/stream")
def chat_stream(body: ChatRequest, model: ModelDep):
    def events():
        try:
            for text in stream_text(model, chat_messages(body.message)):
                yield sse("delta", {"text": text})
        except Exception as exc:
            logger.warning("stream failed: %s", type(exc).__name__)
            yield sse("error", {"message": "生成中断，本次回答未完成"})
            return
        yield sse("done", {})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/intent", response_model=QueryIntent)
def intent(body: IntentRequest, model: ModelDep):
    try:
        return extract_intent(model, body.message, body.method)
    except Exception as exc:
        logger.warning("intent failed: %s", type(exc).__name__)
        raise HTTPException(status_code=502, detail="模型未返回可用的查询意图") from exc
```

### 6.4 API 链路与错误处理

`POST /chat/stream` 接收用户消息，创建事件生成器，由 `StreamingResponse` 消费生成器并发送 SSE 文本。我们使用普通 `def` 和同步迭代器，框架会在线程池中处理同步流式迭代。以后改成异步方案时，应同时使用 `async def`、异步生成器与 `model.astream()`；不要在异步函数里直接跑长时间阻塞的同步模型调用。

本节自定义了三类事件：

| 事件 | `data` 示例 | 客户端含义 |
|---|---|---|
| `delta` | `{"text":"一段文字"}` | 追加内容 |
| `done` | `{}` | 生成正常结束 |
| `error` | `{"message":"生成中断，本次回答未完成"}` | 标记失败，不能当作完整回答提交 |

SSE 的事件以空行分隔；`data` 使用 JSON 编码，避免答案里的换行破坏事件边界。SSE 逻辑事件与底层网络读取分块不一定一一对应。客户端必须根据协议解析边界。

当输出已经开始，HTTP 响应头通常已经发出，不能再把状态码改成 500。因此本例在流内发 `error`，并且不发 `done`。前端必须识别事件；只看 HTTP 200 不足以判断生成成功。即使没有 error，连接突然关闭且没有 done，也应标为未完成。

配置缺失发生在响应开始之前，返回 HTTP 503；`/intent` 在返回 JSON 前遇到生成或解析失败时返回 502；请求体不满足长度或结构要求时由 FastAPI 返回 422。这是教学示例的简化映射，更细的鉴权、限流、超时与拒绝分类留待后续可靠性课程。

`X-Accel-Buffering: no` 用于提示支持它的代理关闭缓冲；它不能保证所有网络链路都不缓冲。不要在生成器之前将全部片段 `list()` 或拼接完，否则下游要等完整生成后才开始收到内容。

## 7. 运行步骤与预期结果

### 7.1 第一个实验：流式解释

```powershell
python -m app.lesson03 stream "用中文解释数据库索引，并举两个例子"
```

预期：终端边收到内容边显示。总耗时取决于模型与网络；片段到达的间隔不保证均匀。若一次显示全部内容，先比较原模型或网关的 streaming 支持与代理缓冲设置。

### 7.2 第二个实验：完整需求与缺信息的需求

```powershell
python -m app.lesson03 intent "统计上个月订单数"
python -m app.lesson03 intent "查一下订单"
```

第一条应提取指标与时间；第二条应要求补充信息。第一条的参考输出：

```json
{
  "action": "query",
  "metric": "订单数",
  "time_range": "上个月",
  "questions": []
}
```

如果网关明确不支持原生 JSON Schema，但支持工具调用，显式试用：

```powershell
python -m app.lesson03 intent "统计上个月订单数" --method function_calling
```

代码没有在失败时自动偷偷切换策略。这样可以明确观察你实际在用哪种能力。

### 7.3 第三个实验：启动 FastAPI

```powershell
python -m uvicorn app.lesson03_api:app --reload --host 127.0.0.1 --port 8000
```

访问 `http://127.0.0.1:8000/docs`，可试用 `/intent`：

```json
{"message":"统计上个月订单数","method":"json_schema"}
```

预期拿到经过校验的 JSON。试验流式展示时，用下面的客户端；API 文档页可能在收齐后才展示，不适合判断页面实时追加效果。

### 7.4 `app/lesson03_client.py`（可选）

```python
import httpx

with httpx.stream(
    "POST",
    "http://127.0.0.1:8000/chat/stream",
    json={"message": "用中文解释数据库索引，并举两个例子"},
    timeout=90,
) as response:
    response.raise_for_status()
    for line in response.iter_lines():
        print(line, flush=True)
```

另开一个已使用相同环境的终端运行：

```powershell
python -m app.lesson03_client
```

会依次看到 `event: delta`、对应 `data`，以及最后的 `event: done`。这段客户端用于观察协议，所以直接打印事件行；接入 React 时需要解析事件后把 delta 的 text 追加到状态中。

本例通过 POST 发送请求体。浏览器原生 `EventSource` 不支持用这种方式发 POST；React 端可用支持 SSE 的 fetch 客户端或实现正确的流解析。不要假设 `reader.read()` 每次取得的字节恰好是一条完整事件或一个完整汉字，需用流式 UTF-8 解码并保留跨块残余。

## 8. 测试与异常场景

下面测试替换 HTTP 网络边界，LangChain、SDK、Schema 生成与解析仍执行真实代码。它们不连接外部模型，不消耗调用额度，也不能证明你选定的供应商实际支持这些能力。

### `tests/test_lesson03.py`

```python
"""Offline tests replace HTTP transport, not the LangChain implementation."""

import json

import httpx
import pytest
from fastapi.testclient import TestClient
from langchain_openai import ChatOpenAI
from pydantic import ValidationError

from app.lesson03 import QueryIntent, chat_messages, extract_intent, stream_text
from app.lesson03_api import app, get_model


def model_for(handler):
    return ChatOpenAI(
        model="offline-test",
        api_key="offline-test-key",
        base_url="https://example.invalid/v1",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        max_retries=0,
        use_responses_api=False,
    )


def completion(payload):
    return httpx.Response(200, json={
        "id": "offline", "object": "chat.completion", "created": 0,
        "model": "offline-test",
        "choices": [{"index": 0, "finish_reason": "stop", "message": {
            "role": "assistant", "content": json.dumps(payload, ensure_ascii=False),
        }}],
    })


def chunk(text, finish=None):
    data = {
        "id": "offline", "object": "chat.completion.chunk", "created": 0,
        "model": "offline-test", "choices": [{
            "index": 0, "delta": {"content": text}, "finish_reason": finish,
        }],
    }
    return ("data: " + json.dumps(data, ensure_ascii=False) + "\n\n").encode()


def normal_stream(request):
    assert json.loads(request.content)["stream"] is True
    return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=(
        chunk("你好") + chunk("\n世界") + chunk("", "stop") + b"data: [DONE]\n\n"
    ))


class BrokenStream(httpx.SyncByteStream):
    def __iter__(self):
        yield chunk("半截答案")
        raise httpx.ReadError("offline interrupted stream")


def broken_stream(request):
    return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=BrokenStream())


def test_stream_returns_deltas_and_skips_empty_text():
    assert list(stream_text(model_for(normal_stream), chat_messages("你好"))) == ["你好", "\n世界"]


def test_stream_failure_is_not_silently_successful():
    chunks = stream_text(model_for(broken_stream), chat_messages("你好"))
    assert next(chunks) == "半截答案"
    with pytest.raises(Exception):
        next(chunks)


def test_intent_uses_native_schema_and_returns_validated_object():
    payload = {"action": "query", "metric": "订单数", "time_range": "上个月", "questions": []}

    def handler(request):
        fmt = json.loads(request.content)["response_format"]
        assert fmt["type"] == "json_schema"
        assert fmt["json_schema"]["strict"] is True
        assert fmt["json_schema"]["schema"]["additionalProperties"] is False
        return completion(payload)

    result = extract_intent(model_for(handler), "统计上个月订单数")
    assert isinstance(result, QueryIntent)
    assert result.model_dump() == payload


@pytest.mark.parametrize("changes", [
    {"action": "delete"}, {"questions": "没有"}, {"unexpected": "extra"},
])
def test_invalid_model_output_is_rejected(changes):
    payload = {"action": "query", "metric": "订单数", "time_range": "上个月", "questions": []}
    payload.update(changes)
    with pytest.raises(ValidationError):
        extract_intent(model_for(lambda request: completion(payload)), "统计订单数")


def test_api_stream_frames_text_and_signals_completion():
    app.dependency_overrides[get_model] = lambda: model_for(normal_stream)
    try:
        with TestClient(app) as client:
            response = client.post("/chat/stream", json={"message": "你好"})
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        assert 'event: delta\ndata: {"text": "你好"}\n\n' in response.text
        assert 'data: {"text": "\\n世界"}' in response.text
        assert response.text.endswith("event: done\ndata: {}\n\n")
    finally:
        app.dependency_overrides.clear()


def test_api_interruption_has_error_without_done():
    app.dependency_overrides[get_model] = lambda: model_for(broken_stream)
    try:
        with TestClient(app) as client:
            response = client.post("/chat/stream", json={"message": "你好"})
        assert "半截答案" in response.text
        assert "event: error" in response.text
        assert "event: done" not in response.text
    finally:
        app.dependency_overrides.clear()


def test_api_invalid_structured_output_returns_502():
    app.dependency_overrides[get_model] = lambda: model_for(lambda request: completion({"action": "delete"}))
    try:
        with TestClient(app) as client:
            response = client.post("/intent", json={"message": "统计订单数"})
        assert response.status_code == 502
    finally:
        app.dependency_overrides.clear()
```

运行：

```powershell
python -m pytest -q tests/test_lesson03.py
```

本讲义对应代码已验证：**9 passed**。其中包括三种不符合输出约定的参数化场景，以及“已经收到半截内容后中断”的异常路径。

真实模型联调尚未代替你执行。请使用本地原有 `.env` 完成第 7 节实验，重点检查：完整需求、缺少时间的需求、网关的 Schema 支持，以及终端是否真正逐步收到内容。

### 常见错误排查

| 现象 | 优先检查 |
|---|---|
| `ModuleNotFoundError: app` | 当前目录是否为 `projects/database-agent`，文件是否放进已有 app 目录 |
| 找不到 LangChain 或其他依赖 | `python` 是否属于当前学习项目的虚拟环境，是否执行本节依赖安装 |
| `AuthenticationError` / HTTP 401 | 原有密钥与 API 地址组合是否正确 |
| `BadRequestError` / HTTP 400 | 模型与网关是否支持 response_format、json_schema、strict 或所选工具调用方式 |
| `ValidationError` 或结构化接口 502 | 上游输出是否缺字段、类型不符、拒绝回答、被截断，或能力不兼容 |
| `APITimeoutError` / 网络异常 | API 地址、连接状况及超时；不要把半截内容当成已完成结果 |
| 命令行流式正常，网页一次显示全部 | 后端是否提前收集全部内容，客户端与反向代理是否缓冲 |
| 数据格式正确，含义却错了 | 业务规则与提取准确率；Pydantic 不会自动检查全部语义 |

## 9. 项目实践与验收

把本节新增能力理解为 Database Agent 的两个入口：`/chat/stream` 用于解释类内容，`/intent` 用于把自然语言整理为可供程序处理的查询需求。当前还没有数据库连接和执行工具，因此 `action="query"` 仅是需求分类。

动手练习：

1. **先观察片段。** 临时把终端输出改为 `print(repr(text), flush=True)`，观察片段长度是否固定，再恢复展示方式。
2. **验证格式和语义的区别。** 准备一个合法字典，把 `time_range` 改成错误但仍为字符串的“本月”，再调用 `QueryIntent.model_validate(...)`。解释为什么字段校验仍可通过。
3. **接回多轮。** 在第二节的对话入口中复用 `stream_text(model, messages)`，保留原有裁剪规则；只有成功结束才把本轮写入历史。用测试中的中断传输验证失败不提交。
4. **设计业务检查。** 思考 `action="query"` 但 `time_range="未提供"` 是否能接受；先写出规则，再考虑在第二周加跨字段验证。不要把 description 当成规则执行器。

验收标准：

- 能说明 `.stream()` 和 `invoke()` 的返回方式，解释 `yield` 与 `flush=True` 的职责。
- CLI 的 stream、intent 两种模式都能用你的模型实际运行。
- 缺信息时返回追问，并且识别这属于业务要求，而非只靠字段类型就能保证。
- FastAPI 能返回 SSE 和经过验证的 JSON；流失败有 error、没有 done。
- 本节 9 项离线测试通过，知道这些测试与真实供应商联调验证了不同内容。
- 增量代码留在原项目内，学习记录写清哪些已运行、哪些还未验证，不把“文件已准备”写成“已经掌握”。

完成本周验收时，将三节课程、新增依赖、启动与测试命令加入项目 README，并更新学习进度；本讲义本身不代表 GitHub 已提交或同步。

## 10. Summary（本节总结）

Streaming 解决分段交付问题；Structured Output 解决数据格式约定问题。LangChain 的 `stream()` 产生消息片段，`with_structured_output()` 创建带 Schema 和解析能力的调用对象；真正请求模型发生在消费流或调用 `invoke()` 时。Pydantic 检查声明过的字段约束，业务含义还需另外验证。

本节成果是 Database Agent 新增流式解释与查询意图提取能力，以及 FastAPI 对应入口和异常测试。尚未解决的部分包括服务端会话持久化、细粒度错误分类、完整业务校验与真实数据库执行。

下一节按既定安排进入 **S2-01：System/User Message 与 Prompt Template（提示词模板）**。第二周会逐步完善输出校验和错误处理，第三周再进入 Tool Calling 与 Agent 循环。

## 11. 面试题与参考答案

### 1. Streaming 会让模型更快吗？

它允许应用在完整结果产生前交付已有片段，主要改善首段内容可见时间和交互体验。完整生成耗时由模型、推理设置、输出长度、网络等共同决定，不保证下降。工程上应分别测量首段文本可见延迟、总延迟与吞吐量；输出前的模型推理也可能让用户等待一段时间。

### 2. 让模型“返回 JSON”和 Structured Output 有什么区别？

文字要求是 Prompt 层的约定；JSON mode 提供合法 JSON 格式能力；原生 Schema 模式进一步约束服务商支持的字段结构。实际应用仍应处理拒绝、截断和供应商能力差异，并对解析结果做本地校验。格式约束不能代替业务真实性检查。

### 3. 使用 Pydantic 后能直接执行模型生成的操作吗？

不能仅凭 Pydantic 校验通过就执行。它只验证你声明的类型和约束，不能自动验证用户身份、团队权限、资源访问范围、查询含义与结果事实。例如“上个月”误提为“本月”仍可能是合法字符串。数据库权限、执行限制和业务规则需要应用程序单独强制实施。

### 4. 流式接口为什么 HTTP 200 仍可能失败？

因为响应开始时状态码已经发给客户端，生成过程之后仍可能超时或断连。服务端可在已有流里发送错误事件；客户端需要区分 delta、done 和 error。如果连接结束却未收到 done，同样不能认定成功。本节选择错误后不发 done，部分答案不作为正常完成的一轮提交。

### 5. “你只实现了两个模型接口，为什么叫 Database Agent 项目？”如何回答？

应如实说明项目采用增量开发：当前阶段完成模型通信、消息组织、流式输出与结构化需求提取，尚未具备自主工具选择与执行循环。后续在相同项目中加入受控数据库工具、Tool Calling、权限检查和终止条件，再评估任务成功率与错误路径。面试时要区分规划中的功能与自己实际完成和验证的功能。

## 12. 官方参考与验证范围

代码按 2026-10-30 可访问的官方文档与上列已安装版本校对；示例业务模型、SSE 事件约定和测试用例为本课程设计。

- [LangChain Models：调用、流式与结构化输出](https://docs.langchain.com/oss/python/langchain/models)
- [LangChain ChatOpenAI 集成](https://docs.langchain.com/oss/python/integrations/chat/openai)
- [FastAPI StreamingResponse](https://fastapi.tiangolo.com/advanced/custom-response/#streamingresponse)

验证结论：9 项离线测试通过；覆盖 SDK/LangChain 在替代 HTTP 传输下的片段解析、Schema 请求与输出校验，以及 FastAPI 事件与错误映射。未调用用户的真实模型，也未连接数据库，未提交远端 GitHub。