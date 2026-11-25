# Database Agent：持续演进的课程项目

当前阶段：**S1-01 至 S2-03 已完成；S3-01 Function Calling / Tool Calling 代码与课程文档已加入，等待本地运行验收。**

项目目前提供真实模型调用、多轮历史、流式输出、结构化查询意图、Prompt Template、Pydantic 校验、有限重试、模型适配，以及单轮 Tool Calling 演示。当前尚未连接真实数据库，也没有执行 SQL。

## S3-01：Function Calling / Tool Calling

课程文档：[S3-01 Function Calling / Tool Calling 执行机制](../../courses/week-03/S3-01-function-calling.md)

新增文件：
- `app/lesson07.py`：定义指标查询工具、绑定工具、解析模型工具调用请求、通过白名单执行工具、构造 ToolMessage 并将结果交还模型。
- `tests/test_lesson07.py`：覆盖工具结果、未知工具、tool_call_id 关联、完整工具调用链、直接回答和空输入。

### 运行示例

在 `projects/database-agent` 目录执行：

~~~powershell
.\.venv\Scripts\python.exe -m app.lesson07 "查询订单数的定义和计算口径"
~~~

### 离线测试

~~~powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_lesson07.py
~~~

测试使用 FakeModel，不访问真实模型网关。CLI 示例会调用现有 `.env` 配置的模型。

本节工具 `lookup_metric_definition` 查询的是项目内置指标目录，不是数据库查询工具，不会连接数据库或执行 SQL。当前实现只演示一轮工具调用；Agent 循环和终止条件安排在 S3-03。

---

