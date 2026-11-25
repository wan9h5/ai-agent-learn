# S3-01：Function Calling / Tool Calling 执行机制

## 1. 学习目标

完成本节后，你应该能够：

- 解释 Function Calling（函数调用）与 Tool Calling（工具调用）的关系。
- 区分模型提出工具调用请求和 Python 后端真正执行函数。
- 读懂 LangChain 的 \`bind_tools()\`、\`AIMessage.tool_calls\` 和 \`ToolMessage\`。
- 解释为什么工具执行结果需要带着 \`tool_call_id\` 返回模型。
- 追踪一次完整的“模型请求工具 → 后端执行 → 结果回传 → 模型回答”链路。

本节只实现一次工具调用轮次，不实现 Agent 的持续循环；循环、终止条件和最大迭代次数放在 S3-03。

## 2. 核心术语

| English | 中文 | 含义 |
|---|---|---|
| Function Calling | 函数调用 | 模型以约定格式提出函数调用请求的能力 |
| Tool Calling | 工具调用 | 更广义的工具调用机制，工具不一定只是普通函数 |
| Tool | 工具 | 应用程序允许模型请求使用的能力 |
| Tool Schema | 工具参数结构 | 工具名称、描述、参数名称和类型等定义 |
| \`bind_tools()\` | 绑定工具 | 将工具定义提供给模型 |
| \`AIMessage\` | AI 消息 | 模型返回的消息 |
| \`tool_calls\` | 工具调用列表 | AIMessage 中模型提出的工具调用请求 |
| \`ToolMessage\` | 工具消息 | 应用执行工具后，返回给模型的结果消息 |
| \`tool_call_id\` | 工具调用 ID | 将工具执行结果与对应调用请求关联起来 |

## 3. 先明确一个关键事实

LLM 不会因为看到了 Python 函数就直接运行它。

例如：

~~~python
def get_weather(city: str):
    return {"city": city, "temperature": 25}
~~~

模型可以判断应该调用 \`get_weather\`，并提出参数 \`{"city": "东京"}\`。但真正执行 Python 函数的是应用程序，而不是模型本身。

模型提出请求与应用执行请求，是两个不同的动作。

## 4. 完整执行链路

~~~text
用户
  |
  | "查询订单数的定义"
  v
Python 应用构建消息
  |
  v
model.bind_tools([lookup_metric_definition])
  |
  v
LLM 根据用户问题和工具 Schema 做判断
  |
  v
AIMessage.tool_calls
  |  name = lookup_metric_definition
  |  args = {"metric": "订单数"}
  |  id = call_xxx
  v
Python 应用检查工具白名单并执行
  |
  v
lookup_metric_definition.invoke(args)
  |
  v
ToolMessage(content=工具结果, tool_call_id=call_xxx)
  |
  | 将 AIMessage + ToolMessage 一起追加到消息历史
  v
LLM 再次处理工具结果
  |
  v
AIMessage（自然语言回答）
  |
  v
用户
~~~

## 5. 本节代码设计

新增文件：

- \`app/lesson07.py\`：工具定义、工具白名单、执行工具调用、回传 ToolMessage 和 CLI 入口。
- \`tests/test_lesson07.py\`：覆盖工具结果、未知工具、工具调用 ID、完整执行链和无需工具的直接回答。

本节工具为 \`lookup_metric_definition\`，用于查询项目内置的指标定义目录。它是一个真实执行的本地 Python 工具，但**不是数据库查询工具**：本节不会连接数据库，不执行 SQL，也不会返回真实订单数量。真实数据库 Schema、SQL 生成与只读执行将在第四周逐步实现。

## 6. 关键代码解析

### 6.1 定义工具

~~~python
@tool
def lookup_metric_definition(metric: str) -> str:
    """查询业务指标的定义、计算口径和来源表。"""
    ...
~~~

\`@tool\` 将普通 Python 函数包装成 LangChain Tool，并根据函数签名和描述生成工具 Schema。

- 函数名成为工具名称。
- 参数类型用于生成参数 Schema。
- Docstring 用于向模型说明工具用途。
- 函数体仍然是普通 Python 代码，只有被应用执行时才会运行。

### 6.2 绑定工具

~~~python
model_with_tools = model.bind_tools(list(DEFAULT_TOOLS))
ai_message = model_with_tools.invoke(messages)
~~~

\`bind_tools()\` 把工具定义交给模型，让模型知道可选工具及其参数格式。它不执行 Python 函数。

模型可能返回普通回答，也可能返回带有 \`tool_calls\` 的 AIMessage。

### 6.3 读取模型提出的调用请求

~~~python
for tool_call in ai_message.tool_calls:
    tool_name = tool_call["name"]
    tool_args = tool_call["args"]
    tool_call_id = tool_call["id"]
~~~

三个字段分别表示：

- \`name\`：模型想调用哪个工具。
- \`args\`：模型为工具生成的参数。
- \`id\`：这一次调用的关联 ID。

注意：这些字段是模型提出的请求，不代表工具已经执行。

### 6.4 应用执行工具

~~~python
selected_tool = registry.get(tool_name)
result = selected_tool.invoke(tool_args)
~~~

应用程序通过显式白名单找到工具，再调用 \`invoke()\`。不能直接对模型提供的名称使用 \`getattr\` 或执行任意代码。

本节还会把未知工具和执行异常转换为受控的错误结果。

### 6.5 创建 ToolMessage

~~~python
ToolMessage(
    content=tool_result,
    tool_call_id=tool_call_id,
    name=tool_name,
)
~~~

工具执行结果通过 ToolMessage 回传。关键是 \`tool_call_id\` 必须与模型最初提出的调用 ID 对应，否则模型和框架就无法正确关联请求与结果。

### 6.6 再次调用模型

~~~python
follow_up_messages = [
    *messages,
    ai_message,
    *tool_messages,
]
final_message = model.invoke(follow_up_messages)
~~~

这里将原始用户消息、模型的工具调用请求、工具执行结果按顺序交给模型。模型才能理解工具执行了什么、结果是什么，并组织自然语言回答。

这也是为什么工具结果不一定直接展示给用户：它首先是提供给模型继续推理的上下文。

## 7. 运行步骤

在 \`projects/database-agent\` 目录执行。

### 7.1 运行工具调用示例

~~~powershell
.\.venv\Scripts\python.exe -m app.lesson07 "查询订单数的定义和计算口径"
~~~

预期输出分为三段：

1. Model tool calls：模型提出的工具调用请求。
2. Tool messages：Python 执行工具后产生的结果，以及对应的调用 ID。
3. Final answer：模型根据工具结果组织的自然语言回答。

模型可能根据问题直接回答而不调用工具；这也是正常行为。

### 7.2 运行离线测试

~~~powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_lesson07.py
~~~

测试使用 FakeModel，不访问真实模型网关，不需要真实 API Key，也不会产生 Token 费用。

## 8. 方案边界与常见误区

1. \`bind_tools()\` 不是函数执行器，只是把工具定义提供给模型。
2. 模型提出工具调用，不代表应用必须执行；应用必须检查工具白名单、权限和参数。
3. \`AIMessage.tool_calls\` 是调用请求，\`ToolMessage\` 才是应用执行后产生的工具结果消息。
4. \`tool_call_id\` 用于关联调用请求和工具结果。
5. 工具返回结构化数据并不意味着必须原样展示给用户；可以交给模型解释，也可以由后端直接展示。
6. 本节只有一次工具调用轮次，不是完整 Agent 循环。持续循环和终止条件属于 S3-03。

## 9. Summary

- Function Calling / Tool Calling 描述的是模型提出工具调用请求的机制。
- 模型负责理解问题、选择工具和生成参数。
- Python 应用负责检查请求、执行函数并产生结果。
- 应用通过 ToolMessage 将结果交还模型。
- 模型读取工具结果后，可以生成更适合用户理解的自然语言回答。
- \`bind_tools()\`、\`AIMessage.tool_calls\`、工具的 \`invoke()\` 和 \`ToolMessage\` 构成了本节最重要的执行链路。

## 10. 面试题

### Q1：调用 bind_tools() 后，工具会立即执行吗？

参考答案：不会。bind_tools() 将工具定义和参数 Schema 绑定到模型，使模型能够提出工具调用请求。实际执行仍由应用程序完成。

### Q2：AIMessage.tool_calls 和 ToolMessage 有什么区别？

参考答案：AIMessage.tool_calls 是模型提出的工具调用请求，包含工具名称、参数和调用 ID；ToolMessage 是应用执行工具后产生的结果消息，并通过 tool_call_id 与请求关联。

### Q3：为什么不能直接根据模型返回的工具名称执行任意函数？

参考答案：模型输出是不可信输入。应用必须使用显式工具白名单，并校验权限和参数，不能让模型任意调用系统函数或执行代码。

### Q4：为什么工具执行结果要再次传给模型？

参考答案：模型需要读取工具结果，才能基于真实执行结果继续分析并组织最终回答。如果后续业务不需要模型解释，应用也可以选择直接处理或展示工具结果。

### Q5：本节的执行流程与完整 Agent 循环有什么区别？

参考答案：本节只执行一次“模型请求工具—应用执行—结果回传—模型回答”的流程。完整 Agent 循环还要判断模型是否继续请求工具、是否结束任务，并设置最大迭代次数和终止条件。

## 11. 动手练习与验收标准

- 能指出 \`bind_tools()\`、\`tool_calls\`、工具 \`invoke()\` 和 \`ToolMessage\` 分别发生在哪一步。
- 能解释模型为什么不直接执行 Python 函数。
- 能解释 \`tool_call_id\` 的作用。
- 能运行 CLI 示例和全部离线测试。
- 能区分本节的单轮工具调用与 S3-03 的 Agent 循环。

完成以上标准后，再进入 S3-02。
