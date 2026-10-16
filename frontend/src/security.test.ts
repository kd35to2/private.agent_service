import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, errorText, jsonBody } from "./api";
import { markdown } from "./markdown";

afterEach(() => vi.unstubAllGlobals());
describe("safe rendering", () => {
  it("removes executable markup and javascript URLs from model responses", () => {
    const html = markdown(
      '<script>alert(1)</script><img src=x onerror=alert(1)><iframe src="https://evil.test"></iframe>[click](javascript:alert%281%29)\n\n**安全文本**',
    );
    expect(html).not.toMatch(/<script|<img|<iframe|onerror|href="javascript:/);
    expect(html).toContain("<strong>安全文本</strong>");
  });
  it("never exposes raw backend details or URLs", () => {
    const message = errorText(
      new ApiError(503, "", "Traceback C:\\private http://secret-host"),
    );
    expect(message).not.toContain("Traceback");
    expect(message).not.toContain("secret-host");
    expect(
      errorText(new ApiError(503, "KNOWLEDGE_BASE_UNAVAILABLE")),
    ).toContain("知识库暂时不可用");
  });
});
describe("session API", () => {
  it("uses the same origin proxy and cookie credentials", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ id: "owner" })));
    vi.stubGlobal("fetch", fetchMock);
    await api("/auth/me");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/auth/me",
      expect.objectContaining({
        credentials: "same-origin",
        cache: "no-store",
      }),
    );
  });
  it("expires protected sessions but keeps invalid login on the login form", async () => {
    const expired = vi.fn();
    window.addEventListener("session-expired", expired);
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockImplementation(() =>
          Promise.resolve(
            new Response(
              JSON.stringify({ detail: "Invalid username or password" }),
              { status: 401 },
            ),
          ),
        ),
    );
    await expect(api("/auth/login", jsonBody({}))).rejects.toMatchObject({
      status: 401,
    });
    expect(expired).not.toHaveBeenCalled();
    await expect(api("/knowledge/documents")).rejects.toMatchObject({
      status: 401,
    });
    expect(expired).toHaveBeenCalledOnce();
    window.removeEventListener("session-expired", expired);
  });
});
