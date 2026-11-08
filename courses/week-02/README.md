# 第 2 周：Prompt 与可靠输出

## 本周目标
围绕“Prompt 与可靠输出”完成 3 节课，并将成果接入持续演进的项目。

## 课程安排

### S2-01：System/User Message 与 Prompt Template

<badge>已完成代码与讲解准备</badge>

**实践任务：** 将固定提示词改造成可复用模板，并测试不同输入。

课程文档：[S2-01：System Message、User Message 与 Prompt Template](S2-01-system-user-prompt-template.md)。

### S2-02：Pydantic、JSON Schema 与结构化输出校验

<badge>本次新增</badge>

**实践任务：** 定义嵌套业务输出模型，生成 JSON Schema，处理缺字段、类型错误、多余字段和跨字段业务约束。

课程文档：[S2-02：Pydantic、JSON Schema 与结构化输出校验](S2-02-pydantic-json-schema-structured-output.md)。

配套代码：
- projects/database-agent/app/lesson05.py
- projects/database-agent/tests/test_lesson05.py

### S2-03：超时、重试、错误分类与模型适配

**下一节：** 为模型调用增加超时、有限重试、统一错误格式和供应商配置。

**实践任务：** 把模型调用中的网络错误、超时、限流、模型拒绝和结构化解析失败区分开，避免对所有错误盲目重试。

## 本周验收
- 三节课的代码均能按文档运行。
- 至少完成一项异常场景测试。
- 更新项目 README 与学习进度。
- 能口头解释本周核心架构决策。
