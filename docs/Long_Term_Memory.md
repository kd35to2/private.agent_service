# Research assistant long-term memory

The research assistant reads user memories before each model call. Its tools can save,
list, update, and delete explicitly requested facts and preferences. Memories live in
the namespace `("users", user_id, "research-assistant", "memories")`, independent of
the conversation's `thread_id`. Other agents do not automatically use these memories.

## PostgreSQL configuration

Configure `.env` (never commit it):

```dotenv
DATABASE_TYPE=postgres
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432
POSTGRES_USER=postgres
POSTGRES_PASSWORD=<your local database password>
POSTGRES_DB=agent_service
POSTGRES_IMAGE=postgres:16-alpine
```

Start only the database container, leaving the Python services running locally:

```powershell
docker compose up -d postgres
```

Restart the backend after changing `.env`. The existing service lifespan initializes
the PostgreSQL checkpointer and store tables. Both survive backend restarts; the Docker
database uses the existing `postgres_data` volume. Switching from SQLite does not migrate
old conversations. Keep `checkpoints.db` to retain that history.

## Try it

Choose `research-assistant`. Say "Remember that I prefer Chinese and Python examples."
The assistant should call `remember_memory`. Start a new chat with the same `user_id`
and ask what preferences it remembers. Then ask it to forget the preference; it should
use `forget_memory`. `recall_memories` lists keys when a specific key is needed.

For API calls, explicitly provide a stable `user_id` and change only `thread_id` when
starting another conversation. The current Streamlit app includes `user_id` in its URL;
keep that URL/user ID when reopening it. This ID is not authenticated by the service.

The model receives up to 50 saved memory entries as JSON in its system prompt. This is
key-value memory, not semantic vector search or automatic storage of entire conversations.
Writes happen only through tools; merely configuring the Store does not save preferences.
SQLite mode still uses an in-memory Store and loses these memories on backend restart.
