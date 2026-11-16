import type { SignalHistory, SignalHistoryEntry } from "../types/api";

interface Props {
  history: SignalHistory | null;
  error: string | null;
  nowMs: number;
  desktopPermission: NotificationPermission | "unsupported";
  onEnableDesktopAlerts: () => void;
  hidden: boolean;
}

const formatLevel = (value: number) => new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 4 }).format(value);
const formatDate = (value: string) => new Intl.DateTimeFormat("en-PH", { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Manila" }).format(new Date(value));

function AutomaticSignal({ entry, nowMs }: { entry: SignalHistoryEntry; nowMs: number }) {
  const levels = entry.reference_levels;
  const proof = entry.signal_proof;
  const passed = proof?.checks.filter((check) => check.passed).length ?? 0;
  const expired = !entry.expires_at_utc || Date.parse(entry.expires_at_utc) <= nowMs;
  return <li className="signal-record">
    <div className="signal-record-head">
      <div><strong className={`history-decision ${entry.decision.toLowerCase()}`}>{entry.decision.replace("_", " ")}</strong><span>{entry.symbol} · {entry.broker_server ?? "Broker unknown"}</span></div>
      <span className={`signal-record-state ${expired ? "expired" : "current"}`}>{expired ? "Historical · expired" : "Current until next review"}</span>
    </div>
    <p>{entry.summary}</p>
    {levels && <dl className="signal-record-levels">
      <div><dt>Entry</dt><dd>{formatLevel(levels.entry)}</dd></div>
      <div><dt>Stop</dt><dd>{formatLevel(levels.stop_loss)}</dd></div>
      <div><dt>TP1</dt><dd>{formatLevel(levels.take_profit_1)}</dd></div>
      <div><dt>TP2</dt><dd>{formatLevel(levels.take_profit_2)}</dd></div>
    </dl>}
    <div className="signal-record-proof"><strong>{passed}/{proof?.checks.length ?? 0} source checks</strong><span>Unvalidated performance · not a win probability</span></div>
    <div className={`signal-followup ${entry.forward_outcome?.directional_state.toLowerCase() ?? "pending"}`}>
      <strong>12-bar follow-up: {entry.forward_outcome ? entry.forward_outcome.directional_state.toLowerCase() : "awaiting completed candles"}</strong>
      {entry.forward_outcome && <span>{entry.forward_outcome.directional_change >= 0 ? "+" : ""}{formatLevel(entry.forward_outcome.directional_change)} XAUUSD price units by {formatDate(entry.forward_outcome.outcome_close_utc)}</span>}
      <small>Completed M5 broker closes only. Not a fill or P&amp;L; TP and stop touches are not inferred.</small>
    </div>
    {proof && <details className="signal-proof-details"><summary>View frozen evidence</summary><ul>{proof.checks.map((check) => <li key={check.code}>{check.passed ? "✓" : "×"} {check.detail}</li>)}</ul><small>Rules: {proof.rule_versions.join(", ") || "Unavailable"}</small></details>}
    <footer><span>Recorded {formatDate(entry.provided_at_utc)}</span><span>Quote {levels ? formatDate(levels.quote_observed_at_utc) : "unavailable"}</span><span>Review {entry.expires_at_utc ? formatDate(entry.expires_at_utc) : "unavailable"}</span></footer>
  </li>;
}

export function SignalHistoryPanel({ history, error, nowMs, desktopPermission, onEnableDesktopAlerts, hidden }: Props) {
  const automatic = history?.entries.filter((entry) => entry.signal_kind === "AUTOMATIC") ?? [];
  const manual = history?.entries.filter((entry) => entry.signal_kind !== "AUTOMATIC") ?? [];
  const alertLabel = desktopPermission === "granted" ? "Desktop alerts on" : desktopPermission === "denied" ? "Desktop alerts blocked" : desktopPermission === "unsupported" ? "Desktop alerts unavailable" : "Enable desktop alerts";
  return <article className="panel lower-card signal-history-card" hidden={hidden}>
    <div className="signal-history-heading"><div><span className="eyebrow">SIGNAL HISTORY</span><h2>{automatic.length ? `${automatic.length} published research ${automatic.length === 1 ? "signal" : "signals"}` : "No automatic signals yet"}</h2></div><button type="button" onClick={onEnableDesktopAlerts} disabled={desktopPermission !== "default"}>{alertLabel}</button></div>
    <p>New signals appear only after completed-candle, source, spread, calendar, rule-agreement, and level checks pass. In-app alerts work while this page is open; desktop alerts need permission. Levels are frozen research references, not predicted fills.</p>
    {error && <p className="module-error" role="alert">Signal history refresh issue: {error}. Showing the last saved view.</p>}
    {automatic.length ? <ul className="signal-history-list">{automatic.map((entry) => <AutomaticSignal key={entry.signal_id} entry={entry} nowMs={nowMs} />)}</ul> : <div className="signal-history-empty">The system has not published a source-qualified directional watch. A withheld or unvalidated watch is not inserted as a new signal.</div>}
    {manual.length > 0 && <details className="manual-history"><summary>On-demand research reviews ({manual.length})</summary><ul>{manual.map((entry) => <li key={entry.signal_id}><strong>{entry.decision.replace("_", " ")}</strong><span>{formatDate(entry.provided_at_utc)} · {entry.data_status}</span><p>{entry.summary}</p></li>)}</ul></details>}
  </article>;
}
