# AI Agent Learn

面向具备 Python、Node.js、NestJS、React 和 MySQL 基础的开发者，系统学习 AI Agent 工程开发，并兼顾岗位面试与真实产品落地。

## 学习目标

完成第一轮学习后，目标是能够：

- 解释 LLM 应用、Tool Calling、RAG、Memory、MCP、LangChain、LangGraph 和 Multi-Agent 的工作原理与适用场景。
- 独立开发一个带工具调用、状态管理、权限控制和评测能力的 Agent 应用。
- 设计并实现包含规划、人工审核、工具执行、结果呈现的工作流型 Agent。
- 对 Agent 进行测试、追踪、部署、安全加固与成本控制。
- 回答常见 AI Agent 开发面试问题，并能讲清自己的架构决策。

## 学习方式

**开始第一课：** [S1-01：直接调用模型 API 与 LangChain 的区别](courses/week-01/s1-01-model-api-and-langchain.md)。配套代码位于 [Database Agent 项目](projects/database-agent/)，学习和联调结果记录在 [学习进度](docs/learning-progress.md)。

**继续第二课：** [S1-02：Message、Prompt、Token 与上下文窗口](courses/week-01/s1-02-messages-prompt-context.md)，加入多轮对话、完整轮次裁剪和服务报告的 Token 用量。

**第三节课：** [S1-03：Streaming 与 Structured Output](courses/week-01/S1-03-streaming-structured-output.md)，新增流式输出、结构化查询意图提取与 FastAPI 接口。

采用“每学一个知识点，就写代码并逐步完善项目”的方式。每节课必须包含概念解释、可运行代码、执行链路分析、项目实践、测试练习、Summary 和 3–5 道面试题及参考答案。

## 12 周路线

| 周次 | 主题 | 主要成果 |
|---|---|---|
| 1 | LLM 应用基础 | 真实模型 API + FastAPI 对话服务 |
| 2 | Prompt 与可靠输出 | 结构化输出、校验、异常处理 |
| 3 | Tool Calling + LangChain Agent | 可选择并执行多个工具的 Agent |
| 4 | Database Agent | 受权限控制的自然语言只读查询 |
| 5 | RAG | 可检索文档并引用来源的知识库 Agent |
| 6 | LangGraph | 有状态、带条件分支的 Agent 流程 |
| 7 | Memory 与人工审核 | 暂停、审核、持久化和恢复执行 |
| 8 | MCP | MCP Server/Client 与工具接入 |
| 9 | Multi-Agent | 多角色协作原型 |
| 10 | 评测与可观测性 | 可重复运行的评测集、追踪和日志 |
| 11 | 生产工程与部署 | 安全、限流、成本控制和 Docker 部署 |
| 12 | 综合项目与面试 | AI4S Workflow Agent、演示与面试材料 |

建议每周投入 8–10 小时。时间不足时可延长到 16–20 周，不以赶进度为目标。

## 项目

1. **Database Agent**：前期实战项目，逐步练习模型调用、工具调用、Schema 检索、RAG、权限、安全和 MCP。
2. **AI4S Workflow Agent**：综合项目，练习任务规划、React Flow 可视化、LangGraph、人工审核、分析工具执行、结果汇总和可复用 Pipeline。

## 文件导航

- `docs/learning-methods.md`：学习方法
- `docs/teaching-principles.md`：教学原则与每节课标准
- `docs/technical-principles.md`：技术选型与工程原则
- `docs/projects.md`：项目规划
- `docs/interview-plan.md`：面试学习要求
- `courses/00-roadmap.md`：完整课程安排
- `courses/lesson-template.md`：每节课模板
- `courses/week-01/` 至 `courses/week-12/`：每周课程目标与 3 节课安排

## 重要约定

- 课程用中文讲解，英文术语附中文翻译。
- 示例优先使用真实、可运行的工程代码，不以伪代码代替核心实现。
- API Key、数据库凭据等通过环境变量配置，不写入代码仓库。
- 每一阶段完成后更新项目代码、README、学习进度和面试清单。
- 课程示例使用的框架/API 若发生变化，应优先核对官方文档后再编写代码。
