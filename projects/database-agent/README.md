# Database Agent：持续演进的课程项目

当前阶段：**S1-01 模型接入层 + S1-02 多轮对话 + S1-03 流式输出与结构化输出 + S2-01 Prompt Template**。提供真实模型调用、多轮历史、流式输出、结构化查询意图，以及可复用的提示词模板。当前没有数据库连接、SQL 执行或工具循环。

课程入口：
- [S1-01 模型 API 与 LangChain](../../courses/week-01/s1-01-model-api-and-langchain.md)
- [S1-02 Message、Prompt、Token 与上下文](../../courses/week-01/s1-02-messages-prompt-context.md)
- [S1-03 Streaming 与 Structured Output](../../courses/week-01/S1-03-streaming-structured-output.md)
- [S2-01 System/User Message 与 Prompt Template](../../courses/week-02/S2-01-system-user-prompt-template.md)

## S2-01：Prompt Template

本节新增：
- \`app/lesson04.py\`：System/User 模板、动态变量、可选历史消息、Conversation 历史转换和 CLI。
- \`tests/test_lesson04.py\`：模板、角色、历史和模型请求的离线测试。

无需新增依赖，沿用原来的虚拟环境与 \`.env\`。在本项目目录执行：

\`\`\`powershell
.\\.venv\\Scripts\\python.exe -m app.lesson04 preview "统计上个月订单数"
.\\.venv\\Scripts\\python.exe -m app.lesson04 preview "统计上个月订单数" --database-context "MySQL 8.0；orders(id, created_at, amount)"
.\\.venv\\Scripts\\python.exe -m app.lesson04 ask "统计上个月订单数"
.\\.venv\\Scripts\\python.exe -m pytest -q tests/test_lesson04.py
\`\`\`

\`preview\` 只格式化并显示最终消息，不调用模型；\`ask\` 才会使用原来的模型配置发起请求。完整讲解、执行链路和练习见 S2-01 课程文档。

## S1-03：Streaming 与 Structured Output

完整课程：[S1-03 中文讲解](../../courses/week-01/S1-03-streaming-structured-output.md)。

本节在原项目中增量增加流式调用、Pydantic 查询意图、FastAPI SSE / JSON 接口和离线测试。沿用现有虚拟环境与 \`.env\`，不要重新创建环境，也不要覆盖已有密钥配置。

### 安装本节依赖

在当前项目目录执行：

\`\`\`powershell
python -m pip install -r requirements-s1-03.txt
\`\`\`

### 命令行实验

\`\`\`powershell
python -m app.lesson03 stream "用中文解释数据库索引，并举两个例子"
python -m app.lesson03 intent "统计上个月订单数"
python -m app.lesson03 intent "查一下订单"
\`\`\`

### FastAPI 接口

\`\`\`powershell
python -m uvicorn app.lesson03_api:app --reload --host 127.0.0.1 --port 8000
\`\`\`

### 离线测试

\`\`\`powershell
python -m pytest -q tests/test_lesson03.py
\`\`\`

## S1-02 多轮对话

\`\`\`powershell
.\\.venv\\Scripts\\python.exe -m app.chat_cli --keep-turns 3
\`\`\`

## 环境与安装

建议使用 Python 3.12。首次运行时在仓库根目录进入本项目：

\`\`\`powershell
cd projects/database-agent
python -m venv .venv
.\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
\`\`\`

编辑 \`.env\`：填写自己的 API Key、模型 ID 和服务基础地址。不要把密钥提交到 Git。已有 \`.env\` 时不要覆盖。

## 当前验证边界

自动测试通过 MockTransport 替换网络响应，不会使用真实模型密钥或产生模型调用费用。真实服务联调由学习者在本地完成后记录。
