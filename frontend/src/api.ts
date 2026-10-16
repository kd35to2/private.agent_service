export class ApiError extends Error {
  constructor(
    public status: number,
    public code = "",
    message = "",
  ) {
    super(message);
  }
}

const messages: Record<string, string> = {
  KNOWLEDGE_BASE_UNAVAILABLE: "知识库暂时不可用，请稍后重试。",
  DOCUMENT_NOT_FOUND: "这份文档不存在，或你没有查看权限。",
  DOCUMENT_BUSY: "这份文档正在处理中，请稍后重试。",
  DOCUMENT_CONFLICT: "文档发生了变化，请刷新后再操作。",
  DOCUMENT_INVALID: "文件无法解析，请检查文件格式和内容。",
  DOCUMENT_PROCESSING_FAILED: "文档处理失败，请检查文件后重新上传。",
  AGENT_EXECUTION_FAILED: "本次回答未能完成，请稍后重试。",
  SERVICE_UNAVAILABLE: "服务暂时不可用，请稍后重试。",
  SESSION_EXPIRED: "登录已过期，请重新登录。",
  PERMISSION_DENIED: "你没有执行此操作的权限。",
  INVALID_REQUEST: "提交内容不符合要求，请检查后重试。",
  NETWORK_ERROR: "连接中断，请检查网络或后端服务。",
  INVALID_RESPONSE: "响应未完整接收，请重试或重新打开会话。",
};
const authMessages: Record<string, string> = {
  "Invalid username or password": "用户名或密码不正确。",
  "Username already exists": "这个用户名已被注册。",
  "Current password is incorrect": "当前密码不正确。",
  "Too many login attempts; try again in five minutes":
    "尝试次数过多，请五分钟后再试。",
};

export function errorText(error: unknown): string {
  if (error instanceof ApiError) {
    if (messages[error.code]) return messages[error.code]!;
    if (authMessages[error.message]) return authMessages[error.message]!;
    if (error.status === 401) return messages.SESSION_EXPIRED!;
    if (error.status === 403) return "请求被拒绝，请刷新页面后重试。";
    if (error.status === 413) return "文件超过了服务允许的大小，请缩小后重试。";
    if (error.status === 422 || error.status === 400)
      return messages.INVALID_REQUEST!;
    if (error.status === 429) return "请求过于频繁，请稍后重试。";
    if (error.status === 404) return "请求的内容不存在或已被删除。";
  }
  return "操作未完成，请检查网络和服务状态后重试。";
}

export async function checkedResponse(
  path: string,
  init: RequestInit = {},
): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      ...init,
      credentials: "same-origin",
      cache: "no-store",
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError")
      throw error;
    throw new ApiError(0, "NETWORK_ERROR");
  }
  if (!response.ok) {
    let body: { detail?: unknown } = {};
    try {
      body = await response.json();
    } catch {
      /* Proxies may return HTML; never render it. */
    }
    const detail = body.detail;
    const structured =
      typeof detail === "object" && detail !== null
        ? (detail as Record<string, unknown>)
        : {};
    const error = new ApiError(
      response.status,
      typeof structured.code === "string" ? structured.code : "",
      typeof detail === "string" ? detail : "",
    );
    if (
      response.status === 401 &&
      path !== "/auth/login" &&
      path !== "/auth/register" &&
      path !== "/auth/me"
    ) {
      window.dispatchEvent(new Event("session-expired"));
    }
    throw error;
  }
  return response;
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await checkedResponse(path, init);
  return response.status === 204 ? (undefined as T) : response.json();
}

export function jsonBody(body: unknown): RequestInit {
  return {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}
