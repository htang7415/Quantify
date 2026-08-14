import { useEffect } from "react";
import { CompanyDetail, CompanyIndex } from "./companies/CompanyPages";
import { CoveragePage, MethodologyPage, ProductPage } from "./CommercialPages";
import { EarningsPage, IntelligencePage, PolicyPage } from "./intelligence/IntelligencePage";
import { CryptoPage, EtfDetailPage, EtfPage, MacroPage, MarketsPage, RatesPage } from "./markets/MarketPages";
import { NotFoundPage } from "./NotFoundPage";
import { OverviewPage } from "./OverviewPage";
import { VerificationPage } from "./VerificationPage";
import { InvestorComparisonPage, InvestorDashboard, InvestorDetail } from "./investors/InvestorPages";
import { ReleaseOperationsPage } from "./releases/ReleaseOperationsPage";
import { VentureCompaniesPage, VentureDashboard, VentureDetail, VentureOverlapPage } from "./venture/VenturePages";
import { applyRouteMetadata } from "./metadata";
import type { VerificationRequest, VerificationResponse } from "./types";

type Verifier = (request: VerificationRequest) => Promise<VerificationResponse>;

export function App({ verifier, initialPath }: { verifier?: Verifier; initialPath?: string }) {
  const path = (initialPath ?? window.location.pathname).replace(/\/$/, "") || "/";
  useEffect(() => {
    applyRouteMetadata(path);
  }, [path]);

  if (path === "/agent" || path === "/verify") return <VerificationPage verifier={verifier} />;
  if (path === "/") return <OverviewPage />;
  if (path === "/product") return <ProductPage />;
  if (path === "/coverage") return <CoveragePage />;
  if (path === "/methodology") return <MethodologyPage />;
  if (path === "/markets") return <MarketsPage />;
  if (path === "/markets/macro") return <MacroPage />;
  if (path === "/markets/rates") return <RatesPage />;
  if (path === "/markets/etfs") return <EtfPage />;
  const etfMatch = path.match(/^\/markets\/etfs\/([a-z0-9-]+)$/);
  if (etfMatch) return <EtfDetailPage slug={etfMatch[1]} />;
  if (path === "/markets/crypto") return <CryptoPage />;
  if (path === "/investors") return <InvestorDashboard />;
  if (path === "/investors/compare") return <InvestorComparisonPage />;
  if (path === "/investors/venture") return <VentureDashboard />;
  if (path === "/investors/venture/companies") return <VentureCompaniesPage />;
  if (path === "/investors/venture/overlap") return <VentureOverlapPage />;
  const ventureMatch = path.match(/^\/investors\/venture\/([a-z0-9-]+)$/);
  if (ventureMatch) return <VentureDetail firmId={ventureMatch[1]} />;
  const investorMatch = path.match(/^\/investors\/([a-z0-9-]+)$/);
  if (investorMatch) return <InvestorDetail slug={investorMatch[1]} />;
  if (path === "/companies") return <CompanyIndex />;
  const companyMatch = path.match(/^\/companies\/([a-z0-9-]+)$/);
  if (companyMatch) return <CompanyDetail slug={companyMatch[1]} />;
  if (path === "/intelligence") return <IntelligencePage />;
  if (path === "/intelligence/earnings") return <EarningsPage />;
  if (path === "/intelligence/policy") return <PolicyPage />;
  if (path === "/intelligence/releases") return <ReleaseOperationsPage />;
  return <NotFoundPage />;
}
