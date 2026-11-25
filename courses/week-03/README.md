# 第 3 周：Tool Calling 与 LangChain Agent

## 本周目标
围绕“Tool Calling 与 LangChain Agent”完成 3 节课，并将成果接入持续演进的项目。

## 课程安排

### S3-01：Function Calling / Tool Calling 的执行机制
<badge>代码已提交，待本地验收</badge>

**课程文档：** [S3-01-function-calling.md](./S3-01-function-calling.md)

**新增代码：**
- `projects/database-agent/app/lesson07.py`
- `projects/database-agent/tests/test_lesson07.py`

**实践任务：** 追踪模型提出工具调用请求、应用执行工具、结果返回模型的完整过程。

**本节范围：** 单轮工具调用闭环；不实现 Agent 循环。工具使用内置指标目录，不连接真实数据库。

### S3-02：工具定义、参数 Schema 与结果返回

**实践任务：** 实现至少两个工具，校验参数，并测试工具失败和非法参数。

### S3-03：使用 LangChain 构建 Agent 循环

**实践任务：** 构建能选择工具、读取结果并结束任务的 Agent，加入最大迭代次数。

## 本周验收
- 三节课的代码均能按文档运行。
- 至少完成一项异常场景测试。
- 更新项目 README 与学习进度。
- 能口头解释本周核心架构决策。
