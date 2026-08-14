import { afterEach, describe, expect, it, vi } from "vitest";
import { applyRouteMetadata, metadataForPath } from "./metadata";

describe("route metadata", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    document.head.querySelector('link[rel="canonical"]')?.remove();
  });

  it("defines distinct metadata for durable commercial routes", () => {
    expect(metadataForPath("/")).toMatchObject({
      title: "Quantify — AI research agent for company evidence",
      canonicalPath: "/",
      indexable: true
    });
    expect(metadataForPath("/coverage/")).toMatchObject({
      title: "Current coverage — Quantify",
      canonicalPath: "/coverage",
      indexable: true
    });
  });

  it("canonicalizes the legacy verification path to the agent", () => {
    expect(metadataForPath("/verify").canonicalPath).toBe("/agent");
  });

  it("keeps unknown routes out of search", () => {
    expect(metadataForPath("/outside-release")).toMatchObject({
      title: "Page not found — Quantify",
      indexable: false
    });
    expect(metadataForPath("/markets/outside-release").indexable).toBe(false);
    expect(metadataForPath("/companies/nvda").indexable).toBe(true);
  });

  it("applies canonical and sharing metadata while previews remain noindex", () => {
    vi.stubEnv("VITE_QUANTIFY_PUBLIC_ORIGIN", "https://research.example.test");
    applyRouteMetadata("/methodology");

    expect(document.title).toBe("Methodology — Quantify");
    expect(document.head.querySelector('meta[name="description"]')).toHaveAttribute(
      "content",
      expect.stringContaining("deterministic validation")
    );
    expect(document.head.querySelector('meta[name="robots"]')).toHaveAttribute("content", "noindex,nofollow");
    expect(document.head.querySelector('meta[property="og:url"]')).toHaveAttribute(
      "content",
      "https://research.example.test/methodology"
    );
    expect(document.head.querySelector('link[rel="canonical"]')).toHaveAttribute(
      "href",
      "https://research.example.test/methodology"
    );
  });
});
