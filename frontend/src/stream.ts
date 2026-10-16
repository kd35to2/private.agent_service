import { ApiError } from "./api";
import type { ChatMessage } from "./types";

export type StreamEvent =
  | { type: "message"; content: ChatMessage }
  | { type: "token"; content: string }
  | { type: "error"; code: string; message?: string };

export async function readStream(
  response: Response,
  onEvent: (event: StreamEvent) => void,
): Promise<void> {
  if (!response.body) throw new ApiError(0, "INVALID_RESPONSE");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let done = false;
  let data: string[] = [];
  function dispatch() {
    if (!data.length) return;
    const payload = data.join("\n");
    data = [];
    if (payload === "[DONE]") {
      done = true;
      return;
    }
    let event: StreamEvent;
    try {
      event = JSON.parse(payload);
    } catch {
      throw new ApiError(0, "INVALID_RESPONSE");
    }
    if (event.type === "error")
      throw new ApiError(503, event.code || "AGENT_EXECUTION_FAILED");
    if (event.type === "message" || event.type === "token") onEvent(event);
  }
  try {
    while (!done) {
      const part = await reader.read();
      buffer += decoder.decode(part.value, { stream: !part.done });
      let newline: number;
      while ((newline = buffer.indexOf("\n")) >= 0) {
        const line = buffer.slice(0, newline).replace(/\r$/, "");
        buffer = buffer.slice(newline + 1);
        if (!line) dispatch();
        else if (line.startsWith("data:"))
          data.push(line.slice(5).replace(/^ /, ""));
        if (done) break;
      }
      if (part.done) {
        if (buffer.startsWith("data:")) data.push(buffer.slice(5).trim());
        dispatch();
        break;
      }
    }
    if (!done) throw new ApiError(0, "INVALID_RESPONSE");
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}
