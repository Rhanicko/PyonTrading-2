import { pht } from "../services/format";
import { isResearchFresh, isWatchCurrent } from "../services/liveFreshness";
import { confirmationStageLabels, TopDownPanel } from "./TopDownPanel";
import type { LiveResearchWatch, Quote } from "../types/api";

interface Props {
  watch: LiveResearchWatch | null;
  quote: Quote | null;
  quoteFresh: boolean;
  nowMs: number;
  moduleError?: string;
  coordination: {
    totalBots: number;
    liveBots: number;
    blockedBots: number;
    notConfiguredBots: number;
    degradedBots: number;
    agreementCount: number | null;
    requiredAgreementCount: number | null;
    ensembleDecision: string | null;
  };
  onSaveReview: () => void;
  savingReview: boolean;
}

function lifecycleLabel(watch: LiveResearchWatch | null, hasLevels: boolean) {
  if (!watch) return "CHECKING";
  if (watch.lifecycle === "ACTIVE_RESEARCH_WATCH") {
    const direction = watch.direction.replace("_CONTEXT", "").replace("_", " ");
    return hasLevels ? `WATCH ${direction}` : `${direction} SETUP PENDING`;
  }
  return watch.lifecycle.replaceAll("_", " ");
}

function tone(watch: LiveResearchWatch | null, hasLevels: boolean) {
  if (!watch) return "checking";
  if (watch.lifecycle === "ACTIVE_RESEARCH_WATCH") return hasLevels ? "active" : "withheld";
  if (watch.lifecycle === "WITHHELD") return "withheld";
  return "unavailable";
}

function horizonLabel(watch: LiveResearchWatch | null) {
  switch (watch?.research_horizon) {
    case "SHORT_HORIZON_CONTEXT": return "Short-horizon context";
    case "INTRADAY_CONTEXT": return "Intraday context";
    case "MULTI_SESSION_CONTEXT": return "Multi-session context";
    default: return "Not established";
  }
}

function horizonDetail(watch: LiveResearchWatch | null) {
  switch (watch?.horizon_basis) {
    case "M5_M15_H1_H4_COMPLETED_CANDLES_ALIGNED": return "M5 / M15 / H1 / H4 aligned";
    case "M5_M15_H1_COMPLETED_CANDLES_ALIGNED": return "M5 / M15 / H1 aligned";
    case "M5_M15_COMPLETED_CANDLES_ALIGNED": return "M5 / M15 aligned";
    case "NO_ACTIVE_DIRECTIONAL_RESEARCH_WATCH": return "No active directional context";
    default: return "Completed multi-timeframe context is not aligned";
  }
}

export function LiveResearchWatch({ watch, quote, quoteFresh, nowMs, moduleError, coordination, onSaveReview, savingReview }: Props) {
  const active = watch?.lifecycle === "ACTIVE_RESEARCH_WATCH";
  const researchFresh = isResearchFresh(watch?.observed_at_utc, nowMs) && (!watch?.top_down || isResearchFresh(watch.top_down.observed_at_utc, nowMs));
  const current = quoteFresh && researchFresh && !moduleError;
  const sourceIssue = active && (!current || !isWatchCurrent(watch.expires_at_utc, nowMs));
  const score = watch ? `${watch.evidence_score}/100` : "—";
  const sourceSummary = coordination.totalBots
    ? `${coordination.liveBots}/${coordination.totalBots} live`
    : "Checking sources";
  const sourceDetail = [
    coordination.blockedBots ? `${coordination.blockedBots} blocked` : null,
    coordination.notConfiguredBots ? `${coordination.notConfiguredBots} not configured` : null,
    coordination.degradedBots ? `${coordination.degradedBots} source issue` : null,
  ].filter(Boolean).join(" · ") || "All sources ready";
  const agreementSummary = coordination.agreementCount === null || coordination.requiredAgreementCount === null
    ? "Awaiting rules"
    : `${coordination.agreementCount}/${coordination.requiredAgreementCount} aligned`;
  const decisionSummary = coordination.ensembleDecision?.replaceAll("_", " ") ?? "Checking";
  const reviewAt = watch?.scheduled_review_at_utc ?? watch?.expires_at_utc ?? null;
  const reviewMs = Date.parse(reviewAt ?? "");
  const reviewTime = quote?.data_status === "MARKET_CLOSED" ? "Awaiting market"
    : Number.isFinite(reviewMs) && reviewMs > nowMs ? pht(reviewAt)
    : reviewAt ? "Awaiting new M5 bar" : "Awaiting source";
  const clearConditions = watch?.gates.filter((gate) => gate.state === "PASS").length ?? 0;
  const totalConditions = watch?.gates.length ?? 0;
  const conditions = watch?.invalidation_conditions ?? ["Required source-backed evidence is still being checked."];
  const proof = watch?.signal_proof;
  const passedProofChecks = proof?.checks.filter((check) => check.passed).length ?? 0;
  const failedProofChecks = proof?.checks.filter((check) => !check.passed) ?? [];
  const candidate = active ? watch.reference_levels : null;
  const currentSide = watch?.direction === "LONG_CONTEXT" ? quote?.ask : quote?.bid;
  const m5Atr = watch?.analysis_timeframes.find((item) => item.timeframe === "M5")?.indicators?.atr_14;
  const quoteStillNear = currentSide != null && candidate && m5Atr != null && m5Atr > 0
    && Math.abs(currentSide - candidate.entry) <= m5Atr;
  const levels = !sourceIssue && !moduleError && quoteFresh && quote?.data_status === "LIVE" && quote.tick_age_seconds != null
    && quote.tick_age_seconds <= 5 && quoteStillNear ? candidate : null;
  const blockedGate = watch?.gates.find((gate) => gate.state === "BLOCK");
  const pendingStages = watch?.top_down?.stages.filter((stage) => stage.required && stage.state !== "CONFIRMED") ?? [];
  const levelsUnavailableReason = sourceIssue
    ? "The quote or research watch is stale. Wait for fresh source-backed data and a new completed-candle review."
    : active
    ? watch?.reference_levels_reason === "TOP_DOWN_CONFIRMATION_REQUIRED"
      ? pendingStages.length
        ? `Waiting for: ${pendingStages.map((stage) => confirmationStageLabels[stage.stage]).join(", ")}.`
        : "Required top-down confirmation is incomplete."
      : candidate && !levels
      ? "Live quote changed or became stale. Waiting for a fresh source-backed review."
      : watch?.reference_levels_reason === "QUOTE_OUTSIDE_COMPLETED_M5_ATR"
      ? "Price moved beyond the last completed M5 ATR. Waiting for the next review."
      : "A fresh broker quote and completed M5 ATR are required."
    : blockedGate
      ? `${blockedGate.label}: ${blockedGate.reason.replaceAll("_", " ")}`
      : "Independent rules have not produced an active directional watch.";
  const formatLevel = (value: number) => new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 4 }).format(value);
  const summary = sourceIssue
    ? "The last directional watch is no longer current. No levels are shown until the broker source and review recover."
    : active && !levels
    ? `${watch.direction === "SHORT_CONTEXT" ? "Bearish" : "Bullish"} context; entry is not confirmed.`
    : watch?.lifecycle === "ACTIVE_RESEARCH_WATCH"
    ? "Automatic monitoring is active and withdraws when a source or rule changes."
    : watch?.lifecycle === "UNAVAILABLE"
      ? "Waiting for the required broker source or completed-candle window."
      : "No directional watch. Review the blocking conditions below.";

  const quality = watch?.data_quality;
  const qualityIssue = failedProofChecks[0]?.code === "DATA_QUALITY_CLEAR" && quality && (quality.status !== "CLEAR" || quality.candle_gap_count > 0 || quality.spread_state !== "NORMAL");
  const firstBlockerDetail = qualityIssue
    ? `Data quality is ${quality.status}.${quality.candle_gap_count > 0 ? ` Detected ${quality.candle_gap_count} ${quality.candle_gap_count === 1 ? "gap" : "gaps"} in completed M5 candles.` : ""}${quality.spread_state !== "NORMAL" ? ` Spread state: ${quality.spread_state.replaceAll("_", " ")}.` : ""}`
    : failedProofChecks[0]?.detail;
  const firstBlockerSummary = qualityIssue
    ? `Data quality ${quality.status}${quality.candle_gap_count ? ` · ${quality.candle_gap_count} M5 ${quality.candle_gap_count === 1 ? "gap" : "gaps"}` : ""}${quality.spread_state !== "NORMAL" ? ` · spread ${quality.spread_state.replaceAll("_", " ")}` : ""}`
    : firstBlockerDetail;
  const blockerLabel = !current ? "Last review blocker" : qualityIssue ? "Data integrity check" : "Unmet requirement";

  return <section className={`live-research-watch ${sourceIssue ? "unavailable" : tone(watch, !!levels)}`} aria-label="Automatic live research watch">
    <div className="live-watch-heading">
      <div>
        <span className="eyebrow">MARKET SETUP · XAUUSD</span>
        <h2 aria-live="polite">{sourceIssue ? "SOURCE STALE" : lifecycleLabel(watch, !!levels)}</h2>
      </div>
      <span className="live-watch-pulse">{current ? "LIVE RESEARCH" : "VERIFY SOURCE"}</span>
    </div>
    {moduleError && <p className="module-error" role="status">Research refresh issue: {moduleError}. Showing the last verified research state when available.</p>}
    {(!watch || sourceIssue || levels || watch.lifecycle === "UNAVAILABLE") && <p className="live-watch-summary">{watch ? summary : "Checking the current broker quote, completed-candle evidence, and USD-event risk."}</p>}

    <section className={`watch-levels ${levels ? "available" : "empty"}`} aria-label="Research reference levels">
      {levels ? <>
        <div className="watch-levels-heading"><strong>Indicative levels</strong><span>Unvalidated 1R / 2R scenario</span></div>
        <div className="watch-level-grid">
          <div><span>Entry</span><strong>{formatLevel(levels.entry)}</strong></div>
          <div><span>Stop</span><strong>{formatLevel(levels.stop_loss)}</strong></div>
          <div><span>TP1</span><strong>{formatLevel(levels.take_profit_1)}</strong></div>
          <div><span>TP2</span><strong>{formatLevel(levels.take_profit_2)}</strong></div>
        </div>
        <p>Fresh MT5 quote + completed M5 ATR. Recheck at {reviewTime} PHT; these are unvalidated references, not predicted fills or an order.</p>
      </> : <>
        <strong>No entry / stop / targets</strong>
        {(active || sourceIssue || !firstBlockerDetail) && <p>{levelsUnavailableReason}</p>}
        {firstBlockerDetail && <div className="watch-primary-blocker"><span>{blockerLabel}</span><p>{firstBlockerSummary}</p></div>}
      </>}
    </section>

    {levels && firstBlockerDetail && <div className="watch-primary-blocker"><span>{blockerLabel}</span><p>{firstBlockerSummary}</p></div>}
    <div className="live-watch-metrics">
      <article>
        <span>Research horizon</span>
        <strong>{horizonLabel(watch)}</strong>
      </article>
      <article>
        <span>Next review · PHT</span>
        <strong>{reviewTime}</strong>
        {quote?.data_status === "MARKET_CLOSED" && <small>No live M5 close while closed</small>}
      </article>
      <article>
        <span>Data quality</span>
        <strong>{watch?.data_quality?.status ?? "CHECKING"}</strong>
      </article>
      <article>
        <span>USD event risk</span>
        <strong>{watch?.event_risk_state?.replaceAll("_", " ") ?? "CHECKING"}</strong>
      </article>
    </div>

    <details className="watch-review" aria-label="Detailed research review">
      <summary><span>Review evidence</span><strong>{proof ? `${passedProofChecks}/${proof.checks.length} checks` : "Checking"}</strong></summary>
      {proof && <section className={`watch-publication-proof ${proof.publication_state.toLowerCase()}`} aria-label="Signal publication proof">
        <div><strong>{sourceIssue ? "Source changed since review" : proof.publication_state === "ELIGIBLE" ? "Signal publication qualified" : "Signal publication withheld"}</strong><span>{passedProofChecks}/{proof.checks.length} checks passed · performance unvalidated</span></div>
        {failedProofChecks.length > 0 && <><p className="proof-first-blocker">First blocker: {failedProofChecks[0].code}</p><p>{firstBlockerDetail}</p></>}
        {failedProofChecks.length > 1 && <details><summary>{failedProofChecks.length - 1} other blocking checks</summary><ul>{failedProofChecks.slice(1).map((check) => <li key={check.code}><code>{check.code}</code> · {check.detail}</li>)}</ul></details>}
        {proof.checks.every((check) => check.passed) && <small>Qualified research evidence is not a win probability or an order instruction.</small>}
      </section>}
      <TopDownPanel validation={watch?.top_down} current={current} />
      <div className="watch-bot-line">{current ? "Bots" : "Last bot snapshot"}: {sourceSummary} · {agreementSummary} <span>Evidence {score} coverage, not probability · {sourceDetail} · {decisionSummary}</span><span>{horizonDetail(watch)}</span><span>Quote {quote?.data_status?.replaceAll("_", " ") ?? "pending"} · Spread {quoteFresh ? watch?.data_quality?.spread_state ?? "pending" : "not current"}</span></div>
      <section className="live-watch-conditions" aria-label="Research conditions">
        <header><span>What changes this</span><strong>{clearConditions}/{totalConditions} clear</strong></header>
        <ul>
          {conditions.slice(0, 3).map((condition) => <li key={condition}>{condition}</li>)}
        </ul>
      </section>
    </details>

    <div className="live-watch-actions">
      <small>Research only · no order execution</small>
      <button type="button" className="review-snapshot-button" onClick={onSaveReview} disabled={savingReview}>{savingReview ? "Saving…" : "Save review snapshot"}</button>
    </div>
  </section>;
}
