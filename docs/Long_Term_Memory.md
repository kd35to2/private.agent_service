# 长期记忆与知识库

当前仓库只保留 RAG Agent。原研究助手的 remember/recall/forget 工具已移除，历史 Store 数据未删除。

会话 checkpoint 继续保存对话历史；文档知识库由 PostgreSQL 文档表和 Chroma 索引管理，两者不等同于个人偏好记忆。

知识库按登录账号隔离，具体实现见 [RAG 说明](RAG_Assistant.md)。未来需要记住用户偏好时，可在独立的用户命名空间下重新接入 Store，避免把个人记忆混入文档证据。
