"""Public error codes shared by the service and its client."""

PUBLIC_ERROR_MESSAGES = {
    "DOCUMENT_NOT_FOUND": "未找到该文档或你无权访问。",
    "DOCUMENT_BUSY": "文档正在处理，请稍后重试。",
    "DOCUMENT_CONFLICT": "已有同名文档，请使用更新功能。",
    "DOCUMENT_INVALID": "文件无法解析或未提取到有效文本，请检查格式和文件大小。",
    "DOCUMENT_PROCESSING_FAILED": "文档处理失败，旧版本仍保留；可稍后重新索引。",
    "KNOWLEDGE_BASE_UNAVAILABLE": "知识库暂不可用，请联系管理员完成配置后再试。",
    "AGENT_EXECUTION_FAILED": "本次回答未能完成，请稍后重试。",
    "SERVICE_UNAVAILABLE": "服务暂时不可用，请稍后重试。",
    "INVALID_RESPONSE": "服务返回异常，请稍后重试。",
    "SESSION_EXPIRED": "登录已过期，请重新登录。",
    "PERMISSION_DENIED": "你无权访问这段会话。",
    "INVALID_REQUEST": "请求内容无效，请检查输入后重试。",
    "NETWORK_ERROR": "暂时无法连接服务，请稍后重试。",
}


class AgentServiceError(RuntimeError):
    def __init__(self, code: str, *, detail: str, status_code: int = 503):
        self.code = code
        self.detail = detail
        self.status_code = status_code
        super().__init__(PUBLIC_ERROR_MESSAGES[code])

    def public_payload(self) -> dict[str, str]:
        return {"code": self.code, "message": str(self)}
