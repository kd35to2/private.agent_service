import { describe, expect, it } from "vitest";
import { readStream } from "./stream";
import type { StreamEvent } from "./stream";

function response(parts: Uint8Array[]) {
  return new Response(
    new ReadableStream({
      start(controller) {
        for (const part of parts) controller.enqueue(part);
        controller.close();
      },
    }),
  );
}
const encode = (text: string) => new TextEncoder().encode(text);

describe("SSE protocol", () => {
  it("handles byte boundaries inside Chinese text, CRLF and multiple events", async () => {
    const bytes = encode(
      'data: {"type":"token","content":"知识"}\r\n\r\ndata: {"type":"message","content":{"type":"ai","content":"答案","custom_data":{"citations":[]}}}\n\ndata: [DONE]\n\n',
    );
    const events: StreamEvent[] = [];
    await readStream(
      response(Array.from(bytes, (byte) => new Uint8Array([byte]))),
      (event) => events.push(event),
    );
    expect(events).toHaveLength(2);
    expect(events[0]).toEqual({ type: "token", content: "知识" });
    expect(events[1]).toMatchObject({ content: { content: "答案" } });
  });
  it("rejects a disconnected stream instead of treating partial output as complete", async () => {
    await expect(
      readStream(
        response([encode('data: {"type":"token","content":"partial"}\n\n')]),
        () => {},
      ),
    ).rejects.toMatchObject({ code: "INVALID_RESPONSE" });
  });
  it("propagates only the public error code", async () => {
    await expect(
      readStream(
        response([
          encode(
            'data: {"type":"error","code":"KNOWLEDGE_BASE_UNAVAILABLE","message":"internal stack trace"}\n\n',
          ),
        ]),
        () => {},
      ),
    ).rejects.toMatchObject({
      code: "KNOWLEDGE_BASE_UNAVAILABLE",
      message: "",
    });
  });
  it("rejects malformed JSON and releases the reader", async () => {
    const stream = response([encode("data: broken\n\n")]);
    await expect(readStream(stream, () => {})).rejects.toMatchObject({
      code: "INVALID_RESPONSE",
    });
    expect(stream.body?.locked).toBe(false);
  });
});
