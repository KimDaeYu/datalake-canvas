import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "./client";

afterEach(() => vi.unstubAllGlobals());

describe("api client", () => {
  it("surfaces the backend's detail message", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "nope" }), { status: 503 })),
    );
    await expect(api.agentQuery("hi", "ds")).rejects.toMatchObject({
      status: 503,
      message: "nope",
    });
  });

  it("explains an unreachable backend", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("failed")));
    const err = await api.health().catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(0);
  });

  it("sends the workflow as JSON and handles 204", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(api.deleteWorkflow("abc")).resolves.toBeUndefined();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/workflows/abc",
      expect.objectContaining({ method: "DELETE" }),
    );
  });
});
