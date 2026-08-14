import { describe, expect, it } from "vitest";
import { directionalPercent } from "./format";

describe("directional percent formatting", () => {
  it("derives direction from the signed value", () => {
    expect(directionalPercent(16.6)).toBe("↑ 16.6%");
    expect(directionalPercent(-4.25, 2)).toBe("↓ 4.25%");
    expect(directionalPercent(0)).toBe("— 0.0%");
  });
});
