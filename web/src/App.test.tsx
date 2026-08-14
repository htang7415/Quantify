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
    render(<App initialPath="/agent" />);
    expect(screen.getByRole("heading", { name: "Is this claim supported by the declared evidence?" })).toBeInTheDocument();
    expect(screen.getAllByText("Exact scope").length).toBeGreaterThan(0);
    expect(screen.getByRole("heading", { name: "Evidence before explanation." })).toBeInTheDocument();
    expect(screen.getByText("Traceable")).toBeInTheDocument();
    expect(screen.getByText("Ready when you are.")).toBeInTheDocument();
    expect(screen.getByText(/Do not use this tool for price predictions/)).toBeInTheDocument();
  });

  it("does not pretend sign-in works before public Cognito is configured", async () => {
    const user = userEvent.setup();
    render(<App initialPath="/agent" />);

    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("status")).toHaveTextContent("Sign-in is not configured in this preview.");
  });

  it("explains open no-sign-up access when it is enabled", () => {
    vi.stubEnv("VITE_QUANTIFY_TRIAL_URL", "/v1/trial/verify");
    render(<App initialPath="/agent" />);

    expect(screen.getByText(/Open access: no sign-up required/)).toBeInTheDocument();
    expect(screen.getByText(/may slow temporarily/)).toBeInTheDocument();
  });

  it("submits bounded analysis and renders the safe result", async () => {
    const user = userEvent.setup();
    const verify = async () => ({ ...result, report_text: "private source report must never render" }) as VerificationResponse;
    render(<App initialPath="/agent" verifier={verify} />);

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
    render(<App initialPath="/agent" />);

    await user.type(screen.getByLabelText("Company analysis"), "word ".repeat(251));
    await user.click(screen.getByRole("button", { name: /verify analysis/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent("250 words or fewer");
  });

  it("makes review-required results prominent without changing the safe contract", async () => {
    const user = userEvent.setup();
    render(<App initialPath="/agent" verifier={async () => ({ ...result, requires_agent_resolution: true, verdicts: [{ claim_id: "ambiguous-claim", verdict: "requires_agent_resolution" }] })} />);

    await user.type(screen.getByLabelText("Company analysis"), "An ambiguous claim.");
    await user.click(screen.getByRole("button", { name: /verify analysis/i }));

    expect(await screen.findByText("Review required.")).toBeInTheDocument();
    expect(screen.getByText("Do not publish automatically; the declared evidence could not resolve this result.")).toBeInTheDocument();
    expect(screen.getByText("Review required", { selector: ".result-badge" })).toBeInTheDocument();
  });

  it("shows the connected public overview without inventing unavailable market data", () => {
    render(<App initialPath="/" />);

    expect(screen.getByRole("link", { name: "Quantify home" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Verify a claim" })).toHaveAttribute("href", "/agent");
    expect(screen.getByRole("heading", { name: /See where capital is/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "What changed in the release" })).toBeInTheDocument();
    expect(screen.getAllByText("Release required").length).toBeGreaterThan(0);
    expect(screen.getByRole("heading", { name: "Official layers active" })).toBeInTheDocument();
  });

  it("shows the public investor terminal with the declared filing scope", () => {
    render(<App initialPath="/investors" />);

    expect(screen.getByRole("heading", { name: /Follow the money/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Tracked managers" })).toBeInTheDocument();
    expect(screen.getByText("Altimeter Capital")).toBeInTheDocument();
    expect(screen.getByText("Pershing Square")).toBeInTheDocument();
    expect(screen.getByText("SEC 13F · FROZEN")).toBeInTheDocument();
    expect(screen.getByText(/Values and weights cover only securities disclosed/)).toBeInTheDocument();
  });

  it("keeps one product navigation between investors and the agent", () => {
    const { rerender } = render(<App initialPath="/investors" />);
    expect(screen.getByRole("link", { name: "Investors" })).toHaveClass("active");

    rerender(<App initialPath="/agent" />);

    expect(screen.getByRole("link", { name: "Quantify home" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Overview" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign in" })).toBeInTheDocument();
  });

  it("filters managers without changing the frozen catalog", async () => {
    const user = userEvent.setup();
    render(<App initialPath="/investors" />);

    await user.type(screen.getByPlaceholderText("Manager or theme"), "Pershing");

    expect(screen.getByText("Pershing Square")).toBeInTheDocument();
    expect(screen.queryByText("Altimeter Capital")).not.toBeInTheDocument();
  });

  it("renders the five public-market investor modules", () => {
    render(<App initialPath="/investors/altimeter-capital" />);

    expect(screen.getByRole("heading", { name: /Altimeter Capital/ })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Holdings" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Changes" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Allocation" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "History" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /SEC filing/i })).toHaveAttribute("href", expect.stringMatching(/^https:\/\/www\.sec\.gov\//));
  });

  it("withholds derived values when a filing fails the source-integrity check", () => {
    render(<App initialPath="/investors/duquesne-family-office" />);

    expect(screen.getByRole("heading", { name: "Duquesne Family Office" })).toBeInTheDocument();
    expect(screen.getByText(/derived metrics are withheld pending source review/i)).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Holdings" })).not.toBeInTheDocument();
  });

  it("connects an exact company mapping to released reporting-manager rows", () => {
    render(<App initialPath="/companies/nvda" />);

    expect(screen.getByRole("heading", { name: /NVIDIA CORPORATION/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Reporting managers" })).toBeInTheDocument();
    expect(screen.getByText("Sum across tracked managers")).toBeInTheDocument();
    expect(screen.getByText(/not market capitalization, total institutional ownership/i)).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /SEC/i }).length).toBeGreaterThan(0);
  });

  it("connects a company to exact released SEC earnings when covered", () => {
    render(<App initialPath="/companies/aapl" />);

    expect(screen.getByRole("heading", { name: "Reported earnings" })).toBeInTheDocument();
    expect(screen.getByText("$111.18B")).toBeInTheDocument();
    expect(screen.getByText("↑ 16.6% YoY")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /0000320193-26-000013/i })).toHaveAttribute("href", expect.stringMatching(/^https:\/\/www\.sec\.gov\/Archives\//));
  });

  it("connects NVDA only to the exact product-naming export rule", () => {
    render(<App initialPath="/companies/nvda" />);

    expect(screen.getByRole("heading", { name: "Named policy scope" })).toBeInTheDocument();
    expect(screen.getByText("NVIDIA H200 · AMD MI325X")).toBeInTheDocument();
    expect(screen.getByText(/does not establish revenue exposure/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Official source/i })).toHaveAttribute("href", expect.stringMatching(/^https:\/\/www\.federalregister\.gov\//));
  });

  it("lists company ownership views derived from the same frozen release", async () => {
    const user = userEvent.setup();
    render(<App initialPath="/companies" />);

    await user.type(screen.getByPlaceholderText("Ticker, issuer, or theme"), "NVDA");

    expect(screen.getByText("NVIDIA CORPORATION")).toBeInTheDocument();
    expect(screen.queryByText("APPLE INC")).not.toBeInTheDocument();
  });

  it("renders released ETP exposure while keeping crypto market data fail-closed", () => {
    render(<App initialPath="/markets/crypto" />);

    expect(screen.getByRole("heading", { name: /Crypto data, when it can be traced/i })).toBeInTheDocument();
    expect(screen.getByText("NO ACTIVE CRYPTO MARKET RELEASE")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Reported ETP exposure" })).toBeInTheDocument();
    expect(screen.getByText("BTC / IBIT")).toBeInTheDocument();
    expect(screen.getByText("Coatue Management")).toBeInTheDocument();
    expect(screen.getByText(/not direct token ownership/i)).toBeInTheDocument();
    expect(screen.queryByText("$118,400")).not.toBeInTheDocument();
  });

  it("renders the official Treasury curve as an independently released rates layer", () => {
    render(<App initialPath="/markets/rates" />);

    expect(screen.getByRole("heading", { name: "U.S. Treasury curve." })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /Treasury yield curve observed 2026-08-13/i })).toBeInTheDocument();
    expect(screen.getByText("2s10s")).toBeInTheDocument();
    expect(screen.getByText("+0.48 pp")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /U.S. Treasury source/i })).toHaveAttribute("href", expect.stringMatching(/^https:\/\/home\.treasury\.gov\//));
    expect(screen.getByText(/not a forecast or trading signal/i)).toBeInTheDocument();
  });

  it("renders the bounded BLS macro release with explicit calculations and terms", () => {
    render(<App initialPath="/markets/macro" />);

    expect(screen.getByRole("heading", { name: "Three signals. Exact scope." })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Current release" })).toBeInTheDocument();
    expect(screen.getByText("3.4%")).toBeInTheDocument();
    expect(screen.getByText("2.5%")).toBeInTheDocument();
    expect(screen.getByText("4.1%")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /BLS data terms/i })).toHaveAttribute("href", expect.stringMatching(/^https:\/\/www\.bls\.gov\//));
    expect(screen.getByText(/BLS.gov cannot vouch/i)).toBeInTheDocument();
    expect(screen.getByText(/not a live macroeconomic feed or forecast/i)).toBeInTheDocument();
  });

  it("keeps intelligence empty until an eligible event release exists", () => {
    render(<App initialPath="/intelligence" />);

    expect(screen.getByRole("heading", { name: /What happened. What changed/i })).toBeInTheDocument();
    expect(screen.getByText("EARNINGS + POLICY AVAILABLE")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /Available/i })).toHaveLength(2);
    expect(screen.getAllByText("Release required")).toHaveLength(2);
  });

  it("renders reported earnings without estimates or prediction labels", () => {
    render(<App initialPath="/intelligence/earnings" />);

    expect(screen.getByRole("heading", { name: "Reported results. Nothing invented." })).toBeInTheDocument();
    expect(screen.getByText("$111.18B")).toBeInTheDocument();
    expect(screen.getByText("$82.89B")).toBeInTheDocument();
    expect(screen.getByText("$2.01")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /SEC filing/i })).toHaveLength(2);
    expect(screen.queryByText(/beat estimates/i)).not.toBeInTheDocument();
  });

  it("renders typed policy actions without market-direction claims", () => {
    render(<App initialPath="/intelligence/policy" />);

    expect(screen.getByRole("heading", { name: "Action, scope, effective date." })).toBeInTheDocument();
    expect(screen.getByText("3.50–3.75%")).toBeInTheDocument();
    expect(screen.getByText("EFFECTIVE 2026-10-01")).toBeInTheDocument();
    expect(screen.getByText("NVIDIA H200 · AMD MI325X")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /Official source/i })).toHaveLength(3);
    expect(screen.queryByText(/stocks.*up|stocks.*down|cut probability/i)).not.toBeInTheDocument();
  });
});
