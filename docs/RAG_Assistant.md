# 个人知识库：代码与数据流程

本项目只注册 `rag-assistant`。账号、会话 checkpoint 与 LangGraph Store 保留；原研究助手的个人记忆工具已移除，知识库不会混入个人记忆。

## 分层

```text
Streamlit 聊天 / 浏览器知识库管理页
  → FastAPI：登录、账号归属、输入校验
  → rag.documents.KnowledgeBase：文档版本、检索与来源服务
      → PostgreSQL / SQLAlchemy：文档、原文件、版本、片段、处理状态
      → rag.stores.ChromaIndex：向量索引适配器
      → rag.retrieval：中文 BM25、完整编号、RRF 排名融合
      → rag.rerank：百炼文本重排 HTTP API
  → RAG Agent：检索工具 → 基于证据回答 → 引用编号校验
```

`src/agents/tools.py` 不加载 Chroma，也不实现检索策略。普通 `/knowledge/search` 接口与 Agent 使用同一服务。每次回答必先检索；模型不会自行绕过检索。模型调用标记 `skip_stream`，流式接口只输出完成引用校验的回答，避免先把伪造来源流到前端。

## 私有知识库与登录

启用 `USER_AUTH_ENABLED=true` 和 PostgreSQL。在 `/account` 登录后，访问 `/knowledge`：可以上传 PDF、DOCX、UTF-8 TXT / Markdown，查看文档版本、片段，更新、删除、重新索引与检索验证。

所有知识库 API 通过 Cookie 或 Bearer 登录会话认证；`owner_id` 由服务器获取，不接收客户端声明。向量查询限定 owner 和当前有效版本；BM25 仅加载该账号的有效片段。不存在或无权访问的文档都返回 404。没有登录的请求返回 401。原文件、正文、引用接口同样按归属检查。

## 配置

嵌入与聊天模型独立。千问嵌入配置：

```dotenv
DASHSCOPE_API_KEY=在本地填入密钥
RAG_EMBEDDING_PROVIDER=dashscope
RAG_EMBEDDING_MODEL=text-embedding-v4
RAG_EMBEDDING_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
RAG_CHROMA_PATH=./chroma_db
RAG_CHUNK_SIZE=2000
RAG_CHUNK_OVERLAP=500
RAG_VECTOR_K=20
RAG_KEYWORD_K=20
RAG_TOP_K=5
RAG_RERANK_ENABLED=true
RAG_RERANK_MODEL=qwen3-rerank
RAG_RERANK_URL=https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank
RAG_RERANK_TIMEOUT=30
RAG_MIN_RERANK_SCORE=0.05
```

地址示例对应北京地域，API Key、模型权限、地域需匹配；可替换成百炼控制台的业务空间专用地址。重排使用 DashScope 原生接口，不是在 OpenAI 兼容地址后追加 `/rerank`。参考[官方 API](https://help.aliyun.com/zh/model-studio/text-rerank-api)。重排会产生额外的模型请求。最低分数只是初始配置，不是“可信概率”，需要用自己的文档和问答案例调整。

索引记录嵌入 provider/model 签名。改变嵌入模型后，旧签名版本暂不参与向量召回、仍可进行关键词检索并明确提示重新索引。更换聊天模型通常不需要重建向量。更换嵌入模型且向量维度变化时，先把 `RAG_CHROMA_PATH` 指向新的索引目录，再重新索引全部文档；原目录保留为备份，避免混合不同维度。新索引使用集合 `kb_chunks_v1`，不查询无账号归属的旧集合 `langchain`。

## 增量与失败恢复

1. 内容哈希相同的活跃文档重复上传会直接返回已有文档；不重复调用嵌入 API。
2. 同名但内容不同的新上传返回 409；用户选择“更新”指定稳定 document ID。
3. PostgreSQL 记录待处理版本，原 active version 保持有效。
4. 完成解析、嵌入及向量写入，再在一个 SQL 事务中保存片段并切换 active version。
5. 失败记录 failed 状态和公开提示；详细原因仅写服务器日志。旧版本继续可检索。可重新索引最新上传内容。
6. 成功后清理旧版本向量；清理失败时，SQL 有效版本过滤仍会排除旧索引。
7. 删除先标记 deleted 并清空 active version，再清理向量；旧 SQL 版本与原文件留作历史记录，不承诺物理擦除。
8. 服务启动将中断的 processing 标记 failed，保留此前有效版本；待处理索引可在恢复时清理。没有常驻后台任务队列，当前导入在请求内执行。

两个数据库没有分布式事务。该流程通过“先准备、后发布”和权威版本过滤保证可见性；不能把 Chroma 写入与 PostgreSQL 提交当成同一个事务。

当前是本地 Chroma 单服务进程部署。运行 `src/run_service.py` 即可；不要为同一个本地索引启动多个写入进程或 Uvicorn workers。执行管理 CLI 前先停后端，执行完成再启动。规模增长时可替换 stores 适配器为独立向量服务，并引入任务队列。

## 检索与来源

向量与 BM25 各召回最多 20 条，通过 RRF 合并排名、去重后再重排，返回最多 5 条。完整的 `AP2609-3074` 等编号单独保留；明确包含编号的查询会过滤掉只有相似编号的片段。中文分词使用 jieba。来源元数据包含文档 ID、版本、片段 ID、片段号、原文位置和可用页码。

PDF 页码按 1 开始显示；DOCX 不推算页码，使用片段号和字符位置。字符位置基于提取后的文本（PDF 为对应页内位置），不是 Word 排版坐标。

引用使用服务器签发的 `[1]` 等编号。回答包含未知编号或没有引用时，不输出该未核查回答；提供原文片段供核查。模型生成的链接不作为可信来源。该校验保证编号确实来自检索结果，不能自动证明每句话都被原文支持，仍应检查证据。

向量服务或重排失败会降级到仍可用的召回路径，公开返回 degraded 与 notices；内部错误和堆栈只记录到日志。无结果时不调用回答模型，并明确告知资料不足。

## API

| 接口 | 用途 |
| --- | --- |
| GET `/knowledge/documents` | 当前账号文档和版本状态 |
| POST `/knowledge/documents` | multipart 文件；可带 document_id 更新 |
| POST `/knowledge/documents/{id}/reindex` | 重新解析最新上传版本并索引 |
| DELETE `/knowledge/documents/{id}` | 停止检索并清理对应向量 |
| GET `/knowledge/documents/{id}/chunks` | offset/limit 分页查看当前片段 |
| GET `/knowledge/documents/{id}/chunks/{chunk_id}` | 查看授权文档的引用原文，包括保留的历史版本 |
| POST `/knowledge/search` | JSON query，可选 limit；不调用聊天模型 |

## 导入及旧索引迁移

```powershell
# 需要已经注册的真实账号；不会默认清空整库
.\.venv\Scripts\python.exe scripts/manage_knowledge.py --owner zhq --file "data/投标方案8-15.docx"

# 迁移旧 langchain 集合；先备份到 .local/backups，再复用已有向量
.\.venv\Scripts\python.exe scripts/manage_knowledge.py --owner zhq --migrate-existing
```

旧入口 `scripts/create_chroma_db.py` 调用相同的安全管理入口，也必须指定 `--owner`。`.local/` 已加入 Git 忽略。迁移不会猜测文档所属用户；旧来源文件缺失或已变更时停止，要求检查原文件。
