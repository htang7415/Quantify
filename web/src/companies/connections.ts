import { earningsForTicker } from "../earnings/catalog";
import { etfExposuresForTicker } from "../etfs/holdingsCatalog";
import { policyEventsForTicker } from "../policy/catalog";
import type { CompanyOwnership } from "./ownership";

export type CompanyConnectionSummary = {
  reportingManagers: number;
  etfRows: number;
  earningsAvailable: boolean;
  policyEvents: number;
};

export function companyConnections(company: CompanyOwnership): CompanyConnectionSummary {
  return {
    reportingManagers: company.reporting_manager_count,
    etfRows: etfExposuresForTicker(company.ticker).length,
    earningsAvailable: earningsForTicker(company.ticker) !== null,
    policyEvents: policyEventsForTicker(company.ticker).length
  };
}
