import { useState } from "react";
import { api } from "../services/api";
import type { WalkForwardMetrics, WalkForwardValidation } from "../types/api";

const pointFormat = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2, signDisplay: "exceptZero" });

function observedPoints(metrics: WalkForwardMetrics): string {
  return metrics.net_points === null ? "Unavailable" : pointFormat.format(metrics.net_points).replace("-", "−");
}

export function WalkForwardPanel({ hidden }: { hidden: boolean }) {
  const [result, setResult] = useState<WalkForwardValidation | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    setRunning(true);
    setError(null);
    setResult(null);
    try {
      setResult(await api.validateArchive());
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "ARCHIVE_VALIDATION_FAILED");
    } finally {
      setRunning(false);
    }
  };

  return <article className="panel lower-card walk-forward-card" aria-label="Full archive hold-out validation" hidden={hidden}>
    <span className="eyebrow">OUT-OF-SAMPLE RESEARCH</span>
    <div className="backtest-heading"><h2>Full archive hold-out validation</h2><button type="button" className="analyze-button" onClick={() => void run()} disabled={running}>{running ? "Validating…" : "Validate full archive"}</button></div>
    <p>Chronological 60/20/20 split with three expanding walk-forward checks before the final hold-out. Holding period is selected on training bars only. Trials within each strategy do not overlap.</p>
    {running && <p role="status">Reading completed broker candles and validating strategies…</p>}
    {error && <p className="module-error" role="alert">Validation failed: {error}</p>}
    {result && <>
      {result.cache_hit && <p>Reused unchanged archive result. The quote status was checked again.</p>}
      <p>{result.completed_candles.toLocaleString("en-US")} completed M5 bars · {result.broker_server ?? "broker identity unavailable"} · archive status {result.data_status.replaceAll("_", " ")}.</p>
      {result.results.length ? <div className="walk-forward-table-wrap"><table className="walk-forward-table">
        <caption>Recorded-spread-adjusted points and completed trials; not net profit</caption>
        <thead><tr><th scope="col">Strategy</th><th scope="col">Validation</th><th scope="col">Held-out</th><th scope="col">Review</th></tr></thead>
        <tbody>{result.results.map((item) => <tr key={item.strategy_id}>
          <th scope="row">{item.strategy_id.replaceAll("_", " ").toLowerCase()}</th>
          <td>{observedPoints(item.validation)} <small>{item.validation.trials} trials</small></td>
          <td>{observedPoints(item.held_out)} <small>{item.held_out.trials} trials</small></td>
          <td>{item.state.replaceAll("_", " ").toLowerCase()}</td>
        </tr>)}</tbody>
      </table></div> : <p>No comparable strategy trials are available for this exact broker archive. {result.reason_codes.join(" / ").replaceAll("_", " ")}.</p>}
      {result.results.some((item) => item.walk_forward?.length) && <details className="validation-details"><summary>Walk-forward stability and held-out diagnostics</summary>
        <p>All values use recorded spread only. Drawdown is a cumulative point series for one strategy; it is not account-equity drawdown. Commission, slippage, swap and fills remain unavailable.</p>
        <div className="walk-forward-table-wrap"><table className="walk-forward-table"><caption>Strategy diagnostics · no model promotion</caption>
          <thead><tr><th scope="col">Strategy</th><th scope="col">Positive validation folds</th><th scope="col">Held-out expectancy</th><th scope="col">Profit factor</th><th scope="col">Drawdown points</th></tr></thead>
          <tbody>{result.results.map((item) => <tr key={item.strategy_id}><th scope="row">{item.strategy_id.replaceAll("_", " ").toLowerCase()}</th>
            <td>{item.walk_forward?.filter((fold) => fold.validation.net_points != null && fold.validation.net_points > 0).length ?? 0}/{item.walk_forward?.length ?? 0}</td>
            <td>{item.held_out.spread_adjusted_expectancy_points == null ? "Unavailable" : pointFormat.format(item.held_out.spread_adjusted_expectancy_points)}</td>
            <td>{item.held_out.spread_adjusted_profit_factor?.toFixed(2) ?? "Unavailable"}</td>
            <td>{item.held_out.spread_adjusted_max_drawdown_points == null ? "Unavailable" : pointFormat.format(item.held_out.spread_adjusted_max_drawdown_points)}</td>
          </tr>)}</tbody></table></div>
      </details>}
      <small>{result.limitation}</small>
    </>}
  </article>;
}
