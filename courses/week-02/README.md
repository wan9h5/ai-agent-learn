# 第 2 周：Prompt 与可靠输出

## 本周目标

围绕“Prompt 与可靠输出”完成 3 节课，并将成果接入持续演进的 Database Agent 项目。

## 课程安排

### S2-01：System/User Message 与 Prompt Template

**实践任务：** 将固定提示词改造成可复用模板，并测试不同输入。

课程文档：[S2-01：System Message、User Message 与 Prompt Template](S2-01-system-user-prompt-template.md)。

配套代码：
- projects/database-agent/app/lesson04.py
- projects/database-agent/tests/test_lesson04.py

### S2-02：Pydantic、JSON Schema 与结构化输出校验

**实践任务：** 定义嵌套业务输出模型，生成 JSON Schema，处理缺字段、类型错误、多余字段和跨字段业务约束。

课程文档：[S2-02：Pydantic、JSON Schema 与结构化输出校验](S2-02-pydantic-json-schema-structured-output.md)。

配套代码：
- projects/database-agent/app/lesson05.py
- projects/database-agent/tests/test_lesson05.py

### S2-03：超时、重试、错误分类与模型适配

**本次新增。**

**实践任务：** 为模型调用加入超时、有限重试、统一错误格式和模型适配层。区分网络错误、超时、限流、认证失败、请求错误和结构化输出校验失败，避免对所有错误盲目重试。

课程文档：[S2-03：超时、重试、错误分类与模型适配](S2-03-timeout-retry-error-handling-model-adapter.md)。

配套代码：
- projects/database-agent/app/lesson06.py
- projects/database-agent/app/lesson06_api.py
- projects/database-agent/tests/test_lesson06.py

本节复用项目原有 .env、LLM_API_KEY、LLM_MODEL、LLM_BASE_URL、LLM_TIMEOUT_SECONDS 和 LLM_MAX_COMPLETION_TOKENS，不新增密钥配置，不覆盖已有 .env。

## 本周验收

- 三节课的代码均能按文档运行。
- 至少完成一项异常场景测试。
- 能解释 JSON Schema 与 Pydantic 校验的边界。
- 能解释为什么只对暂时性错误重试。
- 能说明模型适配层如何降低供应商耦合。
- 更新项目 README 与学习进度。
