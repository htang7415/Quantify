import { describe, expect, it } from "vitest";
import { investorCatalog } from "../investors/catalog";
import { parsePublicReleaseIndex, publicReleaseIndex, releaseFor } from "./catalog";

describe("public release index contract", () => {
  it("binds the available investor entry to the loaded frozen catalog", () => {
    const investors = releaseFor("investors");
    expect(investors.status).toBe("available");
    expect(investors.release_id).toBe(investorCatalog.release_id);
    expect(investors.manifest_hash).toBe(investorCatalog.manifest_hash);
  });

  it("keeps not-yet-approved market catalogs explicitly unavailable", () => {
    for (const catalog of ["markets", "etf_flows", "crypto", "events"] as const) {
      expect(releaseFor(catalog).status).toBe("unavailable");
      expect(releaseFor(catalog).release_id).toBeNull();
    }
  });

  it("publishes typed policy actions independently from narrative events", () => {
    expect(releaseFor("policy").status).toBe("available");
    expect(releaseFor("policy").release_id).toMatch(/^policy-events-/);
    expect(releaseFor("events").status).toBe("unavailable");
  });

  it("publishes reported earnings independently from narrative events", () => {
    expect(releaseFor("earnings").status).toBe("available");
    expect(releaseFor("earnings").release_id).toMatch(/^earnings-/);
    expect(releaseFor("events").status).toBe("unavailable");
  });

  it("publishes BLS macro independently from the broader market release", () => {
    expect(releaseFor("markets").status).toBe("unavailable");
    expect(releaseFor("macro").status).toBe("available");
    expect(releaseFor("macro").release_id).toMatch(/^bls-macro-/);
  });

  it("publishes official Treasury rates independently from the broader market release", () => {
    expect(releaseFor("markets").status).toBe("unavailable");
    expect(releaseFor("rates").status).toBe("available");
    expect(releaseFor("rates").manifest_hash).toMatch(/^[a-f0-9]{64}$/);
  });

  it("publishes crypto-linked ETP exposure independently from crypto market data", () => {
    expect(releaseFor("crypto").status).toBe("unavailable");
    expect(releaseFor("crypto_exposure").status).toBe("available");
    expect(releaseFor("crypto_exposure").release_id).toMatch(/^crypto-exposure-/);
  });

  it("rejects an available release without replay identity", () => {
    const invalid = {
      ...publicReleaseIndex,
      releases: publicReleaseIndex.releases.map((release) =>
        release.catalog === "crypto" ? { ...release, status: "available", release_id: null } : release
      )
    };
    expect(() => parsePublicReleaseIndex(invalid)).toThrow("require identity");
  });
});
