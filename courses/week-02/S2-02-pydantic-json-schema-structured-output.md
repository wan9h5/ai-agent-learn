# S2-02：Pydantic、JSON Schema 与结构化输出校验

> 本节继续使用 projects/database-agent。沿用原来的 Python 虚拟环境和 .env，不重新创建项目，不覆盖前三节和 S2-01 的代码。

## 1. 学习目标

完成本节后，你应该能够：

- 解释 Pydantic、JSON Schema、Structured Output 三者之间的关系。
- 使用 Pydantic BaseModel 定义模型输出的数据结构。
- 使用 Field 描述字段含义，使用 field_validator 和 model_validator 实现业务校验。
- 使用 model_json_schema() 生成 JSON Schema。
- 使用 with_structured_output() 将 Schema 交给模型，并取得经过解析的 Pydantic 对象。
- 区分“JSON 格式正确”“字段类型正确”和“业务逻辑正确”。
- 通过离线测试验证缺字段、错误类型、多余字段和跨字段约束。

## 2. 前置知识

- S1-03：已经见过 Pydantic BaseModel、QueryIntent 和 with_structured_output()。
- S2-01：已经理解 ChatPromptTemplate、System/User Message 和动态变量。
- 知道 model.invoke() 负责调用模型，Prompt Template 负责组织消息。
- 本节不连接数据库、不执行 SQL，也不调用 Tool。

## 3. 核心术语

| English | 中文 | 说明 |
|---|---|---|
| Structured Output | 结构化输出 | 要求模型按指定结构返回数据 |
| Pydantic | Python 数据校验库 | 定义数据模型并在运行时校验 |
| BaseModel | 基础模型类 | Pydantic 数据模型的基类 |
| Field | 字段定义 | 描述字段用途、约束和 Schema 元信息 |
| Validator | 校验器 | 在数据进入业务流程前检查数据 |
| field_validator | 字段校验器 | 校验单个字段 |
| model_validator | 模型校验器 | 校验多个字段之间的关系 |
| JSON | 数据交换格式 | 模型与应用之间常用的结构化文本格式 |
| JSON Schema | JSON 结构规范 | 描述 JSON 对象的字段、类型和约束 |
| strict mode | 严格模式 | 要求模型输出符合指定 Schema |
| Serialization | 序列化 | 把 Python 对象转换成 JSON 或字典 |
| Deserialization | 反序列化 | 把 JSON 数据解析成 Python 对象 |

## 4. 为什么需要结构化输出？

先看一个普通模型调用：

~~~python
response = model.invoke("统计上个月订单数")
print(response.content)
~~~

模型可能返回：

~~~text
用户希望统计上个月的订单数量。
~~~

也可能返回：

~~~text
我理解你想查询订单数量，但还需要确认订单状态。
~~~

对于人来说，这两段话都能理解。但对于后端程序来说，它们只是字符串。后端需要自己猜测：

- 当前是可以查询，还是需要继续追问？
- 用户想查询的指标是什么？
- 时间范围是什么？
- 有没有筛选条件？
- 需要向用户追问什么？

如果后端用字符串包含判断、正则表达式或一堆 if/else 去解析自然语言，程序会越来越脆弱。

我们希望模型返回类似下面的数据：

~~~json
{
  "action": "query",
  "metric": "订单数",
  "time_range": "上个月",
  "filters": [
    {
      "column": "status",
      "operator": "eq",
      "value": "paid"
    }
  ],
  "questions": []
}
~~~

这样后端就能直接读取 action、metric、time_range 等字段。

但注意：**返回 JSON 不等于返回的数据一定正确。** 还需要检查字段、类型和业务约束。

## 5. Pydantic、JSON Schema 和 Structured Output 的关系

可以把三者理解成三个不同层次：

### 5.1 Pydantic：在 Python 应用中定义数据模型

~~~python
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal

class QueryIntent(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    action: Literal["query", "clarify"]
    metric: str = Field(description="用户希望查询的指标")
    questions: list[str]
~~~

Pydantic 模型不仅描述字段，还能在 Python 程序运行时检查数据是否合法。

### 5.2 JSON Schema：把数据模型转换成标准结构说明

~~~python
schema = QueryIntent.model_json_schema()
print(schema)
~~~

Pydantic 会根据模型定义生成 JSON Schema。它描述：

- 对象有哪些字段。
- 每个字段是什么类型。
- 哪些字段是必填的。
- 是否允许额外字段。
- 枚举字段允许哪些值。
- 嵌套对象的结构是什么。

JSON Schema 是模型和后端都能理解的结构契约，不是数据库 Schema，也不是 SQL。

### 5.3 Structured Output：把 Schema 用到模型调用中

~~~python
structured_model = model.with_structured_output(
    QueryIntent,
    method="json_schema",
    strict=True,
)

result = structured_model.invoke(messages)
~~~

这一步把 Pydantic 模型作为结构化输出约束交给 LangChain / 模型供应商。模型返回后，LangChain 会解析结果；使用 Pydantic 类作为 Schema 时，正常结果会成为对应的 Pydantic 对象。

所以完整关系是：

1. 开发者定义 Pydantic Model。
2. Pydantic 生成 JSON Schema。
3. with_structured_output() 把结构化约束应用到模型调用。
4. 模型按照 Schema 返回结构化结果。
5. LangChain 解析结果，Pydantic 再执行本地数据校验。
6. 后端读取经过校验的对象，决定下一步业务流程。

## 6. 三种校验：格式、字段与业务逻辑

这是本节最重要的区分。

### 6.1 JSON 格式校验

例如下面不是合法 JSON：

~~~text
{action: query, metric: 订单数}
~~~

JSON 的对象键和字符串值必须使用双引号。格式错误时，解析阶段就会失败。

### 6.2 字段与类型校验

例如：

~~~json
{
  "action": "query",
  "metric": 123,
  "time_range": "上个月",
  "filters": [],
  "questions": []
}
~~~

JSON 本身是合法的，但 metric 应该是字符串，不能是数字。

Pydantic 的 strict=True 会拒绝这类类型错误，而不是尝试把数字转换成字符串。

### 6.3 业务逻辑校验

例如：

~~~json
{
  "action": "clarify",
  "metric": "订单数",
  "time_range": "上个月",
  "filters": [],
  "questions": []
}
~~~

字段类型都正确，但 action=clarify 表示需要澄清，questions 却是空数组。这在业务上自相矛盾。

这种跨字段约束需要 model_validator 来检查。

**结论：JSON Schema 描述结构契约，Pydantic 负责本地数据校验，业务校验器负责检查字段之间是否符合业务规则。**

## 7. 本节项目代码

### 7.1 文件结构

~~~text
projects/database-agent/
├── app/
│   ├── lesson03.py
│   ├── lesson04.py
│   └── lesson05.py          # 本节新增
└── tests/
    ├── test_lesson04.py
    └── test_lesson05.py     # 本节新增
~~~

不需要新增依赖。继续使用原来的虚拟环境、langchain-openai、langchain-core 和 Pydantic。

### 7.2 完整代码：app/lesson05.py

~~~python
"""S2-02: Pydantic, JSON Schema, and validated structured output."""

import argparse
import json
import sys
from typing import Literal

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from app.lesson03 import build_model


class FilterCondition(BaseModel):
    """A typed filter description; it is not executable SQL."""

    model_config = ConfigDict(extra="forbid", strict=True)

    column: str = Field(description="列名，只能描述用户明确提到的筛选字段")
    operator: Literal["eq", "ne", "gt", "gte", "lt", "lte", "contains", "in"] = Field(
        description="比较操作符"
    )
    value: str = Field(description="筛选值；多个 in 值用逗号分隔")


class DatabaseQueryIntent(BaseModel):
    """A validated business-level description of a database query request."""

    model_config = ConfigDict(extra="forbid", strict=True)

    action: Literal["query", "clarify"] = Field(
        description="需求足够明确时为 query；缺少必要信息时为 clarify"
    )
    metric: str = Field(description="用户希望查询的对象或指标，例如订单数、销售额")
    time_range: str = Field(description="用户提供的时间范围；未说明时填写未指定")
    filters: list[FilterCondition] = Field(
        description="用户明确提出的筛选条件；没有筛选条件时返回空数组"
    )
    questions: list[str] = Field(
        description="需要向用户澄清的问题；action=query 时必须为空数组"
    )

    @field_validator("metric", "time_range")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("该字段不能为空或只包含空白字符")
        return value

    @field_validator("questions")
    @classmethod
    def questions_must_not_be_blank(cls, value: list[str]) -> list[str]:
        cleaned = [question.strip() for question in value]
        if any(not question for question in cleaned):
            raise ValueError("questions 中不能包含空问题")
        return cleaned

    @model_validator(mode="after")
    def validate_action_consistency(self):
        if self.action == "query":
            if self.metric.casefold() in {"未提供", "未知", "unknown", "not provided"}:
                raise ValueError("action=query 时必须提供明确的 metric")
            if self.questions:
                raise ValueError("action=query 时 questions 必须为空数组")
        elif not self.questions:
            raise ValueError("action=clarify 时至少需要一个澄清问题")
        return self


SYSTEM_PROMPT = """你是一个 Database Agent 的需求解析模块。
你只负责把用户的自然语言需求转换成结构化的查询意图，不负责执行查询。

规则：
1. 严格按照提供的结构化 Schema 返回结果。
2. action 只能是 query 或 clarify。
3. 用户没有明确说明的时间范围填写“未指定”，不要自行推算日期。
4. filters 只能记录用户明确提出的筛选条件，不要擅自补充条件。
5. 如果指标不明确，或无法形成可执行的查询需求，选择 clarify，并提出具体问题。
6. action=query 时 questions 必须为空数组；action=clarify 时 questions 至少包含一个问题。
7. 不生成 SQL，不连接数据库，不编造数据库表、字段或查询结果。
"""


def build_structured_model(model: BaseChatModel):
    """Bind a Pydantic schema to the model using native JSON Schema output."""
    return model.with_structured_output(
        DatabaseQueryIntent,
        method="json_schema",
        strict=True,
    )


def validate_json(raw_json: str) -> DatabaseQueryIntent:
    """Parse JSON text and run Pydantic field and cross-field validation."""
    if not isinstance(raw_json, str) or not raw_json.strip():
        raise ValueError("JSON 输入不能为空。")
    return DatabaseQueryIntent.model_validate_json(raw_json)


def validate_payload(payload: dict) -> DatabaseQueryIntent:
    """Validate an already-decoded Python dictionary."""
    return DatabaseQueryIntent.model_validate(payload)


def extract_query_intent(
    model: BaseChatModel,
    user_text: str,
) -> DatabaseQueryIntent:
    """Ask the model for a structured intent and return a validated Pydantic object."""
    if not isinstance(user_text, str) or not user_text.strip():
        raise ValueError("用户输入不能为空。")

    structured_model = build_structured_model(model)
    result = structured_model.invoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=user_text.strip()),
    ])

    if not isinstance(result, DatabaseQueryIntent):
        raise TypeError("模型没有返回 DatabaseQueryIntent，请检查模型供应商的结构化输出支持。")

    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="S2-02：Pydantic、JSON Schema 与结构化输出校验"
    )
    parser.add_argument(
        "mode",
        choices=["schema", "validate", "extract"],
        help="schema 查看 Schema；validate 离线校验 JSON；extract 调用真实模型",
    )
    parser.add_argument(
        "value",
        nargs="?",
        help="validate 模式传入 JSON 字符串；extract 模式传入用户需求",
    )
    args = parser.parse_args(argv)

    try:
        if args.mode == "schema":
            if args.value is not None:
                parser.error("schema 模式不需要第二个参数。")
            print(json.dumps(
                DatabaseQueryIntent.model_json_schema(),
                ensure_ascii=False,
                indent=2,
            ))
            return 0

        if not args.value or not args.value.strip():
            parser.error(f"{args.mode} 模式必须提供非空参数。")

        if args.mode == "validate":
            result = validate_json(args.value)
        else:
            result = extract_query_intent(build_model(), args.value)

        print(result.model_dump_json(indent=2))
        return 0

    except ValidationError as exc:
        print(
            json.dumps(exc.errors(include_input=False), ensure_ascii=False, indent=2),
            file=sys.stderr,
        )
        return 1
    except Exception as exc:
        print(
            f"执行失败（{type(exc).__name__}）。请检查输入、模型配置、网络或模型服务。",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
~~~

### 7.3 关键实现解析

**第一步：定义嵌套模型**

- FilterCondition 描述一个筛选条件。
- DatabaseQueryIntent 描述完整的查询意图。
- filters 是 FilterCondition 列表，因此每个筛选项也会被单独校验。

这里的 FilterCondition 只是查询意图的数据结构，不是 SQL，也不具备执行能力。

**第二步：配置严格校验**

~~~python
model_config = ConfigDict(extra="forbid", strict=True)
~~~

- extra="forbid"：不接受 Schema 中没有定义的额外字段。
- strict=True：不自动进行宽松类型转换。

例如 metric 应该是字符串，传入 123 会校验失败。

**第三步：字段校验**

~~~python
@field_validator("metric", "time_range")
@classmethod
def text_must_not_be_blank(cls, value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("该字段不能为空")
    return value
~~~

field_validator 检查单个字段。这里要求指标和时间范围不能是空字符串或纯空格。

**第四步：跨字段校验**

~~~python
@model_validator(mode="after")
def validate_action_consistency(self):
    if self.action == "query" and self.questions:
        raise ValueError("action=query 时 questions 必须为空数组")
    if self.action == "clarify" and not self.questions:
        raise ValueError("action=clarify 时至少需要一个澄清问题")
    return self
~~~

model_validator 能同时访问模型中的多个字段，适合检查业务状态是否一致。

注意：这些 Python Validator 并不会自动全部变成 JSON Schema 约束。模型收到 Schema 后，仍然需要由本地 Pydantic 再检查业务逻辑。

**第五步：生成 JSON Schema**

~~~python
schema = DatabaseQueryIntent.model_json_schema()
~~~

这一行是 Pydantic 根据模型定义生成 JSON Schema。它不是模型返回的结果，而是开发者提前定义的输出规范。

**第六步：调用结构化模型**

~~~python
structured_model = model.with_structured_output(
    DatabaseQueryIntent,
    method="json_schema",
    strict=True,
)
result = structured_model.invoke(messages)
~~~

这里传入的是 Pydantic 类，不是 JSON 字符串。LangChain 会基于它生成结构化输出约束，并把正常响应解析成 DatabaseQueryIntent 对象。

**第七步：读取对象**

~~~python
print(result.action)
print(result.metric)
print(result.model_dump())
print(result.model_dump_json(indent=2))
~~~

- model_dump()：转换成 Python dict。
- model_dump_json()：转换成 JSON 字符串。
- result.metric：直接读取对象属性。

## 8. 完整执行链路

~~~mermaid
flowchart TD
    A[定义 Pydantic Model] --> B[model_json_schema]
    B --> C[生成 JSON Schema]
    C --> D[with_structured_output]
    E[用户自然语言输入] --> F[构造 System / User Message]
    D --> G[结构化模型 Runnable]
    F --> G
    G --> H[模型返回结构化内容]
    H --> I[LangChain 解析]
    I --> J[Pydantic 字段与类型校验]
    J --> K[model_validator 业务校验]
    K --> L[DatabaseQueryIntent 对象]
    L --> M[后端读取字段并决定下一步]
~~~

注意几个容易混淆的地方：

1. model_json_schema() 生成 Schema，不会调用 LLM。
2. with_structured_output() 创建结构化模型调用入口，不代表此时已经发起请求。
3. invoke() 才真正调用模型。
4. 正常返回时 result 是 Pydantic 对象，不是给终端用户展示的最终自然语言答案。
5. 校验失败时应该阻止后续业务流程，不能把无效数据当作成功结果。

## 9. 运行步骤

以下命令都在 projects/database-agent 目录执行，沿用之前的 .venv 和 .env。

### 9.1 查看 JSON Schema，不调用模型

Windows PowerShell：

~~~powershell
.\\.venv\\Scripts\\python.exe -m app.lesson05 schema
~~~

你会看到由 Pydantic 自动生成的 JSON Schema，其中包含字段、类型、必填项、枚举和嵌套 FilterCondition。

### 9.2 离线校验一份正确的 JSON

~~~powershell
.\\.venv\\Scripts\\python.exe -m app.lesson05 validate '{"action":"query","metric":"订单数","time_range":"上个月","filters":[{"column":"status","operator":"eq","value":"paid"}],"questions":[]}'
~~~

预期：命令成功，输出格式化后的 JSON。

### 9.3 尝试一份业务不合法的 JSON

~~~powershell
.\\.venv\\Scripts\\python.exe -m app.lesson05 validate '{"action":"clarify","metric":"订单数","time_range":"上个月","filters":[],"questions":[]}'
~~~

预期：命令失败，提示 action=clarify 时至少需要一个澄清问题。

### 9.4 调用真实模型

~~~powershell
.\\.venv\\Scripts\\python.exe -m app.lesson05 extract "统计上个月已支付订单数"
~~~

这一步会使用原来的 .env 配置并发起真实模型请求，可能产生 Token 消耗或费用。模型供应商和模型 ID 必须支持当前使用的 JSON Schema Structured Output。

### 9.5 运行离线测试

~~~powershell
.\\.venv\\Scripts\\python.exe -m pytest -q tests/test_lesson05.py
~~~

测试使用 HTTPX MockTransport 替换网络响应，不会访问真实模型服务，也不会消耗真实 API 额度。

## 10. 本节测试覆盖

test_lesson05.py 覆盖：

- 正确 JSON 转换成 Pydantic 对象。
- JSON Schema 包含全部必填字段，并拒绝额外字段。
- 缺少字段时校验失败。
- 字段类型错误时校验失败。
- 顶层和嵌套对象出现多余字段时校验失败。
- action 与 questions 之间的业务约束。
- 空指标校验失败。
- 模型请求使用 strict JSON Schema。
- 模型返回违反业务约束的数据时，后端拒绝接受。
- 用户输入为空时，不应该调用模型。

## 11. 和第三节、第四节的关系

| 已有知识 | 本节如何继续使用 |
|---|---|
| S1-03 的 QueryIntent | 作为最初的结构化输出示例；本节增加嵌套结构和业务校验 |
| S1-03 的 build_model() | 继续复用原模型配置，不创建第二套客户端 |
| S2-01 的 System/User Message | 本节仍然通过明确的消息角色传入任务指令和用户需求 |
| S2-01 的 Prompt Template | 后续可以把结构化解析的 System Prompt 也抽成模板 |
| 本节的 Pydantic 对象 | 后续 Tool Calling 可以使用它作为业务输入，但仍需重新校验权限和参数 |

### Structured Output 和 Tool Calling 有什么区别？

这是进入下一阶段前必须区分的概念：

- Structured Output：让模型按照约定结构返回数据，例如 action、metric、time_range。
- Tool Calling：模型提出调用某个工具的请求，应用程序检查并执行工具，再把工具结果交还给模型。

Structured Output 返回一个可供程序读取的对象，不代表模型已经调用了数据库工具；Tool Calling 才会进入工具请求和执行链路。

即使进入 Tool Calling，后端也不能因为参数通过 Pydantic 校验就直接执行。还需要检查用户身份、团队权限、数据库范围、SQL 安全规则、超时和审批要求。

## 12. 常见误区

1. **JSON 合法就代表数据正确。** 不对。JSON 语法正确，字段和业务逻辑仍可能错误。
2. **JSON Schema 就是 Pydantic。** 不对。Pydantic 是 Python 数据建模与校验工具；JSON Schema 是描述 JSON 结构的标准规范。
3. **strict=True 能保证模型理解正确。** 不对。它约束输出结构，不保证模型提取的指标、时间范围或筛选条件符合真实意图。
4. **with_structured_output() 会执行数据库操作。** 不对。它只负责结构化模型输出。
5. **通过 Schema 校验就可以执行 SQL。** 不对。权限和 SQL 安全必须由后端独立实现。

## 13. 动手练习与验收标准

### 练习一：扩展筛选条件

给 FilterCondition 增加一个字段，用来标识筛选条件来自用户原文的哪个片段。

验收标准：
- 字段必须出现在 JSON Schema 中。
- 缺少字段时校验失败。
- 多余字段仍然被拒绝。

### 练习二：增加业务约束

尝试增加规则：action=query 时 metric 不能是“未提供”；action=clarify 时必须至少有一个问题。

验收标准：
- 正常数据通过。
- 违反规则的数据抛出 ValidationError。
- 不依赖 Prompt 文本来保证这条规则。

### 练习三：解释执行链路

不看代码，说明从 Pydantic 类到后端拿到 DatabaseQueryIntent 对象，中间经过哪些步骤。

验收标准：
- 能区分 model_json_schema()、with_structured_output() 和 invoke()。
- 能解释 JSON Schema 和 Pydantic Validator 的不同职责。
- 能解释为什么还需要后端权限检查。

## 14. Summary（本节总结）

- Pydantic 定义 Python 数据模型，并在运行时验证数据。
- model_json_schema() 根据 Pydantic 模型生成 JSON Schema。
- with_structured_output() 把结构化约束应用到模型调用中。
- strict=True 用于约束输出结构，但不保证语义正确。
- field_validator 负责字段级检查，model_validator 负责跨字段业务检查。
- 结构化输出的结果可以是 Pydantic 对象，后端可以直接读取字段。
- Structured Output 不等于 Tool Calling，更不等于数据库执行。

## 15. 面试题与参考答案

### Q1：Pydantic 和 JSON Schema 有什么区别？

Pydantic 是 Python 中的数据建模与校验工具，能定义模型、校验运行时数据并生成 JSON Schema。JSON Schema 是一种描述 JSON 数据结构的规范，能被不同语言和服务理解。可以使用 Pydantic 定义模型，再生成 JSON Schema 作为模型输出契约。

### Q2：model_json_schema()、with_structured_output() 和 invoke() 分别做什么？

- model_json_schema()：生成结构规范，不调用模型。
- with_structured_output()：基于 Schema 创建结构化模型调用入口。
- invoke()：真正发起模型请求并取得解析后的结构化结果。

### Q3：为什么使用 strict=True 以后还需要 Pydantic Validator？

strict=True 主要约束模型输出符合 Schema，例如字段、类型和额外属性。某些业务规则属于多个字段之间的关系，不能只靠基础 JSON Schema 表达；还需要在应用侧使用 field_validator 和 model_validator 检查。

### Q4：Structured Output 和 Tool Calling 有什么区别？

Structured Output 让模型返回符合约定结构的数据；Tool Calling 让模型提出调用工具的请求。工具是否执行由应用程序决定，应用必须先检查参数、身份、权限和安全策略。

### Q5：模型返回了结构合法但业务错误的数据，应该怎么办？

应用侧必须进行 Pydantic 和业务规则校验。校验失败时拒绝进入后续流程，可以有限重试、让模型重新生成或向用户澄清；不能把无效结果当作成功，也不能只依赖 Prompt 来保证正确性。
