import { afterEach, expect, test, vi } from "vitest";
import { api } from "../src/services/api";

afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });

test("a stalled live read times out so the next poll can recover", async () => {
  vi.useFakeTimers();
  vi.stubGlobal("fetch", (_path: string, options: RequestInit) => new Promise((_resolve, reject) => {
    options.signal?.addEventListener("abort", () => reject(options.signal?.reason), { once: true });
  }));
  const result = expect(api.research()).rejects.toThrow("REQUEST_TIMEOUT");
  await vi.advanceTimersByTimeAsync(15_001);
  await result;
  vi.stubGlobal("fetch", async () => new Response(JSON.stringify({ data_status: "LIVE" }), { status: 200 }));
  expect(await api.research()).toEqual({ data_status: "LIVE" });
});
