import type { VerificationRequest, VerificationResponse } from "./types";
import { accessToken, verifyScopeGranted } from "./auth";
import type { Verdict } from "./types";

const DEVELOPMENT_DEMO_RESULT: VerificationResponse = {
  verdicts: [{ claim_id: "claim-1", verdict: "verified" }],
  requires_agent_resolution: false,
  evidence_scope: {
    source: "SEC EDGAR",
    forms: ["10-K", "10-Q"],
    snapshot_manifest_hash: "e".repeat(64)
  },
  audit_manifest_hash: "a".repeat(64),
  limitation:
    "Verdicts apply only to the declared frozen SEC evidence snapshot; they are not investment advice."
};

export async function verifyAnalysis(
  request: VerificationRequest
): Promise<VerificationResponse> {
  const authenticatedEndpoint = import.meta.env.VITE_QUANTIFY_AGENT_URL;
  const trialEndpoint = import.meta.env.VITE_QUANTIFY_TRIAL_URL;

  if (!authenticatedEndpoint && !trialEndpoint) {
    if (import.meta.env.DEV) {
      return DEVELOPMENT_DEMO_RESULT;
    }
    throw new Error("Libration verification is not configured for this environment.");
  }

  const token = accessToken();
  const authenticated = Boolean(token && verifyScopeGranted());
  if (!authenticated && !trialEndpoint) {
    throw new Error("Sign in is required before verifying analysis.");
  }
  const endpoint = authenticated ? authenticatedEndpoint : trialEndpoint;
  if (!endpoint) throw new Error("Libration verification is not configured for this environment.");

  const response = await fetch(endpoint, {
    method: "POST",
    headers: {
      ...(authenticated ? { Authorization: `Bearer ${token}` } : {}),
      "Content-Type": "application/json"
    },
    body: JSON.stringify(request)
  });

  if (response.status === 429) {
    throw new Error("The open agent has reached a temporary capacity limit. Please try again shortly.");
  }
  if (!authenticated && response.status === 503) {
    throw new Error("The open agent is temporarily unavailable. Please try again later.");
  }
  if (!response.ok) {
    throw new Error("Libration verification is currently unavailable.");
  }
  return parseSafeResponse(await response.json());
}

const verdicts = new Set<Verdict>([
  "verified",
  "unsupported",
  "defeated",
  "qualified",
  "requires_agent_resolution"
]);
const responseKeys = new Set([
  "verdicts",
  "requires_agent_resolution",
  "evidence_scope",
  "audit_manifest_hash",
  "limitation"
]);

function stringValue(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

/** Retain only the public agent contract; do not keep unexpected response data. */
export function parseSafeResponse(payload: unknown): VerificationResponse {
  if (!payload || typeof payload !== "object") throw new Error("Libration returned an invalid verification result.");
  const value = payload as Record<string, unknown>;
  if (Object.keys(value).length !== responseKeys.size || !Object.keys(value).every((key) => responseKeys.has(key))) {
    throw new Error("Libration returned an unsafe verification result.");
  }
  const rawVerdicts = value.verdicts;
  const evidence = value.evidence_scope;
  if (!Array.isArray(rawVerdicts) || !evidence || typeof evidence !== "object") {
    throw new Error("Libration returned an invalid verification result.");
  }
  const safeVerdicts = rawVerdicts.map((item) => {
    if (!item || typeof item !== "object") throw new Error("Libration returned an invalid verification result.");
    const claim = item as Record<string, unknown>;
    const claimId = stringValue(claim.claim_id);
    const verdict = stringValue(claim.verdict);
    if (Object.keys(claim).length !== 2 || !Object.hasOwn(claim, "claim_id") || !Object.hasOwn(claim, "verdict") || !claimId || !verdict || !verdicts.has(verdict as Verdict)) {
      throw new Error("Libration returned an invalid verification result.");
    }
    return { claim_id: claimId, verdict: verdict as Verdict };
  });
  const safeEvidence = evidence as Record<string, unknown>;
  const source = stringValue(safeEvidence.source);
  const forms = safeEvidence.forms;
  const snapshot = stringValue(safeEvidence.snapshot_manifest_hash);
  const audit = stringValue(value.audit_manifest_hash);
  const limitation = stringValue(value.limitation);
  if (Object.keys(safeEvidence).length !== 3 || !Object.hasOwn(safeEvidence, "source") || !Object.hasOwn(safeEvidence, "forms") || !Object.hasOwn(safeEvidence, "snapshot_manifest_hash") || !source || !Array.isArray(forms) || !forms.every((form) => typeof form === "string") || !snapshot || !audit || !limitation || typeof value.requires_agent_resolution !== "boolean") {
    throw new Error("Libration returned an invalid verification result.");
  }
  return {
    verdicts: safeVerdicts,
    requires_agent_resolution: value.requires_agent_resolution,
    evidence_scope: { source, forms, snapshot_manifest_hash: snapshot },
    audit_manifest_hash: audit,
    limitation
  };
}
