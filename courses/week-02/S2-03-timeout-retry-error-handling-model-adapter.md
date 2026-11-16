# S2-03：超时、重试、错误分类与模型适配

> 本节继续使用 projects/database-agent。沿用现有 Python 虚拟环境、.env、模型网关和密钥配置；不重新建项目、不覆盖 .env、不把密钥提交到 GitHub。

## 1. 学习目标

完成本节后，你应该能够：

- 解释 Timeout、Retry、Backoff、Jitter 和 Error Classification。
- 区分超时、网络错误、限流、服务端错误、认证错误、请求错误和结构化输出错误。
- 判断哪些错误适合重试，哪些错误必须直接失败。
- 实现有限次数的指数退避重试，避免无限请求。
- 理解 SDK 内置重试与应用层重试的关系，避免重试叠加。
- 使用 Model Adapter（模型适配器）隔离业务代码与具体模型 SDK。
- 将统一错误格式接入 CLI 和 FastAPI。
- 使用 MockTransport 离线测试重试和异常路径，不消耗真实模型额度。

## 2. 前置知识

- S1-01：知道如何通过 API Key、模型 ID 和 Base URL 调用模型。
- S1-03：知道 LangChain ChatOpenAI、invoke 和流式调用。
- S2-01：理解 Prompt Template 和消息角色。
- S2-02：理解 Pydantic、JSON Schema、Structured Output 与校验异常。
- 知道 app/config.py 已经负责读取项目配置。

本节不连接数据库、不执行 SQL，也不执行 Tool。我们只处理模型请求这一层的可靠性。

## 3. 核心术语

| English | 中文 | 说明 |
|---|---|---|
| Timeout | 超时 | 请求超过允许的等待时间 |
| Retry | 重试 | 请求失败后再次尝试 |
| Retry Policy | 重试策略 | 定义最大次数、等待时间和可重试错误 |
| Exponential Backoff | 指数退避 | 每次重试逐步增加等待时间 |
| Jitter | 随机抖动 | 给等待时间增加随机量，避免请求同时涌向服务 |
| Error Classification | 错误分类 | 将底层异常映射为稳定的业务错误类别 |
| Transient Error | 暂时性错误 | 可能在稍后恢复的错误，如限流或服务暂时不可用 |
| Non-retryable Error | 不可重试错误 | 重试通常不能解决的错误，如认证失败、参数错误 |
| Model Adapter | 模型适配器 | 把不同模型供应商封装成统一业务接口 |
| Protocol | 接口协议 | 描述适配器必须实现哪些方法 |
| Idempotency | 幂等性 | 同一操作重复执行不会造成额外副作用 |
| Circuit Breaker | 熔断器 | 故障持续时暂时阻止请求，避免系统持续冲击下游 |

## 4. 为什么需要可靠性处理？

此前我们的调用方式大致是：

~~~python
result = structured_model.invoke(messages)
~~~

它在正常情况下可以得到结构化对象。但真实网络和模型网关并不保证每次请求成功：

- 网络连接失败。
- 网关响应慢，超过等待时间。
- 服务商触发限流，返回 429。
- 服务端临时故障，返回 5xx。
- API Key 失效，返回 401。
- 请求参数不被模型支持，返回 400。
- 模型返回的数据没有通过 Pydantic 校验。

如果所有错误都只显示“请求失败”，程序无法决定是否应该重试。如果所有错误都盲目重试，又可能让故障更严重。

因此，本节要把调用过程拆成四层：

1. **配置层**：从已有 .env 读取网关、模型、密钥和超时。
2. **模型适配层**：统一调用模型并返回 DatabaseQueryIntent。
3. **可靠性层**：分类异常，只对暂时性错误进行有限重试。
4. **业务/API 层**：接收结构化结果，向调用方返回稳定错误格式。

## 5. Timeout：超时控制

### 5.1 超时解决什么问题？

超时不是让模型更快，而是限制应用愿意等待多久。

例如：

~~~python
model = ChatOpenAI(
    model=settings.model,
    api_key=settings.api_key,
    base_url=settings.base_url,
    timeout=60,
)
~~~

这表示单次模型请求的等待时间上限为 60 秒。超过后，底层客户端会抛出超时异常。

本项目已经有以下配置：

- LLM_API_KEY：模型 API 密钥。
- LLM_MODEL：模型 ID。
- LLM_BASE_URL：模型网关基础地址。
- LLM_TIMEOUT_SECONDS：单次请求超时秒数。
- LLM_MAX_COMPLETION_TOKENS：模型最大输出 Token 数。

第六节继续读取这些变量。LLM_BASE_URL 应当是 OpenAI 兼容的 API 基础地址；如果你的网关使用自定义协议，就需要为该网关实现对应的适配器，而不能只替换 URL。

### 5.2 单次超时与整个任务的总耗时

假设单次请求 timeout=60 秒，最多尝试 3 次。总耗时可能接近：

- 第一次请求：最多 60 秒。
- 第一次等待：约 0.5 秒。
- 第二次请求：最多 60 秒。
- 第二次等待：约 1 秒。
- 第三次请求：最多 60 秒。

也就是说，单次 timeout 不等于整个业务请求的总 deadline。生产系统还需要在 API 网关、任务队列或业务服务层设置总耗时上限。

## 6. Retry：有限重试

### 6.1 为什么不能无限重试？

如果服务商已经不可用，而应用不断重试，会带来：

- 请求量进一步增加。
- 用户等待时间变长。
- Token 或请求费用增加。
- 下游服务恢复更困难。
- 多个服务层重试叠加，放大请求数量。

所以重试必须有上限。本节的 max_attempts 表示总尝试次数，包含第一次请求。

例如 max_attempts=3，意味着最多调用三次，不是第一次之外再重试三次。

### 6.2 指数退避 Exponential Backoff

本节使用：

~~~python
backoff = min(
    base_delay_seconds * (2 ** (attempt - 1)),
    max_delay_seconds,
)
~~~

假设 base_delay_seconds=0.5，max_delay_seconds=4：

| 尝试失败后 | 等待时间（不含随机抖动） |
|---|---:|
| 第一次 | 0.5 秒 |
| 第二次 | 1 秒 |
| 第三次 | 2 秒 |
| 后续 | 最高 4 秒 |

### 6.3 随机抖动 Jitter

多个客户端可能同时遇到故障。如果它们都固定等待 1 秒后重试，就可能在同一时间再次冲击网关。

因此增加随机等待：

~~~python
delay = backoff + jitter_seconds * random_value()
~~~

random_value 在 0 到 1 之间。这样不同客户端的下一次请求时间会略有差异。

生产系统还应结合服务端提供的 Retry-After 响应头、整体 deadline、并发限制和熔断机制。本节先实现基础版本。

## 7. Error Classification：错误分类

本节定义统一的错误类别：

| 错误类别 | 典型情况 | 是否自动重试 |
|---|---|---|
| timeout | 请求等待超时 | 是 |
| connection_error | 网络连接或传输失败 | 是 |
| rate_limit | HTTP 429 | 是，需控制频率 |
| server_error | HTTP 5xx | 是 |
| authentication_error | HTTP 401 / 403 | 否 |
| invalid_request | HTTP 400 等请求错误 | 否 |
| output_validation | JSON 解析或 Pydantic 校验失败 | 否 |
| unknown_error | 未识别异常 | 默认否 |

这里最重要的是：**重试不是由异常是否发生决定，而是由异常类别和重试策略共同决定。**

例如：

- 429：可能是临时限流，可以等待后重试。
- 401：API Key 错误，重复发送同一个请求不会修复密钥。
- 400：参数或模型能力不匹配，应该修复请求。
- Pydantic ValidationError：模型输出违反业务契约，简单重复请求并不一定有帮助。
- 未知异常：默认不重试，避免错误地放大故障。

未知错误采用 fail-closed（失败关闭）：不确定是否安全时，不自动重复执行。

## 8. Model Adapter：模型适配器

### 8.1 为什么需要适配层？

如果业务代码直接依赖 ChatOpenAI：

~~~python
model = ChatOpenAI(...)
result = model.with_structured_output(...).invoke(messages)
~~~

那么业务层就知道了 LangChain、ChatOpenAI 和具体结构化输出方式。以后更换模型供应商，可能需要修改很多业务代码。

本节定义一个业务接口：

~~~python
class QueryIntentModelAdapter(Protocol):
    def extract(self, user_text: str) -> DatabaseQueryIntent:
        ...
~~~

然后实现 LangChainQueryIntentAdapter：

~~~python
adapter = LangChainQueryIntentAdapter(model)
result = adapter.extract("统计上个月订单数")
~~~

业务服务只依赖 extract()，不必知道底层是哪个 SDK。

以后可以增加：
- LangChainQueryIntentAdapter：适配 LangChain ChatModel。
- CustomGatewayAdapter：适配某个自定义网关协议。
- AnotherProviderAdapter：适配其他模型供应商。

只要实现相同的 extract() 接口，业务层就可以复用。

注意：适配器并不意味着任意供应商都能直接使用同一套请求格式。OpenAI 兼容网关可以复用 ChatOpenAI；非兼容网关需要实现自己的协议转换。

## 9. 完整执行链路

~~~text
用户输入
   |
   v
ReliableQueryService.extract()
   |
   v
invoke_with_retry()
   |
   +---- 第一次尝试
   |        |
   |        v
   |   Model Adapter
   |        |
   |        v
   |   LangChain ChatModel
   |        |
   |        v
   |   已配置的模型网关
   |
   +---- 成功：返回 DatabaseQueryIntent
   |
   +---- 失败：classify_error()
             |
             +---- 不可重试 -> ModelCallError
             |
             +---- 可重试且还有次数
             |          |
             |          v
             |     Backoff + Jitter
             |          |
             |          v
             |       再次尝试
             |
             +---- 次数耗尽 -> ModelCallError
~~~

要特别注意：模型适配器负责调用模型并返回经过校验的对象；可靠性服务负责判断失败是否重试；业务/API 层负责处理最终结果。三个职责不要混在一个函数里。

## 10. 本节项目代码

### 10.1 文件结构

~~~text
projects/database-agent/
├── app/
│   ├── config.py
│   ├── lesson03.py
│   ├── lesson04.py
│   ├── lesson05.py
│   ├── lesson06.py          # 本节新增：可靠性与模型适配
│   └── lesson06_api.py      # 本节新增：统一错误的 API
└── tests/
    └── test_lesson06.py     # 本节新增：离线测试
~~~

不需要新增依赖，继续使用项目已有的 httpx、openai、langchain-core、langchain-openai、python-dotenv、pydantic、fastapi 和 pytest。

### 10.2 配置复用

本节通过 app/config.py 的 Settings.from_env() 读取原来的环境变量，并加载 projects/database-agent/.env。

不会修改或覆盖你的 .env，也不需要把 API Key 发到聊天里。

如果之前的网关已经配置在 LLM_BASE_URL，且兼容 OpenAI Chat Completions 协议，本节可以沿用。真实模型请求只会在你本地运行 CLI 或 API 时发出。

### 10.3 新增代码

- app/lesson06.py：错误分类、RetryPolicy、invoke_with_retry、QueryIntentModelAdapter、LangChainQueryIntentAdapter、ReliableQueryService 和 CLI。
- app/lesson06_api.py：FastAPI 请求模型、依赖注入和统一异常响应。
- tests/test_lesson06.py：使用 MockTransport 和测试适配器覆盖异常及成功路径。

以上代码以仓库中的文件为准，不需要复制旧课代码或替换 app/lesson03.py。

## 11. 运行步骤与预期结果

以下命令在 projects/database-agent 目录执行，沿用你之前的 Windows PowerShell 环境。

### 11.1 CLI 真实模型调用

~~~powershell
.\.venv\Scripts\python.exe -m app.lesson06 "统计上个月订单数"
~~~

默认最多尝试 3 次。成功后返回经过 Pydantic 校验的 DatabaseQueryIntent。

### 11.2 修改最大尝试次数

~~~powershell
.\.venv\Scripts\python.exe -m app.lesson06 "统计上个月订单数" --max-attempts 1
~~~

max-attempts=1 表示只调用一次，不进行重试。

### 11.3 运行离线测试

~~~powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_lesson06.py
~~~

离线测试不读取真实 API Key、不访问真实模型网关、不产生模型调用费用。

### 11.4 启动 FastAPI

~~~powershell
.\.venv\Scripts\python.exe -m uvicorn app.lesson06_api:app --reload --host 127.0.0.1 --port 8001
~~~

另开一个 PowerShell 窗口：

~~~powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8001/intent" -Method Post -ContentType "application/json" -Body '{"message":"统计上个月订单数"}'
~~~

成功时返回 JSON 结构化结果。

### 11.5 错误响应示例

如果模型请求超时且两次尝试均失败，API 会返回类似：

~~~json
{
  "error": {
    "code": "timeout",
    "message": "模型服务响应超时，请稍后重试。",
    "attempts": 2
  }
}
~~~

实际 attempts 由 RetryPolicy 决定。对外响应不会包含 API Key、完整供应商错误响应或内部请求内容。

### 11.6 常见问题

| 现象 | 排查方向 |
|---|---|
| 模型配置不完整 | 检查原有 .env 中的 LLM_API_KEY、LLM_MODEL、LLM_BASE_URL |
| 连接失败 | 检查网关地址、网络、代理和网关状态 |
| 401 / 403 | 检查密钥、账号权限和模型访问权限，不要盲目重试 |
| 400 | 检查模型 ID、参数以及网关是否支持 JSON Schema |
| 429 | 检查额度、并发和限流策略，适当延迟重试 |
| 结构化输出失败 | 检查模型或网关对 JSON Schema Structured Output 的兼容性 |
| API 超时 | 先检查 LLM_TIMEOUT_SECONDS，再结合总任务 deadline 评估 |

## 12. 关键代码解析

### 12.1 classify_error()

它把不同 SDK 和 HTTP 传输异常转换成应用自己的 ErrorCategory。

业务层不应该在每个地方重复判断 openai.RateLimitError、httpx.ReadTimeout 等底层异常。

### 12.2 RetryPolicy

它只描述策略，不执行请求。max_attempts、base_delay_seconds、max_delay_seconds 和 jitter_seconds 都是显式配置。

### 12.3 invoke_with_retry()

它接收一个可调用对象 operation。每次执行失败后：

1. 调用 classify_error()。
2. 如果不可重试，立即抛出 ModelCallError。
3. 如果可重试但已经达到最大次数，抛出 ModelCallError。
4. 否则计算退避时间并等待。
5. 重新调用 operation。

### 12.4 为什么 ChatOpenAI 的 max_retries=0？

因为本节由 invoke_with_retry() 统一管理重试。

如果 SDK 自己重试 3 次，外层业务服务又重试 3 次，请求次数可能叠加，导致请求量和等待时间难以预测。

本节关闭 SDK 隐式重试，让重试次数只有一个明确的控制点。

### 12.5 为什么需要 Protocol？

Protocol 定义业务层要求的接口，不要求适配器必须继承某个具体基类。

只要对象实现 extract()，就能被 ReliableQueryService 使用。这种方式降低了业务逻辑与供应商实现之间的耦合。

## 13. 项目实践与工程边界

本节把原来的直接模型调用升级为：

- 可配置的模型网关和单次超时。
- 有限重试与指数退避。
- 稳定的应用级错误分类。
- 独立的模型适配接口。
- CLI 和 FastAPI 共用的业务服务。

但本节还没有实现：
- 熔断器和全局并发控制。
- 对 Retry-After 的完整处理。
- 跨服务的总 deadline 和取消机制。
- 真实模型供应商之间的协议转换。
- Tool 执行的幂等性与副作用保护。

特别注意：本节的模型意图提取是无副作用请求，适合有限重试；未来执行写数据库、发邮件、提交任务等工具时，不能直接照搬重试策略。必须先考虑幂等键、重复执行保护和人工审批。

流式输出也不能在已经向用户发送部分内容后直接从头重试，否则可能重复输出。流式场景需要单独设计恢复、去重或明确失败的协议。

## 14. 测试与验收

离线测试覆盖：

- 超时、连接错误、限流、服务端错误。
- 认证错误、请求错误、结构化输出错误。
- 未知错误默认不重试。
- 临时失败后重试成功。
- 达到最大尝试次数后停止。
- 不可重试错误只调用一次。
- 非法重试策略。
- 模型网关配置、超时和 SDK 重试关闭。
- LangChain 结构化输出请求。
- FastAPI 正常响应、统一超时响应和空输入。

验收时需要在本地运行测试，并记录实际通过数量。教材已生成不代表本地测试已通过，也不代表真实模型网关已经联调成功。

## 15. Summary（本节总结）

- Timeout 限制单次请求等待时间，不等于整个业务任务的 deadline。
- Retry 必须有次数上限，并且只针对可恢复的暂时性错误。
- Exponential Backoff 逐渐增加等待时间，Jitter 减少集中重试。
- 认证失败、参数错误、Schema 校验错误和未知错误不应该盲目重试。
- Model Adapter 将业务接口与模型 SDK、供应商协议隔离。
- SDK 重试和应用层重试需要统一管理，避免次数叠加。
- 有副作用的工具必须先考虑幂等性，不能直接套用模型调用的重试方式。

## 16. 面试题与参考答案

### Q1：为什么不能对所有模型调用异常进行重试？

**参考答案：** 不同异常的恢复可能性不同。超时、网络错误、429 和部分 5xx 可能是暂时性故障；401 通常是密钥或权限问题，400 通常是请求参数问题，结构化输出校验错误则说明结果不符合业务契约。对不可恢复错误重试只会增加延迟和请求量。应先分类，再根据策略决定是否重试。

### Q2：指数退避和随机抖动分别解决什么问题？

**参考答案：** 指数退避让连续失败的请求逐步拉长等待时间，降低下游压力；随机抖动让不同客户端的重试时间分散，避免大量请求在同一时刻再次冲击服务。生产系统还要考虑 Retry-After 和总 deadline。

### Q3：为什么要关闭 SDK 内置重试？

**参考答案：** 如果 SDK 和应用服务分别执行重试，实际请求次数可能相乘，延迟也会不可预测。统一由应用层 RetryPolicy 管理，可以集中定义最大尝试次数、错误分类、日志和指标。也可以选择 SDK 统一负责重试，但不能在多个层次无约束地叠加。

### Q4：Model Adapter 如何帮助更换模型供应商？

**参考答案：** 业务层依赖稳定的 extract() 接口，而不是直接依赖某家 SDK。更换供应商时实现新的 Adapter，把请求参数、响应格式和错误映射封装在适配层，业务服务可以保持不变。但如果网关不是 OpenAI 兼容协议，就必须实现对应的协议转换，不能仅修改 Base URL。

### Q5：未来 Agent 执行数据库写入工具时，能否直接使用本节重试机制？

**参考答案：** 不能直接照搬。模型意图提取没有业务副作用，而写入工具可能已经成功执行，只是响应丢失。如果重试会产生重复写入。需要使用幂等键、唯一约束、执行记录、事务或人工审批，并区分“请求未到达”“执行失败”和“执行成功但响应丢失”。

## 17. 动手练习

1. 把默认 max_attempts 改为 2，观察失败时最多执行几次。
2. 给 classify_error() 增加一种你认为有必要单独处理的异常。
3. 实现一个 Fake Adapter：第一次抛出 ReadTimeout，第二次返回合法的 DatabaseQueryIntent。
4. 思考：如果网关返回 Retry-After: 5，应该如何修改退避策略？
5. 思考：如果工具执行已经写入数据库但响应超时，如何避免重复写入？

### 验收标准

- 能解释 max_attempts 包含第一次请求。
- 能区分可重试与不可重试错误。
- 能说明 timeout 和总 deadline 的区别。
- 能画出 Adapter、Retry Service、ChatModel 和 Gateway 的调用关系。
- 能解释为什么有副作用的 Tool 需要幂等性保护。

## 18. 本周复盘与下一节

第二周到此完成：Prompt Template、Pydantic / JSON Schema、结构化输出校验，以及超时、重试、错误分类和模型适配。

下一周进入第三周：Tool Calling 与 LangChain Agent。我们会开始学习模型如何提出工具调用、应用程序如何验证参数并真正执行工具，以及工具结果如何返回模型。
