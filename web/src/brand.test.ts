import { describe, expect, it } from "vitest";
import { PRODUCT_NAME, publicBrandText } from "./brand";

describe("public brand presentation", () => {
  it("presents legacy release prose without mutating the source value", () => {
    const released = "Quantify publishes this immutable record.";
    expect(publicBrandText(released)).toBe("Libration publishes this immutable record.");
    expect(released).toBe("Quantify publishes this immutable record.");
    expect(PRODUCT_NAME).toBe("Libration");
  });
});
