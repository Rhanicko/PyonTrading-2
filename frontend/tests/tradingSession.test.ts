import { describe, expect, it } from "vitest";
import { tradingSession } from "../src/services/tradingSession";

describe("indicative trading session clock", () => {
  it.each([
    ["2026-11-16T07:59:59Z", "Tokyo"],
    ["2026-11-16T08:00:00Z", "Tokyo + London"],
    ["2026-11-16T09:00:00Z", "London"],
    ["2026-11-16T13:00:00Z", "London + New York"],
    ["2026-11-16T16:00:00Z", "New York"],
    ["2026-07-13T07:00:00Z", "Tokyo + London"],
    ["2026-07-13T12:00:00Z", "London + New York"],
    ["2026-07-13T15:00:00Z", "New York"],
    ["2026-03-16T12:00:00Z", "London + New York"],
    ["2026-10-26T12:00:00Z", "London + New York"],
    ["2026-11-13T21:59:59Z", "New York"],
    ["2026-11-13T22:00:00Z", "Weekend"],
    ["2026-11-15T21:59:59Z", "Weekend"],
    ["2026-11-15T22:00:00Z", "Sydney"],
    ["2026-07-13T21:30:00Z", "Between sessions"],
    ["2026-07-13T22:00:00Z", "Sydney"],
  ])("labels %s as %s using city-local DST and the New York weekend", (iso, label) => {
    expect(tradingSession(new Date(iso)).label).toBe(label);
  });

  it("distinguishes overlaps and fails safely for an invalid clock", () => {
    expect(tradingSession(new Date("2026-11-16T13:00:00Z")).overlap).toBe(true);
    expect(tradingSession(new Date("2026-11-16T16:00:00Z")).overlap).toBe(false);
    expect(tradingSession(new Date("invalid")).label).toBe("Session unavailable");
  });
});
