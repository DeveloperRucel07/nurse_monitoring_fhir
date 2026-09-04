import { afterEach, describe, expect, it, vi } from "vitest";
import { z } from "zod";
import { apiRequest, onAuthenticationFailure, setCsrfToken } from "../src/shared/api/http";

afterEach(() => {
  vi.unstubAllGlobals();
  onAuthenticationFailure(null);
  setCsrfToken(null);
});

describe("API security", () => {
  it("meldet abgelaufene Sitzungen zentral und sendet CSRF bei POST", async () => {
    const expired = vi.fn();
    onAuthenticationFailure(expired);
    setCsrfToken("csrf-test-value");
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "Sitzung abgelaufen" }), {
        status: 401,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(apiRequest("/api/test", z.object({ ok: z.boolean() }), { method: "POST", body: {} }))
      .rejects.toEqual(expect.objectContaining({ kind: "unauthorized", status: 401 }));
    expect(expired).toHaveBeenCalledOnce();
    expect(expired).toHaveBeenCalledWith("unauthorized");
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(new Headers(init.headers).get("X-CSRF-Token")).toBe("csrf-test-value");
    expect(init.credentials).toBe("same-origin");
  });
});
