import { describe, expect, it } from "vitest";
import { cryptoExposureCatalog, parseCryptoExposureCatalog } from "./catalog";

describe("crypto exposure catalog contract", () => {
  it("publishes delayed ETP exposure without market data", () => {
    const bitcoin = cryptoExposureCatalog.assets.find((asset) => asset.asset_id === "bitcoin");
    const ethereum = cryptoExposureCatalog.assets.find((asset) => asset.asset_id === "ethereum");

    expect(bitcoin?.reported_etp_value_usd).toBe(2_582_823);
    expect(bitcoin?.positions[0].fund_ticker).toBe("IBIT");
    expect(bitcoin?.market_data_status).toBe("unavailable");
    expect(ethereum?.positions).toEqual([]);
  });

  it("rejects market data smuggled into the exposure release", () => {
    const invalid = {
      ...cryptoExposureCatalog,
      assets: cryptoExposureCatalog.assets.map((asset) => ({ ...asset, market_data_status: "available" }))
    };
    expect(() => parseCryptoExposureCatalog(invalid)).toThrow("cannot publish market data");
  });

  it("rejects non-SEC position sources", () => {
    const invalid = {
      ...cryptoExposureCatalog,
      assets: cryptoExposureCatalog.assets.map((asset) => ({
        ...asset,
        positions: asset.positions.map((position) => ({ ...position, filing_source_url: "https://example.com" }))
      }))
    };
    expect(() => parseCryptoExposureCatalog(invalid)).toThrow("filing source is invalid");
  });

  it("rejects coerced numeric position changes", () => {
    const invalid = {
      ...cryptoExposureCatalog,
      assets: cryptoExposureCatalog.assets.map((asset) => ({
        ...asset,
        positions: asset.positions.map((position) => ({ ...position, share_delta_pct: "0" }))
      }))
    };
    expect(() => parseCryptoExposureCatalog(invalid)).toThrow("share change is invalid");
  });
});
