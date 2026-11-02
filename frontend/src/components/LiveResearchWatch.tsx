import { pht } from "../services/format";
import type { LiveResearchWatch } from "../types/api";

interface Props {
  watch: LiveResearchWatch | null;
  coordination: {
    totalBots: number;
    liveBots: number;
    blockedBots: number;
    pendingBots: number;
    agreementCount: number | null;
    requiredAgreementCount: number | null;
    ensembleDecision: string | null;
  };
  onSaveReview: () => void;
  savingReview: boolean;
}

function lifecycleLabel(watch: LiveResearchWatch | null) {
  if (!watch) return "CHECKING";
  if (watch.lifecycle === "ACTIVE_RESEARCH_WATCH") return `WATCH ${watch.direction.replace("_CONTEXT", "").replace("_", " ")}`;
  return watch.lifecycle.replaceAll("_", " ");
}

function tone(watch: LiveResearchWatch | null) {
  if (!watch) return "checking";
  if (watch.lifecycle === "ACTIVE_RESEARCH_WATCH") return "active";
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

export function LiveResearchWatch({ watch, coordination, onSaveReview, savingReview }: Props) {
  const score = watch ? `${watch.evidence_score}/100` : "—";
  const sourceSummary = coordination.totalBots
    ? `${coordination.liveBots}/${coordination.totalBots} live`
    : "Checking sources";
  const sourceDetail = coordination.blockedBots
    ? `${coordination.blockedBots} blocked`
    : coordination.pendingBots
      ? `${coordination.pendingBots} pending`
      : "All sources ready";
  const agreementSummary = coordination.agreementCount === null || coordination.requiredAgreementCount === null
    ? "Awaiting rules"
    : `${coordination.agreementCount}/${coordination.requiredAgreementCount} aligned`;
  const decisionSummary = coordination.ensembleDecision?.replaceAll("_", " ") ?? "Checking";
  const reviewTime = pht(watch?.scheduled_review_at_utc ?? watch?.expires_at_utc ?? null);
  const horizonReviewTime = pht(watch?.horizon_review_at_utc ?? null);
  const clearConditions = watch?.gates.filter((gate) => gate.state === "PASS").length ?? 0;
  const totalConditions = watch?.gates.length ?? 0;
  const conditions = watch?.invalidation_conditions ?? ["Required source-backed evidence is still being checked."];
  const summary = watch?.lifecycle === "ACTIVE_RESEARCH_WATCH"
    ? "Automatic monitoring is active and withdraws when a source or rule changes."
    : watch?.lifecycle === "UNAVAILABLE"
      ? "Waiting for the required broker source or completed-candle window."
      : "No directional watch. Review the blocking conditions below.";

  return <section className={`live-research-watch ${tone(watch)}`} aria-live="polite" aria-label="Automatic live research watch">
    <div className="live-watch-heading">
      <div>
        <span className="eyebrow">AUTOMATIC RESEARCH WATCH</span>
        <h2>{lifecycleLabel(watch)}</h2>
      </div>
      <span className="live-watch-pulse">QUOTE 2S · SCAN ≤5S</span>
    </div>
    <p className="live-watch-summary">{watch ? summary : "Checking the current broker quote, completed-candle evidence, and USD-event risk."}</p>

    <div className="live-watch-metrics">
      <article>
        <span>Evidence coverage</span>
        <strong>{score}</strong>
        <small>Coverage, not probability</small>
      </article>
      <article>
        <span>Integrity</span>
        <strong>{watch?.data_quality?.status ?? "CHECKING"}</strong>
        <small>Quote {watch?.data_status ?? "awaiting source"} · {watch?.data_quality?.spread_state ?? "spread pending"}</small>
      </article>
      <article className="live-watch-horizon">
        <span>Research horizon</span>
        <strong>{horizonLabel(watch)}</strong>
        <small>{horizonDetail(watch)} · context review {horizonReviewTime}</small>
      </article>
      <article>
        <span>Fast review</span>
        <strong>{reviewTime}</strong>
        <small>Completed M5 safety check · PHT</small>
      </article>
    </div>

    <section className="live-watch-coordination" aria-label="Research coordination">
      <article>
        <span>Observers</span>
        <strong>{sourceSummary}</strong>
        <small>{sourceDetail}</small>
      </article>
      <article>
        <span>Ensemble</span>
        <strong>{agreementSummary}</strong>
        <small>{decisionSummary}</small>
      </article>
    </section>

    <section className="live-watch-conditions" aria-label="Research conditions">
      <header><span>What changes this</span><strong>{clearConditions}/{totalConditions} clear</strong></header>
      <ul>
        {conditions.slice(0, 3).map((condition) => <li key={condition}>{condition}</li>)}
      </ul>
    </section>

    <div className="live-watch-actions">
      <small>Live status is automatic. Saving creates an optional audit snapshot.</small>
      <button type="button" className="review-snapshot-button" onClick={onSaveReview} disabled={savingReview}>{savingReview ? "Saving…" : "Save review snapshot"}</button>
    </div>
  </section>;
}
