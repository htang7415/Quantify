import type { Holding } from "./investors/types";

export function money(value: number | null): string {
  if (value === null) return "WITHHELD";
  if (value >= 1_000_000_000_000) return `$${(value / 1_000_000_000_000).toFixed(2)}T`;
  if (value >= 1_000_000_000) return `$${(value / 1_000_000_000).toFixed(2)}B`;
  if (value >= 1_000_000) return `$${(value / 1_000_000).toFixed(0)}M`;
  return `$${value.toLocaleString("en-US")}`;
}

export function quarter(date: string): string {
  const [year, month] = date.split("-").map(Number);
  return `Q${Math.ceil(month / 3)} ${year}`;
}

export function readableDate(date: string): string {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC"
  }).format(new Date(`${date}T00:00:00Z`));
}

export function holdingChangeText(holding: Holding, compact = false): string {
  if (holding.change === "new") return "NEW";
  if (holding.change === "exited") return "EXITED";
  if (holding.change === "unchanged") return compact ? "—" : "UNCHANGED";
  if (holding.share_delta_pct === null) return holding.change.toUpperCase();
  const sign = holding.share_delta_pct > 0 ? "+" : "";
  return `${sign}${holding.share_delta_pct.toFixed(1)}%`;
}
