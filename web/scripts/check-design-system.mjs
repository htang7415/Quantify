import { readFile } from "node:fs/promises";

const [designSystem, entrypoint] = await Promise.all([
  readFile(new URL("../src/design-system.css", import.meta.url), "utf8"),
  readFile(new URL("../src/main.tsx", import.meta.url), "utf8")
]);

const failures = [];
const routeStylesImport = entrypoint.indexOf('import "./styles.css"');
const designSystemImport = entrypoint.indexOf('import "./design-system.css"');
const absoluteFontSizes = [...designSystem.matchAll(/font-size:\s*(\d+(?:\.\d+)?)px/g)]
  .map((match) => Number(match[1]));

if (routeStylesImport < 0 || designSystemImport <= routeStylesImport) {
  failures.push("The canonical design system must load after route styles.");
}
if (absoluteFontSizes.length === 0 || absoluteFontSizes.some((size) => size < 12)) {
  failures.push("Canonical absolute font sizes must be at least 12px.");
}
if (/text-transform:\s*uppercase/.test(designSystem)) {
  failures.push("The canonical visual system must not force uppercase interface copy.");
}
for (const token of [
  "--q-type-meta",
  "--q-type-control",
  "--q-type-small",
  "--q-type-body",
  "--q-type-card",
  "--q-type-section",
  "--q-type-page",
  "--q-type-display"
]) {
  if (!designSystem.includes(token)) failures.push(`Missing canonical typography token: ${token}`);
}
if (/border-radius:\s*(?:18|24)px/.test(designSystem)) {
  failures.push("Canonical surfaces must use the shared radius scale.");
}
if (!designSystem.includes("font-variant-numeric: tabular-nums")) {
  failures.push("Public product numerics must use stable tabular spacing.");
}
for (const rule of [
  "@media (max-width: 1040px)",
  "@media (max-width: 760px)",
  "@media (max-width: 480px)",
  "@media (prefers-reduced-motion: reduce)"
]) {
  if (!designSystem.includes(rule)) failures.push(`Missing required responsive rule: ${rule}`);
}

if (failures.length) throw new Error(failures.join("\n"));

console.log(`Design system check passed: ${absoluteFontSizes.length} readable font-size declarations and four responsive policies.`);
