import { describe, expect, it } from "vitest";
import { latestAutomaticSignal, newSignalAlert } from "../src/services/signalNotifications";
import type { SignalHistoryEntry } from "../src/types/api";

const base: SignalHistoryEntry = {
  signal_id: "auto-2", provided_at_utc: "2026-11-13T01:00:00Z", symbol: "XAUUSD",
  source: "PYONTRADING2_LIVE_RESEARCH_WATCH", source_timestamp_utc: "2026-11-13T00:55:00Z",
  data_status: "LIVE", analysis_mode: "AUTOMATIC_RESEARCH_WATCH_V1", decision: "WATCH_LONG",
  market_context: "UPWARD_STRUCTURE", summary: "Source-backed watch", event_risk_state: "NO_EVENT_IN_EXPORT",
  paper_status: "NOT_CREATED", input_fingerprint: "frozen", reason_codes: [],
  signal_kind: "AUTOMATIC", broker_server: "Demo-Server", feature_set_version: "research-v1",
  expires_at_utc: "2026-11-13T01:05:00Z",
  reference_levels: { entry: 4200.3, stop_loss: 4198.3, take_profit_1: 4202.3, take_profit_2: 4204.3,
    source_candle_close_utc: "2026-11-13T00:55:00Z", quote_observed_at_utc: "2026-11-13T01:00:00Z", basis: "M5_ATR14_1R_2R_UNVALIDATED" },
  signal_proof: { publication_state: "ELIGIBLE", performance_state: "UNVALIDATED", checks: [{ code: "FRESH_BROKER_QUOTE", passed: true, detail: "Live quote" }], rule_versions: ["structure-v1"], reason_codes: ["PERFORMANCE_UNVALIDATED"] },
};

describe("automatic signal alerts", () => {
  it("uses only the active broker's latest automatic signal as the notification cursor", () => {
    const manual = { ...base, signal_id: "manual-newer", signal_kind: "ON_DEMAND" as const };
    const otherBroker = { ...base, signal_id: "other", broker_server: "Other-Demo" };
    expect(latestAutomaticSignal([manual, otherBroker, base], "Demo-Server", "XAUUSD")?.signal_id).toBe("auto-2");
  });

  it("notifies only a newly published eligible signal while it is still valid", () => {
    const now = Date.parse("2026-11-13T01:01:00Z");
    expect(newSignalAlert([base], null, "Demo-Server", "XAUUSD", now, true)).toBeNull();
    expect(newSignalAlert([base], "", "Demo-Server", "XAUUSD", now, true)?.signal_id).toBe("auto-2");
    expect(newSignalAlert([base], "auto-1", "Demo-Server", "XAUUSD", now, true)?.signal_id).toBe("auto-2");
    expect(newSignalAlert([base], "auto-1", "Demo-Server", "XAUUSD", now, false)).toBeNull();
    expect(newSignalAlert([base], "auto-2", "Demo-Server", "XAUUSD", now, true)).toBeNull();
    expect(newSignalAlert([base], "auto-1", "Demo-Server", "XAUUSD", Date.parse("2026-11-13T01:06:00Z"), true)).toBeNull();
    expect(newSignalAlert([{ ...base, signal_proof: { ...base.signal_proof!, publication_state: "WITHHELD" } }], "auto-1", "Demo-Server", "XAUUSD", now, true)).toBeNull();
  });
});
