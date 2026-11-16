import { pht } from "../services/format";
import type { TopDownValidation } from "../types/api";

export const confirmationStageLabels = { BIAS: "Broader bias", INTRADAY: "Intraday direction", SETUP: "Setup", TRIGGER: "Close trigger", TIMING: "Optional timing", RISK: "Risk checks" };

export function TopDownPanel({ validation, current = true }: { validation?: TopDownValidation | null; current?: boolean }) {
  if (!validation) return null;
  const required = validation.stages.filter((stage) => stage.required);
  return <details className="top-down-panel">
    <summary>Top-down confirmation <strong>{required.filter((stage) => stage.state === "CONFIRMED").length}/{required.length}</strong></summary>
    {!current && <p role="status">Last review only · source/research is not current. Waiting for revalidation.</p>}
    <p aria-live="polite">{validation.state.replaceAll("_", " ")} · reviewed {pht(validation.observed_at_utc)} PHT. M1 cannot replace higher-timeframe confirmation.</p>
    <ol>{validation.stages.map((stage) => <li key={stage.stage}>
      <div><strong>{confirmationStageLabels[stage.stage]}</strong><span>{stage.timeframes.join(" / ") || "Source and risk gates"}</span><b className={stage.state.toLowerCase()}>{stage.state.toLowerCase()}</b></div>
      {Object.entries(stage.evidence_timestamps).map(([frame, timestamp]) => <small key={frame}>{frame} close {pht(timestamp)} PHT </small>)}
      {stage.invalidation_price != null && <small>Structure invalidation: {stage.invalidation_price.toFixed(2)}</small>}
      {stage.state !== "CONFIRMED" && <p>{stage.reason_codes.filter((code) => code !== "COMPLETED_CANDLES_ONLY").join(" · ").replaceAll("_", " ").toLowerCase()}</p>}
    </li>)}</ol>
  </details>;
}
