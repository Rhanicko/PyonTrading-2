import { describe, expect, it } from "vitest";
import { price } from "../src/services/format";

describe("broker price display", () => {
  it("displays two decimals without changing source precision", () => {
    expect(price(2714.98765)).toBe("2714.99");
    expect(price(null)).toBe("—");
  });
});

