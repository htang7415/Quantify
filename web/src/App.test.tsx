import { render, screen, within } from "@testing-library/react";
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

describe("Libration web app", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });
  it("shows the product boundary", () => {
    render(<App initialPath="/agent" />);
    expect(screen.getByRole("heading", { name: "Verify one company claim." })).toBeInTheDocument();
    expect(screen.getByText("Data · released")).toBeInTheDocument();
    expect(screen.getByText("AI analysis · gated")).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Libration agent operating model" })).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Claim in. Evidence out." })).toBeInTheDocument();
    expect(screen.getByText("Ready when you are.")).toBeInTheDocument();
    expect(screen.getByText(/Do not use this tool for price predictions/)).toBeInTheDocument();
    expect(screen.getByLabelText("Current verification contract")).toHaveTextContent("2 companies");
    expect(screen.getByRole("group", { name: "01 · Define scope" })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "02 · Write one claim" })).toBeInTheDocument();
    expect(screen.getByLabelText("Task readiness")).toHaveTextContent("Add one factual claim");
    expect(screen.queryByLabelText("Current agent task context")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Skip to content" })).toHaveAttribute("href", "#main-content");
    expect(document.getElementById("main-content")).toHaveAttribute("tabindex", "-1");
    expect(screen.getByLabelText("Claim to verify")).toHaveAttribute(
      "aria-describedby",
      "analysis-word-limit analysis-claim-note analysis-data-note analysis-safety-note"
    );
  });

  it("loads the released verification example without submitting it", async () => {
    const user = userEvent.setup();
    const verifier = vi.fn(async () => result);
    render(<App initialPath="/agent" verifier={verifier} />);

    await user.click(screen.getByRole("button", { name: "Use released Microsoft example" }));

    expect(screen.getByLabelText("Claim to verify")).toHaveValue("Microsoft revenue increased from fiscal 2023 to fiscal 2024.");
    expect(screen.getByLabelText("Claim as-of date")).toHaveValue("2024-07-30");
    expect(screen.getByLabelText("Task readiness")).toHaveTextContent("Ready to verify");
    expect(verifier).not.toHaveBeenCalled();
  });

  it("preselects an allowlisted company from research without submitting a claim", () => {
    const verifier = vi.fn(async () => result);
    render(<App initialPath="/agent?company=0000320193" verifier={verifier} />);

    expect(screen.getByLabelText("Company")).toHaveValue("0000320193");
    expect(screen.getByLabelText("Task readiness")).toHaveTextContent("Add one factual claim · Apple");
    expect(screen.getByLabelText("Claim to verify")).toHaveValue("");
    expect(verifier).not.toHaveBeenCalled();
  });

  it("fails a malformed company deep link closed to the existing default scope", () => {
    render(<App initialPath="/agent?company=unsupported" />);

    expect(screen.getByLabelText("Company")).toHaveValue("0000789019");
    expect(screen.getByLabelText("Task readiness")).toHaveTextContent("Microsoft");
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
      screen.getByLabelText("Claim to verify"),
      "Microsoft revenue increased from fiscal 2023 to fiscal 2024."
    );
    await user.click(screen.getByRole("button", { name: /verify claim/i }));

    expect(await screen.findByText("revenue-growth")).toBeInTheDocument();
    expect(screen.getByText("SEC EDGAR · 10-K")).toBeInTheDocument();
    expect(screen.getByText("This is not investment advice.")).toBeInTheDocument();
    expect(screen.getByText("e".repeat(64))).toBeInTheDocument();
    expect(screen.getByText("a".repeat(64))).toBeInTheDocument();
    const evidenceDisclosure = screen.getByText("Evidence, audit, and limitations").closest("details");
    expect(evidenceDisclosure).not.toHaveAttribute("open");
    await user.click(screen.getByText("Evidence, audit, and limitations"));
    expect(evidenceDisclosure).toHaveAttribute("open");
    expect(screen.queryByText("private source report must never render")).not.toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Result next actions" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Check coverage" })).toHaveAttribute("href", "/coverage");
    expect(screen.getByRole("link", { name: "Review methodology" })).toHaveAttribute("href", "/methodology");
    await user.click(screen.getByRole("button", { name: "Verify another claim" }));
    expect(screen.getByLabelText("Claim to verify")).toHaveValue("");
    expect(screen.getByText("Ready when you are.")).toBeInTheDocument();
    const storedValues = Object.keys(window.sessionStorage).map((key) => window.sessionStorage.getItem(key)).join(" ");
    expect(storedValues).not.toContain("Microsoft revenue increased");
  });

  it("rejects analysis above the product word limit", async () => {
    const user = userEvent.setup();
    render(<App initialPath="/agent" />);

    await user.type(screen.getByLabelText("Claim to verify"), "word ".repeat(251));
    expect(screen.getByLabelText("Task readiness")).toHaveTextContent("Shorten the claim to 250 words");
    await user.click(screen.getByRole("button", { name: /verify claim/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent("250 words or fewer");
  });

  it("requires a complete scope before verification", async () => {
    const user = userEvent.setup();
    const verifier = vi.fn(async () => result);
    render(<App initialPath="/agent" verifier={verifier} />);

    await user.clear(screen.getByLabelText("Claim as-of date"));
    await user.type(screen.getByLabelText("Claim to verify"), "Microsoft revenue increased.");
    expect(screen.getByLabelText("Task readiness")).toHaveTextContent("Complete the scope");
    await user.click(screen.getByRole("button", { name: /verify claim/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Choose a company and claim as-of date.");
    expect(verifier).not.toHaveBeenCalled();
  });

  it("clears a stale result when the task scope changes", async () => {
    const user = userEvent.setup();
    render(<App initialPath="/agent" verifier={async () => result} />);

    await user.type(screen.getByLabelText("Claim to verify"), "Microsoft revenue increased.");
    await user.click(screen.getByRole("button", { name: /verify claim/i }));
    expect(await screen.findByText("revenue-growth")).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Company"), "0000320193");
    expect(screen.queryByText("revenue-growth")).not.toBeInTheDocument();
    expect(screen.getByText("Ready when you are.")).toBeInTheDocument();
    expect(screen.getByLabelText("Task readiness")).toHaveTextContent("Apple");
  });

  it("makes review-required results prominent without changing the safe contract", async () => {
    const user = userEvent.setup();
    render(<App initialPath="/agent" verifier={async () => ({ ...result, requires_agent_resolution: true, verdicts: [{ claim_id: "ambiguous-claim", verdict: "requires_agent_resolution" }] })} />);

    await user.type(screen.getByLabelText("Claim to verify"), "An ambiguous claim.");
    await user.click(screen.getByRole("button", { name: /verify claim/i }));

    expect(await screen.findByText("Review required.")).toBeInTheDocument();
    expect(screen.getByText("Do not publish automatically; the declared evidence could not resolve this result.")).toBeInTheDocument();
    expect(screen.getByText("Review required", { selector: ".result-badge" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Revise claim" }));
    expect(screen.getByLabelText("Claim to verify")).toHaveValue("An ambiguous claim.");
    expect(screen.getByText("Ready when you are.")).toBeInTheDocument();
  });

  it("shows the commercial research overview with a versioned verification sample", () => {
    render(<App initialPath="/" />);

    const brand = screen.getByRole("link", { name: "Libration home" });
    expect(brand).toBeInTheDocument();
    expect(brand.querySelector("svg.site-brand-mark")).toBeInTheDocument();
    expect(brand.querySelectorAll(".libration-arc")).toHaveLength(2);
    expect(screen.getAllByRole("link", { name: "Verify a claim" })[0]).toHaveAttribute("href", "/agent");
    expect(screen.getByRole("heading", { name: "See more of what matters." })).toBeInTheDocument();
    expect(screen.getByText(/For investors, analysts, and curious learners/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Explore companies/i })).toHaveAttribute("href", "/companies");
    expect(screen.getByLabelText("Versioned verification sample")).toHaveTextContent("Libration · Verification sample");
    expect(screen.getByLabelText("Versioned verification sample")).toHaveTextContent("Microsoft · FY2024 10-K · SEC filing scope");
    expect(screen.getByLabelText("Versioned verification sample")).toHaveTextContent("The released filing supports this claim.");
    expect(screen.getByLabelText("Versioned verification sample")).toHaveTextContent("$245.12B");
    expect(screen.getByLabelText("Versioned verification sample")).toHaveTextContent("Audit 75b9cf2d09…90722e");
    expect(screen.getByText("Evidence and audit details")).toBeInTheDocument();
    expect(screen.getByLabelText("Product boundaries")).toHaveTextContent("9 of 12 catalogs released");
    const releasedResearch = screen.getByRole("heading", { name: "Start with the evidence." }).closest("section");
    expect(releasedResearch?.querySelectorAll(".research-entry-grid > a")).toHaveLength(4);
    expect(within(releasedResearch as HTMLElement).getByRole("link", { name: /Companies.*Open companies/i })).toHaveAttribute("href", "/companies");
    expect(within(releasedResearch as HTMLElement).getByRole("link", { name: /Markets.*Open markets/i })).toHaveAttribute("href", "/markets");
    expect(within(releasedResearch as HTMLElement).getByRole("link", { name: /Investors.*Open investors/i })).toHaveAttribute("href", "/investors");
    expect(within(releasedResearch as HTMLElement).getByRole("link", { name: /Policy.*Open policy/i })).toHaveAttribute("href", "/intelligence/policy");
    expect(screen.getByRole("heading", { name: "Ask clearly. See what supports the result." })).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Libration agent operating model" })).not.toBeInTheDocument();
    expect(screen.getByText("AI research answers not public")).toBeInTheDocument();
    const currentTask = screen.getByRole("heading", { name: "Check one claim." }).closest("section");
    expect(releasedResearch?.compareDocumentPosition(currentTask as Node)).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING
    );
    expect(screen.getByRole("link", { name: "Read the methodology →" })).toHaveAttribute("href", "/methodology");
    expect(screen.getByText(/Unavailable data stays unavailable/)).toBeInTheDocument();
    expect(screen.queryByText(/real-time market/i)).not.toBeInTheDocument();
  });

  it("states the current commercial access boundary without an unsupported conversion form", () => {
    render(<App initialPath="/product" />);

    const productLayers = screen.getByRole("heading", { name: "Different jobs. Clear authority." }).closest("section");
    const operatingModel = screen.getByRole("heading", { name: "A visible chain of responsibility." }).closest("section");
    expect(productLayers?.compareDocumentPosition(operatingModel as Node)).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING
    );
    expect(screen.getByRole("heading", { name: "The commercial boundary stays visible." })).toBeInTheDocument();
    expect(screen.getByText("Browse without sign-in")).toBeInTheDocument();
    expect(screen.getByText("Controlled access")).toBeInTheDocument();
    expect(screen.getByText("Private and not open")).toBeInTheDocument();
    expect(screen.getByText(/Libration does not collect pilot requests on this site\./)).toBeInTheDocument();
    expect(screen.queryByRole("form")).not.toBeInTheDocument();
  });

  it("shows the public investor terminal with one progressive release disclosure", async () => {
    const user = userEvent.setup();
    render(<App initialPath="/investors" />);

    expect(screen.getByRole("heading", { name: /Follow the money/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Tracked managers" })).toBeInTheDocument();
    expect(screen.getByText("Altimeter Capital")).toBeInTheDocument();
    expect(screen.getByText("Pershing Square")).toBeInTheDocument();
    expect(screen.getByText("SEC 13F · Frozen")).toBeInTheDocument();
    expect(screen.getByText(/Values and weights cover only securities disclosed/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Venture capital" })).toHaveAttribute("href", "/investors/venture");
    expect(screen.getByLabelText("Research release summary")).toHaveTextContent("SourceSEC EDGAR");
    expect(screen.getByLabelText("Research release summary")).toHaveTextContent("ObservedSource through");
    expect(screen.getByLabelText("Research release summary")).toHaveTextContent("State7 of 8 managers available");

    const disclosure = screen.getByText("Sources & limits").closest("details");
    expect(disclosure).not.toHaveAttribute("open");
    await user.click(screen.getByText("Sources & limits"));
    expect(disclosure).toHaveAttribute("open");
    expect(disclosure).toHaveTextContent("Release ID");
    expect(disclosure).toHaveTextContent("Research data only");
  });

  it("keeps venture relationships separate from public-market positions", () => {
    const { container } = render(<App initialPath="/investors/venture" />);

    expect(screen.getByRole("heading", { name: /Follow the firms.*Read the relationships/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Tracked venture firms" })).toBeInTheDocument();
    expect(container.querySelector(".venture-hero")).toHaveClass("terminal-hero");
    expect(container.querySelector(".venture-card")).toHaveClass("investor-card");
    expect(screen.getByRole("navigation", { name: "Connected research" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Firms" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByText("Sequoia Capital")).toBeInTheDocument();
    expect(screen.getByText("Founders Fund")).toBeInTheDocument();
    expect(screen.getByLabelText("Venture catalog snapshot")).toHaveTextContent("24");
    expect(screen.getByText(/bounded sample of relationships/i)).toBeInTheDocument();
    expect(screen.queryByText("Portfolio value")).not.toBeInTheDocument();
    expect(screen.queryByText("Ownership")).not.toBeInTheDocument();
  });

  it("shows exact venture sources and preserves undisclosed fields", () => {
    render(<App initialPath="/investors/venture/khosla-ventures" />);

    expect(screen.getByRole("heading", { name: "Khosla Ventures" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Released relationships" })).toBeInTheDocument();
    expect(screen.getByText("OpenAI")).toBeInTheDocument();
    expect(screen.getAllByText("2019").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Undisclosed").length).toBeGreaterThan(0);
    expect(screen.getAllByRole("link", { name: /Official.*source/i }).every((link) => link.getAttribute("href")?.startsWith("https://www.khoslaventures.com/"))).toBe(true);
    expect(screen.getByText(/not capital weighted/i)).toBeInTheDocument();
  });

  it("projects exact venture company IDs without creating ownership claims", () => {
    render(<App initialPath="/investors/venture/companies" />);

    expect(screen.getByRole("heading", { name: /One company.*Every tracked firm/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Company relationship index" })).toBeInTheDocument();
    expect(within(screen.getByRole("navigation", { name: "Venture research views" })).getByRole("link", { name: "Companies" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("heading", { name: "OpenAI" })).toBeInTheDocument();
    expect(screen.getAllByText("3 firms").length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: "OpenAI source from Khosla Ventures" })).toHaveAttribute("href", expect.stringMatching(/^https:\/\/www\.khoslaventures\.com\//));
    expect(screen.getByText(/do not establish ownership, syndication/)).toBeInTheDocument();
  });

  it("shows exact pair overlap without a portfolio-similarity score", () => {
    render(<App initialPath="/investors/venture/overlap" />);

    expect(screen.getByRole("heading", { name: /Overlap.*without a score/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Tracked relationship overlap" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Exact overlap matrix" })).toBeInTheDocument();
    expect(within(screen.getByRole("navigation", { name: "Venture research views" })).getByRole("link", { name: "Overlap" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByLabelText("Selected tracked relationship overlap")).toHaveTextContent("Shared released companies");
    expect(screen.getByText(/not proof of the same financing round/)).toBeInTheDocument();
    expect(screen.queryByText(/similarity score/i)).not.toBeInTheDocument();
  });

  it("keeps one product navigation between investors and the agent", () => {
    const { rerender } = render(<App initialPath="/investors" />);
    expect(screen.getByRole("link", { name: "Research" })).toHaveClass("active");
    expect(screen.getByRole("link", { name: "Research" })).toHaveAttribute("aria-current", "page");

    rerender(<App initialPath="/agent" />);

    expect(screen.getByRole("link", { name: "Libration home" })).toBeInTheDocument();
    const primaryNavigation = screen.getByRole("navigation", { name: "Primary navigation" });
    const researchLink = within(primaryNavigation).getByRole("link", { name: "Research" });
    const intelligenceLink = within(primaryNavigation).getByRole("link", { name: "Intelligence" });
    expect(researchLink).toHaveAttribute("href", "/");
    expect(researchLink.compareDocumentPosition(intelligenceLink) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(within(primaryNavigation).queryByRole("link", { name: "Product" })).not.toBeInTheDocument();
    expect(within(primaryNavigation).getByRole("link", { name: "Coverage" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign in" })).toBeInTheDocument();
  });

  it("explains the product authority without implying autonomous verdicts", () => {
    render(<App initialPath="/product" />);

    expect(screen.getByRole("heading", { name: /One system.*Four research layers/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "A visible chain of responsibility." })).toBeInTheDocument();
    expect(within(screen.getByRole("list", { name: "Libration agent operating model" })).getAllByRole("listitem")).toHaveLength(5);
    expect(screen.getByRole("heading", { name: /The agent explains.*The verifier decides/i })).toBeInTheDocument();
    expect(screen.getByText("Every statement stays untrusted until validated.")).toBeInTheDocument();
    expect(screen.getByText("Model-assisted research answers under the new grounded contract")).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Current and gated product capabilities" })).toBeInTheDocument();
    expect(screen.getByText("One structured extraction step; zero production resolution actions")).toBeInTheDocument();
  });

  it("projects commercial coverage directly from the public release index", () => {
    render(<App initialPath="/coverage" />);

    expect(screen.getByRole("heading", { name: /Know what Libration.*can actually see/i })).toBeInTheDocument();
    expect(screen.getByLabelText("Coverage summary")).toHaveTextContent("12");
    expect(screen.getByRole("heading", { name: "Every declared layer." })).toBeInTheDocument();
    expect(screen.getByText("No approved market release is active.")).toBeInTheDocument();
    expect(screen.getAllByText("Not released").length).toBeGreaterThan(0);
    expect(screen.getByText(/does not substitute model-generated/)).toBeInTheDocument();
  });

  it("shows the deterministic methodology and research boundaries", () => {
    render(<App initialPath="/methodology" />);

    expect(screen.getByRole("heading", { name: "Evidence before explanation." })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Four controlled steps." })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Facts decide.*Narrative explains/i })).toBeInTheDocument();
    expect(screen.getByText("Review required")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "What Libration does not do." })).toBeInTheDocument();
    expect(screen.getByText("Execute trades or manage a portfolio")).toBeInTheDocument();
  });

  it("searches exact released entities from the shared navigation", async () => {
    const user = userEvent.setup();
    render(<App initialPath="/markets" />);

    await user.click(screen.getByRole("button", { name: "Search" }));
    expect(screen.getByRole("dialog", { name: "Search Libration" })).toBeInTheDocument();
    await user.type(screen.getByPlaceholderText(/Company, ticker, manager/), "NVDA");

    expect(screen.getByRole("link", { name: /NVDA Nvidia corporation/ })).toHaveAttribute("href", "/companies/nvda");
    expect(screen.getByText(/Exact identifiers · deterministic text match/)).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog", { name: "Search Libration" })).not.toBeInTheDocument();
  });

  it("filters managers without changing the frozen catalog", async () => {
    const user = userEvent.setup();
    render(<App initialPath="/investors" />);

    await user.type(screen.getByPlaceholderText("Manager or theme"), "Pershing");

    expect(screen.getByText("Pershing Square")).toBeInTheDocument();
    expect(screen.queryByText("Altimeter Capital")).not.toBeInTheDocument();
  });

  it("compares two managers using exact released security IDs", () => {
    render(<App initialPath="/investors/compare" />);

    expect(screen.getByRole("heading", { name: "Compare reported portfolios." })).toBeInTheDocument();
    expect(screen.getByText("Shared positions")).toBeInTheDocument();
    expect(screen.getAllByText("Exact shared ID").length).toBeGreaterThan(0);
    expect(screen.getByText(/not a similarity score, trade observation/)).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /SEC filing/i })).toHaveLength(2);
    const tableRegion = screen.getByRole("region", { name: "Reported portfolio comparison" });
    expect(tableRegion).toHaveAttribute("tabindex", "0");
    expect(tableRegion).toHaveClass("sticky-column-1");
    expect(within(tableRegion).getByText("Scroll →")).toHaveAttribute("aria-hidden", "true");
    const instruction = document.getElementById(tableRegion.getAttribute("aria-describedby") ?? "");
    expect(instruction).toHaveTextContent("Scroll horizontally to inspect every column.");
  });

  it("renders the five public-market investor modules", () => {
    render(<App initialPath="/investors/altimeter-capital" />);

    expect(screen.getByRole("heading", { name: /Altimeter Capital/ })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Holdings" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Changes" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Allocation" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "History" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /SEC filing/i })).toHaveAttribute("href", expect.stringMatching(/^https:\/\/www\.sec\.gov\//));
    expect(screen.getAllByRole("link", { name: /NVDA Nvidia corporation/i })[0]).toHaveAttribute("href", "/companies/nvda");
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
    expect(screen.getByRole("heading", { name: "ETF exposure" })).toBeInTheDocument();
    expect(screen.getByText(/top-ten filed rows only/i)).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /N-PORT/i })).toHaveLength(3);
    expect(screen.getByText("Sum across tracked managers")).toBeInTheDocument();
    expect(screen.getByText(/not market capitalization, total institutional ownership/i)).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /SEC/i }).length).toBeGreaterThan(0);
    const researchSections = screen.getByRole("navigation", { name: "NVDA research sections" });
    expect(within(researchSections).getByRole("link", { name: /Reporting managers.*reported rows/i })).toHaveAttribute("href", "#company-managers-title");
    expect(within(researchSections).getByRole("link", { name: /ETF exposure.*filed top-ten rows/i })).toHaveAttribute("href", "#company-etf-title");
    expect(within(researchSections).getByRole("link", { name: /Policy.*named action/i })).toHaveAttribute("href", "#company-policy-title");
    expect(within(researchSections).queryByRole("link", { name: /Earnings/i })).not.toBeInTheDocument();
    expect(within(researchSections).getByText("Not in current release")).toBeInTheDocument();
    expect(screen.getByText("Verification not released for this company")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Check coverage →" })).toHaveAttribute("href", "/coverage");
    expect(screen.queryByRole("heading", { name: "More forces, when released." })).not.toBeInTheDocument();
    expect(screen.getByLabelText("Research release summary")).toHaveTextContent("SEC 13F · SEC Form N-PORT · SEC Company Facts · Official policy records");
    expect(screen.getByLabelText("Research release summary")).toHaveTextContent("NVDA · 3 released research modules");
  });

  it("connects a company to exact released SEC earnings when covered", () => {
    render(<App initialPath="/companies/aapl" />);

    expect(screen.getByRole("heading", { name: "Reported earnings" })).toBeInTheDocument();
    expect(screen.getByText("$111.18B")).toBeInTheDocument();
    expect(screen.getByText("↑ 16.6% YoY")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /0000320193-26-000013/i })).toHaveAttribute("href", expect.stringMatching(/^https:\/\/www\.sec\.gov\/Archives\//));
    expect(screen.getByRole("link", { name: "All earnings →" })).toHaveAttribute("href", "/intelligence/earnings");
    expect(screen.getByRole("link", { name: "Verify a claim about AAPL" })).toHaveAttribute("href", "/agent?company=0000320193");
    expect(within(screen.getByRole("navigation", { name: "AAPL research sections" })).getByRole("link", { name: /Earnings.*filed result/i })).toHaveAttribute("href", "#company-earnings-title");
  });

  it("connects NVDA only to the exact product-naming export rule", () => {
    render(<App initialPath="/companies/nvda" />);

    expect(screen.getByRole("heading", { name: "Named policy scope" })).toBeInTheDocument();
    expect(screen.getByText("NVIDIA H200 · AMD MI325X")).toBeInTheDocument();
    expect(screen.getByText(/does not establish revenue exposure/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Official source/i })).toHaveAttribute("href", expect.stringMatching(/^https:\/\/www\.federalregister\.gov\//));
    expect(screen.getByRole("link", { name: "All policy →" })).toHaveAttribute("href", "/intelligence/policy");
  });

  it("lists reported company positions derived from the same frozen release", async () => {
    const user = userEvent.setup();
    render(<App initialPath="/companies" />);

    expect(screen.getByRole("heading", { name: "Who reports what." })).toBeInTheDocument();
    expect(screen.getByText("Derived from 13F release")).toBeInTheDocument();
    expect(screen.queryByText("Who owns what.")).not.toBeInTheDocument();
    await user.type(screen.getByPlaceholderText("Ticker, issuer, or theme"), "NVDA");

    expect(screen.getByText("Nvidia corporation")).toBeInTheDocument();
    expect(screen.queryByText("Apple inc")).not.toBeInTheDocument();
  });

  it("renders released ETP exposure while keeping crypto market data fail-closed", () => {
    render(<App initialPath="/markets/crypto" />);

    expect(screen.getByRole("heading", { name: /Crypto data, when it can be traced/i })).toBeInTheDocument();
    expect(screen.getByText("Crypto market data unavailable")).toBeInTheDocument();
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

  it("renders exact filed ETF flows without treating net assets as flows", () => {
    render(<App initialPath="/markets/etfs" />);
    expect(screen.getByRole("heading", { name: "Filed fund flows. Exact inputs." })).toBeInTheDocument();
    expect(screen.getByText("SPY")).toBeInTheDocument();
    expect(screen.getByText("SMH")).toBeInTheDocument();
    expect(screen.getByText("VGT")).toBeInTheDocument();
    expect(screen.getByText("+$3.44B")).toBeInTheDocument();
    expect(screen.getByText("+$1.62B")).toBeInTheDocument();
    expect(screen.getByText(/without substituting changes in net assets/i)).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /N-PORT/i })).toHaveLength(5);
  });

  it("renders a release-bound VGT holdings detail and fund comparison", () => {
    render(<App initialPath="/markets/etfs/vgt" />);

    expect(screen.getByRole("heading", { name: /Vanguard Information Technology ETF/ })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Top filed positions" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "ETF comparison" })).toBeInTheDocument();
    expect(screen.getAllByText("57.4%")).toHaveLength(2);
    expect(screen.getAllByText("17.27%").length).toBeGreaterThan(0);
    expect(screen.getByText(/publishes only the ten largest reviewed rows/i)).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /N-PORT/i })).toHaveLength(10);
    expect(screen.getByRole("region", { name: "VGT top filed positions" })).toHaveClass("sticky-column-2");
  });

  it("renders the bounded BLS macro release with explicit calculations and terms", () => {
    render(<App initialPath="/markets/macro" />);

    expect(screen.getByRole("heading", { name: "Macro signals. Exact scope." })).toBeInTheDocument();
    expect(screen.getByText("3 released observations")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Released observations" })).toBeInTheDocument();
    expect(screen.getByText("3.4%")).toBeInTheDocument();
    expect(screen.getByText("2.5%")).toBeInTheDocument();
    expect(screen.getByText("4.1%")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /BLS data terms/i })).toHaveAttribute("href", expect.stringMatching(/^https:\/\/www\.bls\.gov\//));
    expect(screen.getByText(/BLS.gov cannot vouch/i)).toBeInTheDocument();
    expect(screen.getByText(/not a live macroeconomic feed or forecast/i)).toBeInTheDocument();
  });

  it("keeps intelligence empty until an eligible event release exists", () => {
    const { container } = render(<App initialPath="/intelligence" />);

    expect(screen.getByRole("heading", { name: "What happened. What changed. What is connected." })).toBeInTheDocument();
    expect(container.querySelectorAll(".intelligence-page .data-hero h1 > span")).toHaveLength(3);
    expect(screen.getByText("Earnings + policy available")).toBeInTheDocument();
    expect(screen.getByText("Narrative events unavailable")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /Available/i })).toHaveLength(2);
    expect(screen.getAllByText("Release required")).toHaveLength(2);
    expect(screen.getByRole("navigation", { name: "Connected research" })).toBeInTheDocument();
  });

  it("shows exact public release operations without implying internal health", () => {
    render(<App initialPath="/intelligence/releases" />);

    expect(screen.getByRole("heading", { name: "Every public release. One exact state." })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Catalog state" })).toBeInTheDocument();
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByText("12 declared catalogs")).toBeInTheDocument();
    expect(screen.getByText("Venture capital")).toBeInTheDocument();
    expect(screen.getByText("Crypto market")).toBeInTheDocument();
    expect(screen.getAllByText("Unavailable").length).toBeGreaterThan(0);
    expect(screen.getByText(/not uptime, review throughput, or production telemetry/i)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Source to review, without implicit publish." })).toBeInTheDocument();
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
    expect(screen.getByText("Effective 2026-10-01")).toBeInTheDocument();
    expect(screen.getByText("NVIDIA H200 · AMD MI325X")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /Official source/i })).toHaveLength(3);
    expect(screen.getByRole("link", { name: "NVDA →" })).toHaveAttribute("href", "/companies/nvda");
    expect(screen.queryByRole("link", { name: "AMD →" })).not.toBeInTheDocument();
    expect(screen.queryByText(/stocks.*up|stocks.*down|cut probability/i)).not.toBeInTheDocument();
  });

  it("connects every primary research section through concise released paths", () => {
    const { rerender } = render(<App initialPath="/markets" />);
    expect(within(screen.getByRole("navigation", { name: "Research sections" })).getByRole("link", { name: "Markets" })).toHaveAttribute("aria-current", "page");
    expect(within(screen.getByRole("navigation", { name: "Market sections" })).getByRole("link", { name: "Overview" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("navigation", { name: "Connected research" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Companies Open filed ETF holdings by issuer/i })).toHaveAttribute("href", "/companies");
    expect(screen.getByText("Macro + rates + filed ETF data available")).toBeInTheDocument();
    expect(screen.getByText("Broad market release unavailable")).toBeInTheDocument();
    expect(screen.getByText("Current filed flows + holdings")).toBeInTheDocument();

    rerender(<App initialPath="/investors" />);
    expect(screen.getByRole("link", { name: /Companies Open a security across reporting managers/i })).toHaveAttribute("href", "/companies");

    rerender(<App initialPath="/companies" />);
    expect(screen.getByRole("link", { name: /Intelligence Read released earnings and policy records/i })).toHaveAttribute("href", "/intelligence");

    rerender(<App initialPath="/intelligence" />);
    expect(within(screen.getByRole("navigation", { name: "Intelligence sections" })).getByRole("link", { name: "Overview" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: /Markets Read rates, ETF, and crypto context/i })).toHaveAttribute("href", "/markets");
  });

  it("keeps one primary landmark and one page heading on every public route", () => {
    const routes = [
      "/", "/markets", "/markets/macro", "/markets/rates", "/markets/etfs", "/markets/etfs/vgt", "/markets/crypto",
      "/investors", "/investors/compare", "/investors/altimeter-capital", "/investors/venture", "/investors/venture/companies",
      "/investors/venture/overlap", "/investors/venture/khosla-ventures", "/companies", "/companies/nvda", "/intelligence",
      "/intelligence/earnings", "/intelligence/policy", "/intelligence/releases", "/product", "/coverage", "/methodology", "/agent", "/outside-release"
    ];

    for (const route of routes) {
      const view = render(<App initialPath={route} />);
      expect(view.container.querySelectorAll("main"), route).toHaveLength(1);
      expect(view.container.querySelectorAll("h1"), route).toHaveLength(1);
      expect(screen.getByRole("navigation", { name: "Primary navigation" }), route).toBeInTheDocument();
      view.unmount();
    }
  });
});
