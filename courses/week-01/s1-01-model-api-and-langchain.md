# S1-01：直接调用模型 API 与 LangChain 的区别

建议用时：90–120 分钟。目标是理解和跑通一次真实模型调用；后续每节继续扩展同一个 Database Agent 项目。

## 1. 学习目标

学完后，你应该能够：

- 解释一次模型请求从 Python 代码到服务端再返回的完整过程。
- 独立运行直接 HTTP 和 LangChain 两种调用，并说出它们的职责差异。
- 分清 HTTP 返回 JSON、JSON 内的自然语言、框架的 AIMessage 对象。
- 从环境变量配置模型地址、模型 ID 与密钥，排查认证、限流和超时。
- 说明为什么调用一次模型还没有构成能查询数据库的 Agent。

## 2. 前置知识

你已有 Python、Node.js / NestJS、React 与 MySQL 基础。本节借用你熟悉的 HTTP API、请求头、JSON 和函数调用来理解 LLM 应用，不要求机器学习训练经验。

运行需要 Python 3.12、能够安装依赖的网络，以及支持本节接口的模型服务和 API Key。还没有模型服务时，可先阅读和运行不消耗额度的测试；真实联调须在配置好服务后完成。

## 3. 核心术语

| English | 中文 | 本节中的含义 |
|---|---|---|
| LLM / Large Language Model | 大语言模型 | 根据输入上下文生成内容的模型 |
| Inference | 推理 | 使用已训练模型生成结果；本节不会训练模型 |
| API / Application Programming Interface | 应用程序接口 | 通过 HTTP 请求使用远程模型能力 |
| Endpoint | 接口端点 | 例如 POST /v1/chat/completions |
| API Key | API 密钥 | 服务识别请求方并校验访问权限的凭据 |
| Message | 消息 | 带有 role 和 content 的一条输入/输出 |
| Prompt | 提示 | 给模型的指令和上下文，不只是用户最后一句话 |
| SDK / Software Development Kit | 软件开发工具包 | 将某个服务的请求和响应包装为函数与对象 |
| LangChain | 大模型应用开发框架 | 提供模型、消息、工具等组件和组合方式 |
| AIMessage | AI 消息对象 | LangChain 表示模型输出的对象，可包含正文和元数据 |
| Token | 文本处理单位 | 模型处理文本、统计用量时使用的单位，不等于字数 |

## 4. 问题背景与适用场景

我们要为未来 Database Agent 先提供一个能力：回答数据库学习问题。第一条问题是：

> 用三句话解释什么是只读数据库账号。

现在程序没有连 MySQL，只请求模型解释概念。如果此时问“我们公司今天新增了多少客户”，模型没有获得业务数据，不能把生成的数字当成查询结果。

普通 API 的业务逻辑由开发者编写；模型生成结果还会受到消息、模型版本、生成参数等因素影响，因此成功返回 HTTP 200 不能证明内容正确。LLM 的网络响应也可以是 JSON；JSON 内既可能装自然语言，也可能装结构化结果或工具调用信息。不要把二者误解为“普通 API 返回 JSON，LLM 只能返回字符串”。

| 方案 | 适合的场景 | 需要承担的工作 / 限制 |
|---|---|---|
| 直接 HTTP | 理解协议、诊断原始请求、少量接口或特殊网关 | 自己管理请求参数、响应字段与错误 |
| 供应商 SDK | 只接一个服务，希望少写协议代码 | 仍需理解供应商参数、错误和版本 |
| LangChain | 后续需要组合提示、模型、工具和检索组件 | 多一层抽象与依赖，仍然要核对底层 API |

不是必须用框架才能构建 Agent，也不是用了 LangChain 模型就会更聪明。它主要改变应用的组织和集成方式。更换供应商有时可复用接口，但角色、工具协议、参数和扩展字段的兼容性仍要验证。

## 5. 原理与执行流程

本节对比的是两条实际路径：

| 阶段 | 直接 HTTP | LangChain |
|---|---|---|
| 业务输入 | 用户问题字符串 | 同一问题字符串 |
| 消息构建 | build_messages 生成 system / user 列表 | 同一个 build_messages |
| 接口转换 | 手动构造 headers 与 JSON | ChatOpenAI 转换消息和调用参数 |
| 网络请求 | HTTPX 发出 POST | 本节集成经 OpenAI SDK、HTTPX 发出 POST |
| 服务处理 | 服务认证、解析请求并执行模型生成 | 相同职责 |
| 输出转换 | 读取 choices[0].message.content | SDK 响应经 LangChain 转为 AIMessage，读取 content |
| 业务返回 | 校验后返回 str | 校验后返回 str |

`invoke()` 在此处是同步调用：会等到响应结束或发生异常才返回。HTTPX Client 负责连接复用，不是模型的“对话记忆”；每次新进程运行都只发送我们写入 messages 的两条消息。

### 请求里实际有什么？

协议的关键部分如下；MODEL_ID 来自你自己的配置：

```json
{
  "model": "MODEL_ID",
  "messages": [
    {"role": "system", "content": "你是数据库学习助手……"},
    {"role": "user", "content": "用三句话解释什么是只读数据库账号。"}
  ],
  "max_completion_tokens": 2048
}
```

`system` 是应用给出的行为要求，`user` 是本次问题，生成的消息通常为 `assistant`。角色支持与指令优先级须以所选模型的文档为准；有的模型还使用 `developer` 角色，本节先用常见的 system / user 文本输入。

`max_completion_tokens` 限制生成预算，不保证一定生成满额；推理模型的预算还可能包含推理 Token。如果生成被截断，本节明确报错，而不把不完整内容当作成功答案。它也不限制输入上下文长度。

### 为什么先用 Chat Completions？

本节用它来展示显式的 messages 和两种接入方式，并便于检查常见兼容接口。OpenAI 官方对新项目建议尝试 Responses API。本课程并不把 Chat Completions 当成唯一或最新接口；后续需要特定服务能力时再比较。两者请求/响应格式不同，不能只把请求 URL 改成 /responses。

## 6. 可运行代码

完整项目：[projects/database-agent](../../projects/database-agent/)。所有运行文件都在仓库中，下面展示两个实现的核心，配置、错误处理与命令行入口另有完整文件。

### 环境与依赖

使用 Python 3.12。直接依赖为 `httpx[socks]==0.28.1`、`langchain-openai==1.0.1`、`python-dotenv==1.2.1`、`pytest==8.4.2`；完整测试快照见项目 `requirements.txt`。这是本课验证的组合，不代表最新版本。这里只需安装 `langchain-openai` 集成包，不需要为了一个模型调用安装所有 LangChain 集成。

### 文件分工

| 路径 | 用途 |
|---|---|
| app/config.py | Settings.from_env 读取和校验配置 |
| app/messages.py | 统一问题、system 提示与输出文本校验 |
| app/direct_api.py | 原始 HTTP 调用实现 |
| app/langchain_api.py | LangChain 调用实现 |
| app/cli.py | 两种实现共用的入口与错误提示 |
| tests/test_model_calls.py | 正常/异常路径测试 |
| .env.example | 本地配置模板 |

### 直接 HTTP 实现

下面是 `app/direct_api.py` 的核心逻辑；完整文件还处理格式不符和输出截断：

```python
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
content = data["choices"][0]["message"]["content"]
```

### LangChain 实现

下面是 `app/langchain_api.py` 的核心逻辑；完整文件还检查结束原因和正文：

```python
llm = ChatOpenAI(
    model=settings.model,
    api_key=settings.api_key,
    base_url=settings.base_url,
    timeout=settings.timeout,
    max_retries=0,
    max_completion_tokens=settings.max_completion_tokens,
    use_responses_api=False,
    http_client=client,
)
message = llm.invoke(build_messages(question))
content = message.content
```

本节两边都显式使用 Chat Completions，并关闭自动重试以便对比。这里的 `ChatOpenAI` 是模型集成类，还没有使用 Agent 执行器。选择 `langchain` 后端不会自动接入数据库、检索系统或工具。

## 7. 运行步骤与预期结果

### 第一步：获取本课代码

当前远程同步尚未成功，请使用课程文件包解压后的代码。以下 Git 获取方式适用于课程已推送到远程之后；现在只克隆原仓库不会得到新增课文与代码。

首次获取项目时，执行：

```bash
git clone https://github.com/wan9h5/ai-agent-learn.git
cd ai-agent-learn
```

如果已经在本地克隆了仓库，先保存自己的未提交修改，再在 main 分支执行 `git pull --ff-only` 获取最新课程。

本课完整课文位于 `courses/week-01/s1-01-model-api-and-langchain.md`，配套代码位于 `projects/database-agent/`。仓库不包含真实密钥或虚拟环境。

### 第二步：安装依赖

下面按 Windows PowerShell 编写；macOS / Linux 对照项目 README。

```powershell
cd projects/database-agent
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

直接使用虚拟环境的解释器，不依赖 PowerShell 激活脚本策略。用编辑器打开 `.env`，填写真实服务的三个关键值：

```dotenv
LLM_API_KEY=replace-with-your-api-key
LLM_MODEL=replace-with-your-model-id
LLM_BASE_URL=https://api.openai.com/v1
```

MODEL 必须换成供应商控制台里你可调用的模型 ID，不要把网页聊天产品名称当成模型 ID。BASE_URL 应是官方文档中的 API 基础地址，不附加 `/chat/completions`。对其他兼容服务，需确认其支持本课的参数；兼容基础聊天不代表兼容所有高级特性。

### 第三步：先运行测试，再调用真实服务

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m app.cli --backend direct
.\.venv\Scripts\python.exe -m app.cli --backend langchain
```

pytest 无需密钥；后两条各自会发送真实请求并可能按供应商规则产生费用。预期得到类似输出：

```text
backend=direct, model=你配置的模型ID
只读数据库账号通常被授予指定范围内的读取权限。它可以查询允许访问的数据，但没有对应的写入权限。实际限制由数据库授权决定，而不是由模型提示词保证。
```

这是说明输出形态的示例，不是已经由你的账号产生的结果。真实模型措辞可能不同，也不保证严格三句话；本节先检查非空与截断，不把自然语言格式约束误当成确定性校验。

### 第四步：换一个问题

```powershell
.\.venv\Scripts\python.exe -m app.cli --backend langchain --question "为什么只读账号也需要限制可访问的表？"
```

如果失败，先看项目 README 的故障表，核对配置、状态码、网络与模型参数，保留报错文字供复盘，不要发送密钥。

## 8. 关键代码逐步解析

### Settings.from_env：配置与业务分离

相当于 NestJS 的配置模块：业务代码不硬编码密钥、地址与模型。`load_dotenv` 只是把项目 `.env` 的值加载到进程环境；`Settings.from_env()` 才读取并校验这些值。系统环境变量优先，避免本地文件覆盖部署配置。API Key 字段不会出现在 Settings 的默认 repr 中。

### build_messages：业务输入统一

两种实现都调用相同函数，保证比较时模型收到的应用指令和问题一致。空白问题先在本地拒绝，避免无意义的网络请求。system 提示说明当前没有数据库连接，但这只是在约束回答；未来数据库权限仍必须由应用和数据库强制执行。

### client.post：你熟悉的 HTTP 请求

可类比 `axios.post(url, body, {headers})`。`json=` 让 HTTPX 序列化请求正文；Bearer 认证头放的是密钥，不属于模型可读的 messages。服务端会按凭据和权限处理请求。HTTPX 的超时参数用于连接、读取等网络阶段，不能简单理解为整个任务的绝对总时长限制。

### raise_for_status 与 response.json：两种不同检查

前者处理 HTTP 4xx / 5xx，后者解析 JSON。HTTP 200 仍可能含空正文、截断输出或不符合本节约定的结构，因此后面仍需校验。认证成功、协议正确、答案正确是不同层次。

### ChatOpenAI(...) 与 invoke(...)

构造对象主要配置客户端；真正发出模型推理请求的是 `invoke`。本节实现通过 SDK 与 HTTPX 发送请求，返回 LangChain 的 `AIMessage`。正文在 `content`，其他信息可能在 `response_metadata`、`usage_metadata` 或工具调用字段中。不能把 AIMessage 当作原始 JSON，也不能假定所有任务的 content 都是字符串。

### with httpx.Client(...)：资源生命周期

进入 with 后创建本次命令使用的连接客户端；离开时关闭。CLI 调用哪一个后端，就只执行哪一个后端。后续改成长期运行的 FastAPI 服务时，应考虑按服务生命周期复用客户端，避免每个请求都重复建立连接。本节没有对话历史，因此 Client 活着也不表示模型会记住前一次问题。

## 9. 项目实践

本课代码直接放在 `projects/database-agent/app/`，是项目 A 的模型接入起点。`direct_api.ask` 和 `langchain_api.ask` 接受相同的业务问题，返回相同的业务类型 str，CLI 可选择实现。未来 FastAPI 可以复用这层调用，但异步接口中应使用合适的异步调用或线程策略，不能直接阻塞事件循环。

本节已经完成的开发范围：统一配置、消息构建、两种模型调用路径、输入/响应校验、超时和错误提示。学习者是否掌握，需在你完成练习后确认。

后续顺序：S1-02 深入 Message、Prompt、Token 与历史消息；S1-03 加流式与结构化输出；之后才接工具和数据库。当前没有用户权限、MySQL、工具执行、RAG、Memory 或 Agent 循环，因此不能查询公司真实数据。

## 10. 测试、边界条件与故障排查

自动测试使用 `httpx.MockTransport`，在网络边界检查两种实现最终发出的 POST，再返回符合协议的固定 JSON。真实 LangChain 和 SDK 仍会运行；只有外部服务被替换。生产 CLI 不使用 MockTransport。

| 测试 | 证明什么 |
|---|---|
| 正常调用的路径、认证头、model、messages | 两个后端按本课约定构造了请求 |
| 空白问题 | 本地拒绝，不发送请求 |
| 空正文 / null 正文 | 不把无内容当成成功答案 |
| finish_reason=length | 不把被截断的答案当成完整成功 |
| 401、429、超时 | 异常能够从真实调用路径传播 |
| 429 请求计数 | 本节两种路径均不会自动重复调用 |
| 缺失密钥和无效配置 | 在运行前提示可定位的问题 |

这些测试不证明你的网络可达、模型有权限或语义正确。真实联调需记录服务和模型、是否成功、响应情况，不要提交 API Key 或包含凭据的原始日志。

常见排障顺序：先看退出提示 → 检查 `.env` 是否在项目目录、是否被系统环境变量覆盖 → 核对地址与模型权限 → 核对参数 → 检查网络/配额。401 不应靠重试解决；429 可能是限流或额度不足；200 也需要验证答案内容。

## 11. 动手练习与验收标准

### 练习 A：跑通与比较

分别运行两个后端，记录各自输出；用自己的话解释“请求由哪一层发送，正文从哪里读出”。不要求两次文本一致，不用自然语言输出的逐字相等作为测试。

### 练习 B：修改业务指令

将 `app/messages.py` 中 system 提示改为“先给一句定义，再给一个 MySQL 场景”，运行两种后端。观察修改只改变消息内容，不改变 HTTP 地址和响应解析路径。提示要求不一定得到严格遵守，记录实际情况。

### 练习 C：空输入与故障

运行 `--question " "`，应得到“问题不能为空”且退出码为 1；自动测试必须仍通过。用测试中的 401、429、超时案例说明每种故障首先检查什么。无需为了练习而向真实服务故意发送无效密钥。

### 本课验收清单

- [ ] 两个后端已在本地真实调用成功，或明确记录尚未联调的原因。
- [ ] 所有自动测试通过。
- [ ] 完成练习 B，能解释修改后的数据流。
- [ ] 不看代码能说清 HTTP JSON、AIMessage 与正文字符串的差别。
- [ ] 能解释为什么当前程序不能查询 MySQL。
- [ ] 在 `docs/learning-progress.md` 填写自己的结果与尚未理解的问题。

“文件生成、自动测试通过”与“你已经掌握课程”分别记录，不自动替你勾选学习完成。

## 12. Summary（本节总结）

- 核心概念：通过模型 API 使用已训练模型；本节并不训练模型。
- 重要机制：配置 → 构造消息 → HTTP/SDK 请求 → 模型服务 → 解析响应 → 校验正文。
- LangChain 的作用：为模型调用等能力提供统一组件和组合方式，本节从 ChatOpenAI 入门。
- 适用场景：直接 HTTP 便于学习协议和排障；SDK 或 LangChain 适合减少重复集成代码，选择取决于需求。
- 常见误区：调用模型不等于构建数据库 Agent；HTTP 200 不等于答案正确；连接复用不等于对话记忆；换 base_url 不等于完全兼容所有服务。
- 本节成果：Database Agent 的模型接入层与两种可运行路径。待完成：你的真实服务联调与学习验收。下一节：消息角色、提示设计、Token 和上下文管理。

## 13. 面试题与参考答案

### Q1：不使用 LangChain，能开发 Agent 吗？

可以。核心是由应用构造上下文、调用模型、接收行动建议、校验执行工具、回传结果并控制循环结束。HTTP 或 SDK 足以实现这些机制。LangChain 提供可复用抽象，减少接入和组合工作，但不能代替对协议、安全和控制流的理解。

### Q2：直接 HTTP、SDK、LangChain 有什么区别？

HTTP 是通信方式；SDK 是面向某个服务的程序封装；LangChain 是更高层的大模型应用组件与编排框架，其模型集成可能再调用 SDK。选择取决于接口数量、抽象复用、可观测性、版本维护成本及特殊参数需求，不能只比较代码行数。

### Q3：用了 LangChain，为什么仍然会遇到 401、429、超时？

请求仍需经过真实模型服务，框架不提供额外的账号权限或网络保障。401 检查认证与服务地址，429 区分限流和额度，超时检查网络和模型延迟。本节关闭自动重试；生产环境应按错误类型设置有限重试与总预算，避免重复费用或重复副作用。

### Q4：模型返回了一段 SQL，是否代表完成了数据库查询？

没有。生成 SQL 是文本生成；实际查询还需要可信应用校验用户/团队权限、参数和可访问数据范围，使用受限数据库账号执行并处理结果。当前程序没有数据库工具，不具备执行路径。Prompt 要求“只读”不能代替数据库授权。

### Q5：两个版本收到相同问题，为什么输出不完全相同？如何测试？

生成存在随机性，服务配置或模型版本等也可能造成差异。即使设置低温度，也不应假定跨运行、跨环境完全一致。接入测试固定 HTTP 响应、检查请求契约和错误处理；真实模型评测另用事实、格式、任务成功率等标准，避免把自然语言逐字相同作为正确性条件。

## 官方参考

本课于 2026-10-29 核对以下官方资料；安装和测试的具体版本见项目 requirements.txt。

- [OpenAI Chat Completions API](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)：请求、消息与生成参数。
- [LangChain ChatOpenAI 集成](https://docs.langchain.com/oss/python/integrations/chat/openai)：安装、初始化、invoke、消息对象与 API 兼容范围。
- [HTTPX MockTransport](https://www.python-httpx.org/advanced/transports/#mock-transports)：在传输层替换外部服务响应。
