import type { ValidationSummary } from "../types/api";

function checkLabel(code: string): string {
  return code.split("_").map((part, index) => part === "MTF" || part === "ATR"
    ? part : index === 0 ? part.charAt(0) + part.slice(1).toLowerCase() : part.toLowerCase()).join(" ");
}

export function SignalProofAuditPanel({ summary, hidden }: { summary?: ValidationSummary | null; hidden: boolean }) {
  const audit = summary?.proof_audit;
  const heldOut = summary?.walk_forward.held_out_labels;
  const heldOutMatches = summary?.walk_forward.held_out_directional_matches;
  return <article className="panel lower-card proof-audit-card" aria-label="Signal proof audit" hidden={hidden}>
    <span className="eyebrow">SIGNAL QUALIFICATION</span>
    <h2>Why automatic signals are withheld</h2>
    {!audit ? <p>Decision-time proof is unavailable. No publication or performance conclusion can be drawn.</p> : <>
      <p>Recent frozen research decisions, not a replay of broker fills or proof of profitability.</p>
      <dl className="proof-audit-metrics">
        <div><dt>Proof checked</dt><dd>{audit.proof_evaluated_runs} proof-checked runs</dd></div>
        <div><dt>Eligible at review</dt><dd>{audit.eligible_runs} of {audit.proof_evaluated_runs}</dd></div>
        <div><dt>Published, all time</dt><dd>{audit.published_signals} automatically published</dd></div>
      </dl>
      <p className="proof-audit-outcome">{typeof heldOut === "number" && typeof heldOutMatches === "number"
        ? `${heldOutMatches} of ${heldOut} held-out directional matches` : "Held-out direction labels unavailable"} · {summary?.cost_status.replaceAll("_", " ").toLowerCase() ?? "cost status unavailable"}. Direction alone is not net profit.</p>
      <div className="proof-audit-blockers">
        <strong>Most frequent failed checks</strong>
        {audit.failed_checks.length ? <ul>{audit.failed_checks.slice(0, 5).map((check) =>
          <li key={check.code}><span>{checkLabel(check.code)}</span><b>{check.runs} runs</b></li>
        )}</ul> : <p>{audit.proof_evaluated_runs ? "No failed proof checks in this sample." : "No proof-checked runs in this sample yet."}</p>}
      </div>
      <small>Latest proof: {audit.latest_proof_anchor_utc ? new Date(audit.latest_proof_anchor_utc).toLocaleString("en-PH", { timeZone: "Asia/Manila" }) + " PHT" : "unavailable"} · {audit.sampled_runs} most recent runs sampled (limit {audit.sample_limit}).</small>
      <p className="proof-audit-boundary">Not a performance validation. Legacy runs are symbol-scoped, not broker-verified; eligibility is not a filled trade or a win probability.</p>
    </>}
  </article>;
}
