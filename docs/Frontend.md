# 知页：Vue 前端

前端位于 `frontend/`，使用 Vue 3、TypeScript、Vite。旧 Streamlit 文件仍在，FastAPI、账号 ORM、文档索引、检索与 Agent 代码没有迁移到前端，也没有修改。

## 启动和访问

先按 README 启动 PostgreSQL 与 FastAPI，再执行：

```powershell
cd C:\toolkit\agent-service-toolkit\frontend
npm ci
npm run dev
```

浏览器打开 `http://127.0.0.1:8502`。8502 已被旧 Streamlit 占用时，先停止旧前端进程。Vite 固定端口，端口冲突会报错，不会悄悄切换端口。请固定使用同一个主机名（127.0.0.1 或 localhost），避免浏览器把它们当成两个登录站点。

`frontend/.env.example` 仅包含代理地址，可复制为 `.env.local`。不要把根目录 `.env` 或模型密钥复制到前端；前端无需千问或 DeepSeek 的 API Key。

## 页面与现有接口

| 页面 | 现有后端接口 |
| --- | --- |
| 登录、注册、账号设置 | `/auth/register`、`/auth/login`、`/auth/me`、`/auth/change-password`、`/auth/logout` |
| 文档管理 | `/knowledge/documents`、`/{id}/chunks`、`/{id}/reindex` |
| 检索验证 | `/knowledge/search` |
| 知识问答 | `/rag-assistant/threads`、`/rag-assistant/history`、`/rag-assistant/stream` |
| 引用原文 | `/knowledge/documents/{document_id}/chunks/{chunk_id}` |

浏览器请求 `/api/knowledge/...`，Vite 或 Nginx 去掉 `/api` 后转给 FastAPI。代理保留浏览器请求的 Host 与 Origin，原来的后端跨来源校验继续有效。登录使用后端设置的 HttpOnly Cookie，前端不在 localStorage 保存 token、聊天正文或文档内容。用户 ID 由后端从登录会话识别；前端只为新会话生成 thread_id。

聊天解析 SSE 的 message、token、error 和 `[DONE]`。支持数据帧拆包和中文 UTF-8 拆包；断流会显示友好提示。点击「停止等待」停止浏览器接收，后端任务可能仍在执行，可重新打开会话读取已保存结果。不会自动重复提交一次问题。

模型回复的 Markdown 经 DOMPurify 清理后渲染，去除脚本、图片、内联样式等。引用按钮使用后端返回的文档和片段 ID 请求原文，权限继续由后端检查。后端内部异常、代理 HTML 和原始请求地址不会作为错误提示直接显示在页面。

## 代码入口

| 文件 | 用途 |
| --- | --- |
| `frontend/src/App.vue` | 页面、交互与界面状态，直接组合现有 API |
| `frontend/src/style.css` | 桌面和移动布局、颜色、字体与组件样式 |
| `frontend/src/api.ts` | Cookie 请求、公开错误码的中文映射与登录失效通知 |
| `frontend/src/stream.ts` | SSE 解码与完整性检查 |
| `frontend/src/markdown.ts` | Markdown 与 HTML 清理 |
| `frontend/src/types.ts` | 后端响应的 TypeScript 类型 |
| `frontend/vite.config.ts` | 本地 API 代理与开发端口 |
| `docker/frontend.conf` | 容器里的同源 API 代理、流式转发与静态文件 |

前端的文档统计从后端返回值计算，不创建额外数据库表。上传多文件时依次调用原有单文件上传接口；更新、去重、版本管理、重建索引和删除均由原来的知识库服务处理。检索验证直接展示召回片段与排序分数，不调用聊天模型。

## 验证与部署

`npm test` 检查 SSE 拆包、断流、错误隐私、HTML 清理和 Cookie 请求；`npm run build` 执行 TypeScript 检查并生成 `frontend/dist`。`npm run preview` 仅用于预览静态产物，不提供开发 API 代理；完整本地体验请用 `npm run dev`，生产使用 Compose 的 Nginx 前端。

Compose 的 PostgreSQL 和 agent_service 配置不变，前端服务改为 `web_frontend`。Nginx 关闭 API 响应缓冲以便转发 SSE。公网部署还应配置 HTTPS，并按原有后端说明设置安全 Cookie。Nginx 默认限制请求体为 30MB，调整后端上传限制时也需核对该值。
