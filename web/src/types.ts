export type Verdict =
  | "verified"
  | "unsupported"
  | "defeated"
  | "qualified"
  | "requires_agent_resolution";

export type VerificationRequest = {
  cik: string;
  analysis: string;
  as_of_date: string;
};

export type VerificationResponse = {
  verdicts: Array<{ claim_id: string; verdict: Verdict }>;
  requires_agent_resolution: boolean;
  evidence_scope: {
    source: string;
    forms: string[];
    snapshot_manifest_hash: string;
  };
  audit_manifest_hash: string;
  limitation: string;
};
