import { describe, expect, it } from "vitest";
import { parseSafeResponse } from "./api";

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
  it("returns the declared safe contract", () => {
    expect(parseSafeResponse(safeResult)).toEqual(safeResult);
  });

  it("fails closed when a response includes report text", () => {
    expect(() => parseSafeResponse({ ...safeResult, report_text: "private report" })).toThrow(
      "unsafe verification result"
    );
  });
});
