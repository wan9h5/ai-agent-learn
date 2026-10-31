# Database Agent：持续演进的课程项目

当前阶段：**S1-01 模型接入层 + S1-02 多轮对话 + S1-03 流式输出与结构化输出**。提供两个真实模型调用实现与一个 LangChain 多轮入口。单次 CLI 不保存历史；多轮 CLI 在当前进程保留有限轮次。当前没有数据库连接、SQL 执行、工具循环或历史持久化。

完整中文讲解：[S1-01 课程](../../courses/week-01/s1-01-model-api-and-langchain.md)。

第二课：[S1-02 消息、Prompt、Token 与上下文](../../courses/week-01/s1-02-messages-prompt-context.md)。

## S1-02 多轮对话

在下方环境安装与配置完成后，于本项目目录执行（Windows）：

```powershell
.\.venv\Scripts\python.exe -m app.chat_cli --keep-turns 3
```

macOS / Linux 用 `.venv/bin/python -m app.chat_cli --keep-turns 3`。输入问题开始真实调用；`/history` 查看保留的消息，`/reset` 清空历史但保留 system，`/exit` 退出。命令本身不调用模型，每个普通问题调用一次。失败的本轮不保存，之前成功轮次仍保留。

`keep-turns` 只限制轮数，不是 Token 上限。输入包含 system、最多 N 轮历史和当前问题；成功后只保存最近 N 轮。Token 用量读取自服务返回值，缺失时显示未知。退出进程后历史清空；多个用户需要独立会话，不能共用一个全局列表。

如果 Copy-Item 不适用于你的终端，可以直接在编辑器里复制 `.env.example` 并重命名为 `.env`；已有 `.env` 则保留原配置。

## S1-03：Streaming 与 Structured Output

完整课程：[S1-03 中文讲解](../../courses/week-01/S1-03-streaming-structured-output.md)。

本节在原项目中增量增加流式调用、Pydantic 查询意图、FastAPI SSE / JSON 接口和离线测试。沿用现有虚拟环境与 `.env`，不要重新创建环境，也不要覆盖已有密钥配置。

### 安装本节依赖

在当前项目目录（`projects/database-agent`）执行：

```powershell
python -m pip install -r requirements-s1-03.txt
```

这是本节的直接依赖清单，不是完整 lock 文件；它可能升级当前虚拟环境中的 LangChain、OpenAI SDK、Pydantic 和 FastAPI 版本。原来的 `requirements.txt` 保留不变。

### 命令行实验

```powershell
python -m app.lesson03 stream "用中文解释数据库索引，并举两个例子"
python -m app.lesson03 intent "统计上个月订单数"
python -m app.lesson03 intent "查一下订单"
python -m app.lesson03 intent "统计上个月订单数" --method function_calling
```

`stream` 会逐段输出文本；`intent` 返回经过 Pydantic 校验的查询意图。若网关不支持 JSON Schema 但支持 Tool Calling，可显式试用 `--method function_calling`。代码不会在失败时自动切换方法。

### FastAPI 接口

```powershell
python -m uvicorn app.lesson03_api:app --reload --host 127.0.0.1 --port 8000
```

打开 `http://127.0.0.1:8000/docs`，可调用 `POST /intent`；流式接口为 `POST /chat/stream`。可选终端客户端：

```powershell
python -m app.lesson03_client
```

### 离线测试

```powershell
python -m pytest -q tests/test_lesson03.py
```

测试使用 MockTransport，不调用真实模型、不消耗 API 额度。真实模型与网关能力仍需在本地用自己的配置验证。

### 本节新增文件

- `app/lesson03.py`：流式调用、结构化查询意图和 CLI。
- `app/lesson03_api.py`：SSE 流式接口与 JSON 意图接口。
- `app/lesson03_client.py`：可选的 SSE 终端客户端。
- `tests/test_lesson03.py`：流式、Schema、异常与 API 测试。
- `requirements-s1-03.txt`：本节增量直接依赖。

## 环境与安装

建议使用 Python 3.12。本节自动测试在 Python 3.12.14 上执行；依赖版本是本节验证快照，不代表最新版本。

从仓库根目录进入项目，后续命令均在此目录执行：

```powershell
cd projects/database-agent
python -m venv .venv
# Windows PowerShell：无需激活虚拟环境，直接指定解释器即可。
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

macOS / Linux：

```bash
cd projects/database-agent
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
```

编辑 `.env`：填写你自己的 API Key 和有权限调用的模型 ID。默认地址为 OpenAI 官方 API；如果使用其他服务，按其官方文档配置基础地址，并核对 Chat Completions 兼容性。

```dotenv
LLM_API_KEY=replace-with-your-api-key
LLM_MODEL=replace-with-your-model-id
LLM_BASE_URL=https://api.openai.com/v1
LLM_TIMEOUT_SECONDS=60
LLM_MAX_COMPLETION_TOKENS=2048
```

占位符不会被当成可用配置。不要把密钥发到聊天里或写进 Git。系统环境变量优先于 `.env`；已有同名环境变量时，修改 `.env` 不会覆盖它。

## 两种调用

Windows PowerShell：

```powershell
.\.venv\Scripts\python.exe -m app.cli --backend direct
.\.venv\Scripts\python.exe -m app.cli --backend langchain
.\.venv\Scripts\python.exe -m app.cli --backend direct --question "为什么只读账号也要限制可以访问的表？"
```

macOS / Linux：

```bash
.venv/bin/python -m app.cli --backend direct
.venv/bin/python -m app.cli --backend langchain
```

每条命令成功时发送一次模型请求，按供应商规则计费。默认关闭 SDK 自动重试，便于观察一次请求。输出类似：

```text
backend=direct, model=你配置的模型ID
只读数据库账号通常只有指定数据范围内的读取权限……
```

文字由真实模型生成，不要求两个版本逐字一致。两次调用分别生成结果，并未共享历史或对话状态。失败时输出中文提示并以状态码 1 退出。

## 不需要密钥的测试

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

macOS / Linux 用 `.venv/bin/python -m pytest -q`。

测试使用真实 LangChain / OpenAI SDK，经 HTTPX MockTransport 拦截请求并返回测试 JSON；没有真实模型推理和扣费。覆盖请求路径、认证头、消息、空输入、空响应、截断、401、429、超时、无密钥和无效配置。它们验证接入代码契约，不证明供应商可达或模型答案正确。

## 文件导航

| 文件 | 作用 |
|---|---|
| `app/config.py` | 从环境变量读取并校验配置 |
| `app/messages.py` | 统一两种实现的 system / user 消息 |
| `app/direct_api.py` | 手动发送 HTTP、读取 Chat Completions JSON |
| `app/langchain_api.py` | 使用真实 ChatOpenAI，将 AIMessage 转为业务文本 |
| `app/cli.py` | 命令行入口、资源关闭与中文故障提示 |
| `tests/test_model_calls.py` | 不调用外部服务的契约与异常测试 |
| `requirements.in` | 本节直接依赖 |
| `requirements.txt` | 验证环境的完整依赖版本快照 |

## 常见问题

| 现象 | 排查 |
|---|---|
| 提示缺少 LLM_API_KEY / LLM_MODEL | 检查是否已复制 `.env.example`，并填写非占位值 |
| 401 | 密钥是否属于当前地址对应的服务，是否有效 |
| 403 / 404 | 模型权限、模型 ID、接口基础路径是否正确 |
| 400 | 模型/服务是否支持 system 消息和 max_completion_tokens；不要只换模型名而忽略参数差异 |
| 429 | 可能是限流，也可能是配额/余额问题；去供应商控制台确认 |
| 超时 / 连接失败 | 检查网络、代理、基础地址与证书；可按实际情况调整超时 |
| 没有文本 / 输出截断 | 检查模型是否拒绝、是否返回非文本；推理模型可能先消耗推理 Token，需增加输出预算 |
| `No module named app` | 当前工作目录应是 `projects/database-agent` |
| `No module named langchain_openai` | 使用虚拟环境的 Python 安装依赖并运行 |
| 修改 `.env` 没生效 | 检查是否已有同名系统环境变量；命令启动时会重新读取配置 |

本项目包含 SOCKS 代理支持依赖，但不会自动替你配置代理。不要用关闭证书校验来解决连接问题。

## 当前验证边界

已执行的检查记录在 [学习进度](../../docs/learning-progress.md)。维护者生成此课程时未使用你的真实密钥，未验证你的模型账户、网络或额度。真实服务联调由你在本地完成后再记录。
