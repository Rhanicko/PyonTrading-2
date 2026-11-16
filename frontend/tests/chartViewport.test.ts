import { describe, expect, it } from "vitest";
import { defaultViewportRange, visiblePriceRange } from "../src/services/chartViewport";

describe("visible chart price range", () => {
  const candles = Array.from({ length: 120 }, (_, index) => ({
    high: index < 30 ? 4100 : 3890,
    low: index < 30 ? 4000 : 3870,
    close: index < 30 ? 4050 : 3880,
  }));

  it("uses visible candles rather than distant history for the default view", () => {
    const range = visiblePriceRange(candles, defaultViewportRange(candles.length));
    expect(range).not.toBeNull();
    expect(range!.to).toBeLessThan(3910);
    expect(range!.from).toBeGreaterThan(3850);
  });

  it("uses the visible historical section when the user pans back", () => {
    const range = visiblePriceRange(candles, { from: 0, to: 20 });
    expect(range!.to).toBeGreaterThan(4100);
    expect(range!.from).toBeLessThan(4000);
  });
});
