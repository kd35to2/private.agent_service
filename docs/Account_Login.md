# 用户账号与长期记忆

本项目使用 SQLAlchemy 异步 ORM 管理账号，使用 LangGraph 管理 Agent 状态和记忆。
两者共用 PostgreSQL 数据库，但使用不同的表。

## 为什么选择 PostgreSQL

这里主要是复用 LangGraph 已有的 PostgreSQL Checkpointer / Store 和项目现有连接配置。
MySQL 也能存用户信息和记忆；如果切换，就需要相应的 Store、Checkpointer 和驱动适配。
当前记忆按 namespace / key 读写，并没有启用向量检索。

Docker 负责运行 PostgreSQL，Python 通过数据库驱动访问映射出来的端口。直接安装或使用
远程 PostgreSQL 时，修改连接参数即可，不要求使用 Docker。

## 数据表与代码位置

| 表 | 作用 | 谁负责读写 |
| --- | --- | --- |
| `account_users` | 固定用户 UUID、用户名、密码哈希、登录失败次数 | SQLAlchemy ORM |
| `account_sessions` | 登录令牌哈希、用户 ID、过期时间 | SQLAlchemy ORM |
| `account_threads` | 会话 ID 属于哪个用户和哪个 Agent | SQLAlchemy ORM |
| `account_runs` | 执行 ID 归属，用于校验反馈权限 | SQLAlchemy ORM |
| LangGraph checkpoint 表 | 会话消息、图执行状态 | LangGraph Checkpointer |
| LangGraph Store 表 | 跨会话用户记忆 | LangGraph Store |

- `src/accounts/models.py`：ORM 表定义。
- `src/accounts/database.py`：异步引擎、Session 工厂、初始建表。
- `src/schema/accounts.py`：请求和响应校验。
- `src/service/account_auth.py`：注册、登录、改密、凭证验证、会话权限。
- `src/service/account_page.py`：浏览器账号页面。
- `src/service/service.py`：把认证身份绑定到 Agent 配置。
- `src/rag/documents.py`：用登录账号 UUID 隔离知识库；账号 UUID 由后端确认。

当前首次启动使用 `create_all()` 创建缺少的账号表；它不会升级已有表结构。以后修改表字段
时，需要编写数据库迁移，例如引入 Alembic。这里不会修改或清空原有 LangGraph 表。

## 注册、登录和恢复身份

```text
注册 → 校验用户名和密码 → Argon2 哈希 → ORM INSERT account_users
登录 → ORM 查询用户 → 校验哈希 → 生成随机令牌 → 数据库保存令牌哈希
     → 浏览器保存 HttpOnly Cookie
聊天 → 校验 Cookie 或 Bearer → 查询登录会话 → 获取固定用户 UUID
     → 写入 Agent config.user_id → Checkpointer / Store
```

用户名按小写保存，长度 3–32，允许字母、数字、点、下划线和连字符。
密码长度 8–128，仅保存 Argon2 哈希。默认登录有效期 7 天，连续五次密码错误会锁定账号五分钟。

浏览器使用 HttpOnly、SameSite=Lax Cookie；API 客户端可以使用登录返回的 Bearer 令牌。
令牌不会放在 URL 中。退出登录撤销当前会话；修改密码要求旧密码，并撤销所有登录会话。
修改密码不会更换用户 UUID，所以重新登录仍能找回原来的会话和长期记忆。

登录模式下，接口不接受与登录账号不同的 `user_id`。新会话创建归属记录，继续会话和读取历史
时校验归属。已有匿名 checkpoint 不会因为有人提交其 thread_id 就归入该账号。

## 配置和启动

复用现有 `.env` 中的 PostgreSQL 参数，再设置：

```dotenv
USER_AUTH_ENABLED=true
AUTH_SESSION_DAYS=7
AUTH_COOKIE_SECURE=false
APP_URL=http://127.0.0.1:8502
AGENT_URL=http://127.0.0.1:8081
PORT=8081
```

本地 HTTP 使用 `AUTH_COOKIE_SECURE=false`。部署 HTTPS 后应设置为 true。账号页和聊天页
需要使用同一个主机名：本地统一用 `127.0.0.1`，不要一个用 localhost，另一个用 127.0.0.1。
Cookie 跨端口共享，但不会跨不同主机名共享。修改环境配置后需重启后端与 Streamlit。

```powershell
uv sync --frozen
docker compose up -d postgres
.\.venv\Scripts\python.exe src\run_service.py
```

另一个终端：

```powershell
.\.venv\Scripts\python.exe -m streamlit run src\streamlit_app.py --server.address 127.0.0.1 --server.port 8502
```

打开后端的 `/account`，注册并登录，再点击“进入聊天”。Streamlit 从浏览器请求 Cookie 中
取出登录令牌，调用 `/auth/me` 获取固定用户 UUID。刷新或重开页面时可以恢复登录，直到过期、
退出或修改密码。账号管理页面提供修改密码和退出；旧的聊天分享链接只对原账号有效。

## 接口

| 方法和路径 | 输入或作用 |
| --- | --- |
| `POST /auth/register` | JSON：username、password |
| `POST /auth/login` | JSON：username、password；返回用户和 access_token，同时设置 Cookie |
| `GET /auth/me` | 当前用户，不返回密码哈希 |
| `POST /auth/logout` | 撤销当前登录并清除 Cookie |
| `POST /auth/change-password` | JSON：current_password、new_password；成功后重新登录 |

登录后调用 `/invoke`、`/stream` 时可省略 `user_id`，后端自动填写。新对话更换 `thread_id`，
长期记忆继续使用同一个用户 UUID。`GET /threads` 也可以省略 `user_id`。

`USER_AUTH_ENABLED=false` 保留原有可信客户端模式；启用账号后，`AUTH_SECRET` 不能代替
用户登录凭证。`/info` 和 `/health` 保持公开，聊天、历史和反馈必须认证。

旧匿名用户的记忆不会自动迁移到新账号：无法凭 URL 证明匿名 ID 属于谁，需要另外设计迁移流程。
