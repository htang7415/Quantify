import { CompanyDetail, CompanyIndex } from "./companies/CompanyPages";
import { EarningsPage, IntelligencePage, PolicyPage } from "./intelligence/IntelligencePage";
import { CryptoPage, MacroPage, MarketsPage, RatesPage } from "./markets/MarketPages";
import { NotFoundPage } from "./NotFoundPage";
import { OverviewPage } from "./OverviewPage";
import { VerificationPage } from "./VerificationPage";
import { InvestorDashboard, InvestorDetail } from "./investors/InvestorPages";
import type { VerificationRequest, VerificationResponse } from "./types";

type Verifier = (request: VerificationRequest) => Promise<VerificationResponse>;

export function App({ verifier, initialPath }: { verifier?: Verifier; initialPath?: string }) {
  const path = (initialPath ?? window.location.pathname).replace(/\/$/, "") || "/";
  if (path === "/agent" || path === "/verify") return <VerificationPage verifier={verifier} />;
  if (path === "/") return <OverviewPage />;
  if (path === "/markets") return <MarketsPage />;
  if (path === "/markets/macro") return <MacroPage />;
  if (path === "/markets/rates") return <RatesPage />;
  if (path === "/markets/crypto") return <CryptoPage />;
  if (path === "/investors") return <InvestorDashboard />;
  const investorMatch = path.match(/^\/investors\/([a-z0-9-]+)$/);
  if (investorMatch) return <InvestorDetail slug={investorMatch[1]} />;
  if (path === "/companies") return <CompanyIndex />;
  const companyMatch = path.match(/^\/companies\/([a-z0-9-]+)$/);
  if (companyMatch) return <CompanyDetail slug={companyMatch[1]} />;
  if (path === "/intelligence") return <IntelligencePage />;
  if (path === "/intelligence/earnings") return <EarningsPage />;
  if (path === "/intelligence/policy") return <PolicyPage />;
  return <NotFoundPage />;
}
