import { gzipSync } from "node:zlib";
import { readdir, readFile } from "node:fs/promises";

const assetDirectory = new URL("../dist/assets/", import.meta.url);
const names = (await readdir(assetDirectory))
  .filter((name) => !name.startsWith("._") && (name.endsWith(".js") || name.endsWith(".css")))
  .sort();
if (names.length === 0) throw new Error("No production JavaScript or CSS assets were found. Run the production build first.");

const assets = await Promise.all(names.map(async (name) => {
  const bytes = await readFile(new URL(name, assetDirectory));
  return { name, raw: bytes.byteLength, gzip: gzipSync(bytes).byteLength };
}));

const javascript = assets.filter((asset) => asset.name.endsWith(".js"));
const styles = assets.filter((asset) => asset.name.endsWith(".css"));
const total = (rows, field) => rows.reduce((sum, row) => sum + row[field], 0);
const failures = [];

if (total(javascript, "gzip") > 150_000) failures.push("JavaScript gzip total exceeds 150 kB.");
if (total(styles, "gzip") > 30_000) failures.push("CSS gzip total exceeds 30 kB.");
if (total(assets, "gzip") > 180_000) failures.push("Combined asset gzip total exceeds 180 kB.");
for (const asset of javascript) {
  if (asset.raw > 300_000) failures.push(`${asset.name} exceeds 300 kB uncompressed.`);
}

for (const asset of assets) console.log(`${asset.name}: ${(asset.raw / 1000).toFixed(1)} kB raw · ${(asset.gzip / 1000).toFixed(1)} kB gzip`);
console.log(`Total: ${(total(assets, "raw") / 1000).toFixed(1)} kB raw · ${(total(assets, "gzip") / 1000).toFixed(1)} kB gzip`);
if (failures.length) throw new Error(failures.join(" "));
