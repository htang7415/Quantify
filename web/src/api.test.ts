import { afterEach, describe, expect, it, vi } from "vitest";
import { parseSafeResponse, verifyAnalysis } from "./api";

const safeResult = {
  verdicts: [{ claim_id: "claim-1", verdict: "verified" }],
  requires_agent_resolution: false,
  evidence_scope: {
    source: "SEC EDGAR",
    forms: ["10-K"],
    snapshot_manifest_hash: "e".repeat(64)
  },
  audit_manifest_hash: "a".repeat(64),
  limitation: "Verdicts apply only to a declared frozen evidence snapshot."
};

describe("safe public-agent response parser", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
    window.sessionStorage.clear();
  });

  it("returns the declared safe contract", () => {
    expect(parseSafeResponse(safeResult)).toEqual(safeResult);
  });

  it("fails closed when a response includes report text", () => {
    expect(() => parseSafeResponse({ ...safeResult, report_text: "private report" })).toThrow(
      "unsafe verification result"
    );
  });

  it("uses the anonymous trial without an authorization header", async () => {
    vi.stubEnv("VITE_QUANTIFY_AGENT_URL", "/v1/agent/verify");
    vi.stubEnv("VITE_QUANTIFY_TRIAL_URL", "/v1/trial/verify");
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(safeResult), { status: 200 })
    );

    await expect(
      verifyAnalysis({ cik: "0000789019", analysis: "Microsoft revenue increased.", as_of_date: "2024-07-30" })
    ).resolves.toEqual(safeResult);

    expect(fetchMock).toHaveBeenCalledWith(
      "/v1/trial/verify",
      expect.objectContaining({
        headers: { "Content-Type": "application/json" },
        method: "POST"
      })
    );
  });

  it("explains an exhausted anonymous limit without retaining the request", async () => {
    vi.stubEnv("VITE_QUANTIFY_TRIAL_URL", "/v1/trial/verify");
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(null, { status: 429 }));

    await expect(
      verifyAnalysis({ cik: "0000789019", analysis: "Microsoft revenue increased.", as_of_date: "2024-07-30" })
    ).rejects.toThrow("anonymous trial limit");
  });
});
