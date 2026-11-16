import { useEffect, useState } from "react";
import { api } from "../services/api";
import { pht } from "../services/format";
import type { MarketScan } from "../types/api";

const number = (value: number | null | undefined, suffix = "") => value == null ? "Unavailable" : `${value.toFixed(2)}${suffix}`;

export function MarketScannerPanel() {
  const [scan, setScan] = useState<MarketScan | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refresh, setRefresh] = useState(0);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let disposed = false;
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    api.marketScan(controller.signal).then((result) => { if (!disposed) setScan(result); }).catch((cause) => {
      if (!disposed) { setScan(null); setError(cause instanceof Error ? cause.message : "Scan unavailable"); }
    }).finally(() => { if (!disposed) setLoading(false); });
    const timer = window.setTimeout(() => setRefresh((value) => value + 1), 60_000);
    return () => { disposed = true; controller.abort(); window.clearTimeout(timer); };
  }, [refresh]);

  return <section className="market-scanner panel" aria-label="Comparative market scanner">
    <header><div><span className="eyebrow">BROADER MARKET CONTEXT</span><h2>Comparative scanner</h2></div><button type="button" onClick={() => setRefresh((value) => value + 1)} disabled={loading}>{loading ? "Scanning…" : "Refresh scan"}</button></header>
    <p>Context ranking compares observed H1 movement with volatility. It does not qualify a trading signal. Visible broker instruments only; refreshes every minute while this view is open.</p>
    {loading && <p role="status">Reading broker quotes and completed H1 windows…</p>}
    {error && <p role="alert" className="module-error">{error}</p>}
    {scan && <>
      <small>MT5 · {scan.data_status.replaceAll("_", " ")} · observed {pht(scan.observed_at_utc)} PHT</small>
      {scan.instruments.length ? <div className="walk-forward-table-wrap"><table className="walk-forward-table">
        <caption>Comparative context · no signal authority</caption>
        <thead><tr><th scope="col">Instrument</th><th scope="col">Context rank</th><th scope="col">20-bar return</th><th scope="col">Spread / ATR</th><th scope="col">Regime / source</th></tr></thead>
        <tbody>{scan.instruments.map((item) => <tr key={item.symbol}>
          <th scope="row">{item.symbol}</th><td>{item.comparison_rank ?? "Unranked"}</td><td>{number(item.return_20_bars_percent, "%")}</td><td>{number(item.spread_atr_ratio == null ? null : item.spread_atr_ratio * 100, "%")}</td>
          <td>{item.data_status === "LIVE" ? item.market_regime.replaceAll("_", " ") : item.data_status.replaceAll("_", " ")}<small>{item.candle_close_utc ? `H1 close ${pht(item.candle_close_utc)} PHT` : "No current completed window"}</small></td>
        </tr>)}</tbody>
      </table></div> : <p>No visible broker FX instruments with currency metadata are available. Check MT5 Market Watch.</p>}
      {scan.currency_strength.length > 0 && <details><summary>Relative currency movement</summary><p>Mean signed return of the scanned pairs; the result depends on this sample.</p><div className="currency-strength-list">{scan.currency_strength.map((item) => <span key={item.currency}><strong>{item.currency}</strong> {number(item.return_score_percent, "%")} <small>({item.pair_count} pairs)</small></span>)}</div></details>}
      <details><summary>Correlation and shared exposure</summary>{scan.correlations.length ? <ul>{scan.correlations.map((item) => <li key={`${item.first_symbol}-${item.second_symbol}`}>{item.first_symbol} / {item.second_symbol}: {number(item.return_correlation)} · {item.shared_return_bars} matched H1 returns{item.overlapping_exposure ? ` · shared exposure ${item.shared_currencies.join(" / ")}` : ""}</li>)}</ul> : <p>At least 20 matching uninterrupted H1 return timestamps are required. No correlation is estimated from unmatched data.</p>}</details>
    </>}
  </section>;
}
