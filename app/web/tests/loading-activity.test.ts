import { afterEach, describe, expect, it, vi } from "vitest";
import { isBusy, track } from "@/lib/client/activity";
import { callAgent } from "@/lib/client/api";
import { KbListResponse } from "@/lib/contract/schemas";

const messages = { network: "n", invalidResponse: "i", noResult: "r" };

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("the loading bar's activity", () => {
  it("is busy until every tracked request settles, a failed one included", async () => {
    let finish: (value: string) => void = () => {};
    const slow = track(new Promise<string>((resolve) => (finish = resolve)));
    const failed = track(Promise.reject(new Error("boom"))).catch(() => "caught");
    expect(isBusy()).toBe(true);
    await failed;
    expect(isBusy()).toBe(true);
    finish("done");
    await slow;
    expect(isBusy()).toBe(false);
  });

  it("counts a call to the agents while its answer is on its way", async () => {
    let answer: (response: Response) => void = () => {};
    vi.stubGlobal("fetch", () => new Promise<Response>((resolve) => (answer = resolve)));
    const call = callAgent({ action: "kb.list", prefix: "general/" }, KbListResponse, { locale: "fr", messages });
    expect(isBusy()).toBe(true);
    answer(new Response(JSON.stringify({ items: [] }), { status: 200 }));
    await call.catch(() => null);
    expect(isBusy()).toBe(false);
  });
});
