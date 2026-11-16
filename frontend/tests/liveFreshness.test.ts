import { describe, expect, it } from "vitest";
import { isQuoteFresh, isResearchFresh, isWatchCurrent } from "../src/services/liveFreshness";

describe("live research freshness", () => {
  const now = Date.parse("2026-11-13T00:00:10Z");

  it("withdraws a frozen LIVE quote after updates stop", () => {
    expect(isQuoteFresh({ data_status: "LIVE", observed_at_utc: "2026-11-13T00:00:09Z", tick_age_seconds: 0.5 }, now)).toBe(true);
    expect(isQuoteFresh({ data_status: "LIVE", observed_at_utc: "2026-11-13T00:00:00Z", tick_age_seconds: 0.5 }, now)).toBe(false);
  });

  it("rejects delayed, old-tick and invalid quotes", () => {
    expect(isQuoteFresh({ data_status: "DELAYED", observed_at_utc: "2026-11-13T00:00:09Z", tick_age_seconds: 0.5 }, now)).toBe(false);
    expect(isQuoteFresh({ data_status: "LIVE", observed_at_utc: "2026-11-13T00:00:09Z", tick_age_seconds: 8 }, now)).toBe(false);
    expect(isQuoteFresh({ data_status: "LIVE", observed_at_utc: "bad", tick_age_seconds: 0.5 }, now)).toBe(false);
  });

  it("expires an old directional watch even if its last payload said active", () => {
    expect(isWatchCurrent("2026-11-13T00:00:11Z", now)).toBe(true);
    expect(isWatchCurrent("2026-11-13T00:00:09Z", now)).toBe(false);
  });

  it("does not call a frozen research snapshot current just because quotes still arrive", () => {
    expect(isResearchFresh("2026-11-13T00:00:09Z", now)).toBe(true);
    expect(isResearchFresh("2026-11-12T23:59:54Z", now)).toBe(false);
    expect(isResearchFresh("2026-11-13T00:00:13Z", now)).toBe(false);
    expect(isResearchFresh("bad", now)).toBe(false);
  });
});
