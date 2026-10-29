# AI Agent 学习路线总表

## 总目标

兼顾 AI Agent 岗位能力、面试和产品开发；采用项目驱动的渐进式学习。建议 12 周、每周 8–10 小时；如时间不足，可延长至 16–20 周。

## 12 周安排

### 第 1 周：大模型应用基础
- S1-01：直接调用模型 API 与 LangChain 的区别
- S1-02：Message、Prompt、Token 与上下文窗口
- S1-03：Streaming 与 Structured Output
- 交付：真实模型 API + FastAPI 对话服务

### 第 2 周：Prompt 与可靠输出
- S2-01：System/User Message 与 Prompt Template
- S2-02：Pydantic、JSON Schema 与结构化输出校验
- S2-03：超时、重试、错误分类与模型适配
- 交付：经过校验的 JSON 输出服务

### 第 3 周：Tool Calling 与 LangChain Agent
- S3-01：Function Calling / Tool Calling 执行机制
- S3-02：工具定义、参数 Schema 与结果返回
- S3-03：使用 LangChain 构建 Agent 循环
- 交付：能选择并执行多个工具的 Agent

### 第 4 周：Database Agent
- S4-01：数据库 Schema 与元数据读取
- S4-02：自然语言转 SQL 与结果处理
- S4-03：只读权限、SQL 限制、超时和人工确认
- 交付：受控的自然语言数据库查询

### 第 5 周：RAG
- S5-01：文档解析、切分与 Embedding
- S5-02：向量检索、召回与重排序
- S5-03：检索结果注入、来源引用与质量检查
- 交付：可引用来源的知识库 Agent

### 第 6 周：LangGraph
- S6-01：State、Node、Edge
- S6-02：条件路由、循环与终止条件
- S6-03：Workflow 与 Agent 的区别及混合架构
- 交付：有状态、带分支的 Agent 流程

### 第 7 周：Memory 与人工审核
- S7-01：对话状态、短期记忆与长期记忆
- S7-02：Checkpoint、持久化与恢复
- S7-03：Human-in-the-loop、暂停、审核与继续
- 交付：可暂停并恢复的任务执行流程

### 第 8 周：MCP
- S8-01：MCP 架构、Tool、Resource 与 Prompt
- S8-02：使用 Python MCP SDK 编写 MCP Server
- S8-03：MCP Client 接入 Agent 与安全边界
- 交付：可供客户端调用的 MCP 服务

### 第 9 周：Multi-Agent
- S9-01：Router、Supervisor、Subagent
- S9-02：委派、并行、结果合并与失败处理
- S9-03：何时采用多 Agent，以及复杂度控制
- 交付：多角色科研任务协调原型

### 第 10 周：评测与可观测性
- S10-01：Tracing、日志、Token、延迟和成本
- S10-02：评测数据集、成功率与工具调用准确率
- S10-03：规则评测、LLM-as-a-Judge 与回归测试
- 交付：可重复运行的 Agent 评测集

### 第 11 周：生产工程与部署
- S11-01：Prompt Injection、最小权限和数据隔离
- S11-02：超时、重试、幂等性、并发和限流
- S11-03：Docker、认证授权、监控和配置管理
- 交付：可在受控环境部署的 Agent 服务

### 第 12 周：综合项目与面试
- S12-01：AI4S Workflow Agent 架构设计
- S12-02：整合 React Flow、LangGraph、审核、工具与结果
- S12-03：部署、README、架构说明、演示与面试复盘
- 交付：端到端综合项目与面试材料

## 课程完成标准

每节都应有可运行代码、执行链路解释、项目实践、测试练习、Summary 和 3–5 道面试题及参考答案。完成每周后，更新代码、进度和未解决问题。
