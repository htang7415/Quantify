export type VerificationCompany = {
  cik: string;
  name: string;
  ticker: string;
};

export const verificationCompanies: readonly VerificationCompany[] = [
  { cik: "0000789019", name: "Microsoft", ticker: "MSFT" },
  { cik: "0000320193", name: "Apple", ticker: "AAPL" }
] as const;

export function verificationCompanyForCik(cik: string | null | undefined): VerificationCompany | null {
  if (!cik) return null;
  return verificationCompanies.find((company) => company.cik === cik) ?? null;
}

export function verificationCompanyForTicker(ticker: string): VerificationCompany | null {
  return verificationCompanies.find((company) => company.ticker === ticker) ?? null;
}
