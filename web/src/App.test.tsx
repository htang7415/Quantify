import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import type { VerificationResponse } from "./types";

const result: VerificationResponse = {
  verdicts: [{ claim_id: "revenue-growth", verdict: "verified" }],
  requires_agent_resolution: false,
  evidence_scope: {
    source: "SEC EDGAR",
    forms: ["10-K"],
    snapshot_manifest_hash: "e".repeat(64)
  },
  audit_manifest_hash: "a".repeat(64),
  limitation: "This is not investment advice."
};

describe("Quantify web app", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });
  it("shows the product boundary", () => {
    render(<App />);
    expect(screen.getByRole("heading", { name: "Is this claim supported by the declared evidence?" })).toBeInTheDocument();
    expect(screen.getAllByText("Exact scope").length).toBeGreaterThan(0);
    expect(screen.getByRole("heading", { name: "Evidence before explanation." })).toBeInTheDocument();
    expect(screen.getByText("Traceable")).toBeInTheDocument();
    expect(screen.getByText("Ready when you are.")).toBeInTheDocument();
    expect(screen.getByText(/Do not use this tool for price predictions/)).toBeInTheDocument();
  });

  it("does not pretend sign-in works before public Cognito is configured", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("status")).toHaveTextContent("Sign-in is not configured in this preview.");
  });

  it("explains open no-sign-up access when it is enabled", () => {
    vi.stubEnv("VITE_QUANTIFY_TRIAL_URL", "/v1/trial/verify");
    render(<App />);

    expect(screen.getByText(/Open access: no sign-up required/)).toBeInTheDocument();
    expect(screen.getByText(/may slow temporarily/)).toBeInTheDocument();
  });

  it("submits bounded analysis and renders the safe result", async () => {
    const user = userEvent.setup();
    const verify = async () => ({ ...result, report_text: "private source report must never render" }) as VerificationResponse;
    render(<App verifier={verify} />);

    await user.type(
      screen.getByLabelText("Company analysis"),
      "Microsoft revenue increased from fiscal 2023 to fiscal 2024."
    );
    await user.click(screen.getByRole("button", { name: /verify analysis/i }));

    expect(await screen.findByText("revenue-growth")).toBeInTheDocument();
    expect(screen.getByText("SEC EDGAR · 10-K")).toBeInTheDocument();
    expect(screen.getByText("This is not investment advice.")).toBeInTheDocument();
    expect(screen.getByText("e".repeat(64))).toBeInTheDocument();
    expect(screen.getByText("a".repeat(64))).toBeInTheDocument();
    expect(screen.queryByText("private source report must never render")).not.toBeInTheDocument();
    const storedValues = Object.keys(window.sessionStorage).map((key) => window.sessionStorage.getItem(key)).join(" ");
    expect(storedValues).not.toContain("Microsoft revenue increased");
  });

  it("rejects analysis above the product word limit", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.type(screen.getByLabelText("Company analysis"), "word ".repeat(251));
    await user.click(screen.getByRole("button", { name: /verify analysis/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent("250 words or fewer");
  });

  it("makes review-required results prominent without changing the safe contract", async () => {
    const user = userEvent.setup();
    render(<App verifier={async () => ({ ...result, requires_agent_resolution: true, verdicts: [{ claim_id: "ambiguous-claim", verdict: "requires_agent_resolution" }] })} />);

    await user.type(screen.getByLabelText("Company analysis"), "An ambiguous claim.");
    await user.click(screen.getByRole("button", { name: /verify analysis/i }));

    expect(await screen.findByText("Review required.")).toBeInTheDocument();
    expect(screen.getByText("Do not publish automatically; the declared evidence could not resolve this result.")).toBeInTheDocument();
    expect(screen.getByText("Review required", { selector: ".result-badge" })).toBeInTheDocument();
  });
});
