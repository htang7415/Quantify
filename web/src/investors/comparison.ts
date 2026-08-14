import type { Holding, InvestorManager } from "./types";

export type InvestorComparisonRow = {
  securityId: string;
  ticker: string | null;
  cusip: string;
  issuer: string;
  left: Holding | null;
  right: Holding | null;
  shared: boolean;
  weightGapPp: number;
};

export type InvestorComparison = {
  left: InvestorManager;
  right: InvestorManager;
  sharedPositions: number;
  leftOnlyPositions: number;
  rightOnlyPositions: number;
  rows: InvestorComparisonRow[];
};

export function compareInvestors(left: InvestorManager, right: InvestorManager): InvestorComparison {
  if (left.status !== "available" || right.status !== "available") {
    throw new Error("Investor comparison requires two available reporting managers.");
  }
  if (left.slug === right.slug) throw new Error("Investor comparison requires two different reporting managers.");
  if (left.latest_filing.report_period !== right.latest_filing.report_period) {
    throw new Error("Investor comparison requires reporting managers from the same period.");
  }

  const leftRows = new Map(left.holdings.map((holding) => [holding.security_id, holding]));
  const rightRows = new Map(right.holdings.map((holding) => [holding.security_id, holding]));
  const securityIds = new Set([...leftRows.keys(), ...rightRows.keys()]);
  const rows = [...securityIds].map((securityId): InvestorComparisonRow => {
    const leftHolding = leftRows.get(securityId) ?? null;
    const rightHolding = rightRows.get(securityId) ?? null;
    const identity = leftHolding ?? rightHolding;
    if (!identity) throw new Error("Investor comparison contains an empty security identity.");
    return {
      securityId,
      ticker: identity.ticker,
      cusip: identity.cusip,
      issuer: identity.issuer,
      left: leftHolding,
      right: rightHolding,
      shared: leftHolding !== null && rightHolding !== null,
      weightGapPp: (leftHolding?.weight_pct ?? 0) - (rightHolding?.weight_pct ?? 0)
    };
  }).sort((leftRow, rightRow) => {
    if (leftRow.shared !== rightRow.shared) return leftRow.shared ? -1 : 1;
    return Math.max(rightRow.left?.weight_pct ?? 0, rightRow.right?.weight_pct ?? 0) - Math.max(leftRow.left?.weight_pct ?? 0, leftRow.right?.weight_pct ?? 0);
  });

  return {
    left,
    right,
    sharedPositions: rows.filter((row) => row.shared).length,
    leftOnlyPositions: rows.filter((row) => row.left && !row.right).length,
    rightOnlyPositions: rows.filter((row) => row.right && !row.left).length,
    rows
  };
}
