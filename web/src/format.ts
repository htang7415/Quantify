import type { Holding } from "./investors/types";

export function money(value: number | null): string {
  if (value === null) return "Withheld";
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

export function displayName(value: string): string {
  const letters = value.match(/[A-Za-z]/g);
  if (!letters || letters.some((letter) => letter !== letter.toUpperCase())) return value;
  const lower = value.toLowerCase();
  return `${lower.charAt(0).toUpperCase()}${lower.slice(1)}`;
}

export function sentenceCase(value: string): string {
  const normalized = value.replaceAll("_", " ").toLowerCase();
  return `${normalized.charAt(0).toUpperCase()}${normalized.slice(1)}`;
}

export function holdingChangeText(holding: Holding, compact = false): string {
  if (holding.change === "new") return "New";
  if (holding.change === "exited") return "Exited";
  if (holding.change === "unchanged") return compact ? "—" : "Unchanged";
  if (holding.share_delta_pct === null) return sentenceCase(holding.change);
  const sign = holding.share_delta_pct > 0 ? "+" : "";
  return `${sign}${holding.share_delta_pct.toFixed(1)}%`;
}

export function directionalPercent(value: number, digits = 1): string {
  const direction = value > 0 ? "↑" : value < 0 ? "↓" : "—";
  return `${direction} ${Math.abs(value).toFixed(digits)}%`;
}
