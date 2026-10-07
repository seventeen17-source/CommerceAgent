# agent-service

CommerceAgent 的 **Agent Service**（Python 3.13 / FastAPI / LangGraph）。它负责：认证与 run ownership、`AgentState` 与状态演化、Tool 调用与 allowlist、写前意图 / 写后权威校验、结构化 Trace。

**进度与"下一步做什么"只读根目录的 [`PROJECT_PROGRESS.md`](../PROJECT_PROGRESS.md)**；本文件不记录进度，避免成为第二个会过期的真相。

本机门禁（等价于文档里的 `uv run ...`；受限环境下 `uv run` 写不了 uv cache）：

```powershell
.\.venv\Scripts\python.exe -m ruff check . --no-cache
.\.venv\Scripts\python.exe -m ruff format --check . --no-cache
.\.venv\Scripts\python.exe -m mypy app
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

架构与完整请求链路见 [`docs/PROJECT_ARCHITECTURE.md`](../docs/PROJECT_ARCHITECTURE.md)；契约见 [`specs/002-commerce-after-sales-agent/contracts/`](../specs/002-commerce-after-sales-agent/contracts/)。
