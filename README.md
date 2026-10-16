# 个人知识库助手

基于 FastAPI、LangGraph、Streamlit、PostgreSQL 与 Chroma 的个人知识库。只保留 `rag-assistant`，支持账号私有文档、增量导入与版本更新、混合检索、百炼重排和可展开原文引用。

## 启动

```powershell
uv sync --frozen
# 配置本地 .env，参考 .env.example；账号机制要求 PostgreSQL
docker compose up -d postgres
.\.venv\Scripts\python.exe src/run_service.py
```

另一个终端：

```powershell
.\.venv\Scripts\python.exe -m streamlit run src/streamlit_app.py --server.address 127.0.0.1 --server.port 8502
```

本地配置后端端口为 8081：先在 <http://127.0.0.1:8081/account> 注册/登录，知识库管理地址为 <http://127.0.0.1:8081/knowledge>，聊天地址为 <http://127.0.0.1:8502>。其他部署端口请按 `.env` 调整。

## 主要目录

| 目录 | 职责 |
| --- | --- |
| `src/agents` | 唯一 RAG Agent 和检索工具 |
| `src/rag` | 文档与版本、切分、混合检索、重排、来源、索引适配器 |
| `src/accounts` | SQLAlchemy 账号与会话数据库 |
| `src/service` | FastAPI、登录页面、知识库管理页面、聊天协议 |
| `src/client` | Python 客户端 |
| `src/memory` | 会话 checkpoint 和底层 Store |
| `scripts/manage_knowledge.py` | 指定账号的导入与旧向量迁移 |

数据流、配置、文档生命周期、限制与接口见 [RAG 说明](docs/RAG_Assistant.md)，账号机制见 [账号说明](docs/Account_Login.md)。

## 验证

```powershell
$env:USER_AUTH_ENABLED='false'
uv run pytest tests/rag tests/agents tests/service tests/client tests/core tests/schema
uv run ruff check src tests scripts
```

知识库 API 始终要求账号认证，测试使用临时数据库和测试账号。外部 API 集成需要本地真实配置，单元测试不消费模型额度。Streamlit AppTest 单独从 `tests/app` 运行。

本项目基于 Joshua Carroll 的 [Agent Service Toolkit](https://github.com/JoshuaC215/agent-service-toolkit) 改造。原作者版权和 MIT 许可保留，见 LICENSE。
