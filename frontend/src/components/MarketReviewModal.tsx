import type { MarketAnalysis, TimeframeEvidence } from "../types/api";

interface Props {
  analysis: MarketAnalysis;
  onClose: () => void;
  onMinimize: () => void;
}

function reading(value: number | null | undefined, digits = 2) {
  return value === null || value === undefined ? "Unavailable" : value.toFixed(digits);
}

function structureLabel(value: TimeframeEvidence["structure"]) {
  return value.replaceAll("_", " ");
}

function indicatorTone(structure: TimeframeEvidence["structure"] | undefined) {
  if (structure === "UPWARD_STRUCTURE") return "positive";
  if (structure === "DOWNWARD_STRUCTURE") return "negative";
  return "neutral";
}

function gateTone(state: MarketAnalysis["gates"][number]["state"]) {
  return state === "PASS" ? "gate-pass" : state === "WATCH" ? "gate-watch" : "gate-block";
}

export function MarketReviewModal({ analysis, onClose, onMinimize }: Props) {
  const primary = analysis.analysis_timeframes.find((evidence) => evidence.timeframe === "M5");
  const indicators = primary?.indicators;
  const decisionClass = analysis.decision.toLowerCase();

  return <div className="analysis-modal-backdrop" role="presentation" onMouseDown={(event) => {
    if (event.target === event.currentTarget) onClose();
  }}>
    <section className={`analysis-modal ${decisionClass}`} role="dialog" aria-modal="true" aria-labelledby="market-review-title">
      <header className="analysis-modal-header">
        <div>
          <span className="eyebrow">FRESH CROSS-BOT REVIEW</span>
          <h2 id="market-review-title">{analysis.decision.replace("_", " ")}</h2>
          <p>{analysis.summary}</p>
        </div>
        <div className="analysis-modal-actions">
          <button type="button" className="modal-action" onClick={onMinimize}>Minimize</button>
          <button type="button" className="modal-action close" onClick={onClose}>Close</button>
        </div>
      </header>

      <div className="analysis-modal-meta">
        <span>{analysis.data_status}</span>
        <span>MT5 completed candles</span>
        <span>No order execution</span>
      </div>

      <section className="modal-section" aria-labelledby="review-gates-title">
        <div className="modal-section-heading"><h3 id="review-gates-title">Evidence gates</h3><small>Current source checks</small></div>
        <ul className="modal-gates">
          {analysis.gates.map((gate) => <li key={gate.label}>
            <span className={gateTone(gate.state)}>{gate.state}</span>
            <div><strong>{gate.label}</strong><small>{gate.reason}</small></div>
          </li>)}
        </ul>
      </section>

      <section className="modal-section" aria-labelledby="integrity-title">
        <div className="modal-section-heading"><h3 id="integrity-title">Integrity & regime</h3><small>Observable source conditions</small></div>
        <div className="indicator-grid compact-readings">
          <article className="indicator-card"><span>Data integrity</span><strong>{analysis.data_quality?.status ?? "UNAVAILABLE"}</strong><small>{analysis.data_quality ? `${analysis.data_quality.candle_gap_count} gaps · spread ${analysis.data_quality.spread_state}` : "No quality snapshot"}</small></article>
          <article className="indicator-card"><span>Session</span><strong>{analysis.session_regime?.session_label.replaceAll("_", " ") ?? "UNAVAILABLE"}</strong><small>{analysis.session_regime?.session_timezone_basis ?? "Timezone basis unavailable"}</small></article>
          <article className="indicator-card"><span>Regime</span><strong>{analysis.session_regime?.market_regime ?? "UNAVAILABLE"}</strong><small>Volatility: {analysis.session_regime?.volatility_regime ?? "UNAVAILABLE"}</small></article>
          <article className="indicator-card"><span>Event risk</span><strong>{analysis.event_risk_state.replaceAll("_", " ")}</strong><small>Frozen with each research decision</small></article>
        </div>
      </section>

      {analysis.professional_analysis && <section className="modal-section" aria-labelledby="professional-title">
        <div className="modal-section-heading"><h3 id="professional-title">Professional research modules</h3><small>Source-labelled; not an order instruction</small></div>
        <div className="indicator-grid compact-readings">
          <article className="indicator-card"><span>Volume source</span><strong>{analysis.professional_analysis.volume_source_category.replaceAll("_", " ")}</strong><small>{analysis.professional_analysis.volume_momentum.vwap_basis}</small></article>
          <article className="indicator-card"><span>Liquidity sweep</span><strong>{analysis.professional_analysis.liquidity_sweep.state.replaceAll("_", " ")}</strong><small>{analysis.professional_analysis.liquidity_sweep.absorption_state.replaceAll("_", " ")}</small></article>
          <article className="indicator-card"><span>Estimated CVD</span><strong>{reading(analysis.professional_analysis.estimated_order_flow.session_cvd, 0)}</strong><small>Price-direction estimate, not executed flow</small></article>
          <article className="indicator-card"><span>Risk review</span><strong>{analysis.professional_analysis.risk_engine.state.replaceAll("_", " ")}</strong><small>{analysis.professional_analysis.risk_engine.lifecycle_state.replaceAll("_", " ")}</small></article>
        </div>
        <ul className="modal-timeframes ensemble-votes">{analysis.professional_analysis.strategy_modules.map((module) => <li key={module.strategy_id}><div className="timeframe-label"><strong>{module.strategy_id.replaceAll("_", " ")}</strong><span className={module.direction === "WATCH_LONG" ? "positive" : module.direction === "WATCH_SHORT" ? "negative" : "neutral"}>{module.state.replaceAll("_", " ")}</span></div><small>{module.strategy_version} · {module.data_sources.map((source) => source.replaceAll("_", " ")).join(", ")}</small></li>)}</ul>
      </section>}

      <section className="modal-section" aria-labelledby="indicators-title">
        <div className="modal-section-heading">
          <div><h3 id="indicators-title">M5 technical readings</h3><small>Calculated from completed M5 broker candles only</small></div>
          <span className={`structure-pill ${indicatorTone(primary?.structure)}`}>{primary ? structureLabel(primary.structure) : "UNAVAILABLE"}</span>
        </div>
        {indicators ? <div className="indicator-grid">
          <article className="indicator-card"><span>EMA trend</span><strong>{reading(indicators.ema_20)} / {reading(indicators.ema_60)}</strong><small>EMA 20 / EMA 60</small></article>
          <article className="indicator-card"><span>RSI</span><strong>{reading(indicators.rsi_14, 1)}</strong><small>14-period momentum</small></article>
          <article className="indicator-card"><span>ADX</span><strong>{reading(indicators.adx_14, 1)}</strong><small>14-period trend strength</small></article>
          <article className="indicator-card"><span>ATR</span><strong>{reading(indicators.atr_14)}</strong><small>14-period average range</small></article>
          <article className="indicator-card"><span>MACD histogram</span><strong>{reading(indicators.macd_histogram, 3)}</strong><small>12 / 26 / 9 context</small></article>
          <article className="indicator-card"><span>Range position</span><strong>{reading(indicators.range_position_percent, 0)}%</strong><small>Within the completed window</small></article>
        </div> : <p className="indicator-unavailable">Indicator values are unavailable until the completed broker-candle window is live.</p>}
      </section>

      <section className="modal-section" aria-labelledby="timeframes-title">
        <div className="modal-section-heading"><h3 id="timeframes-title">Multi-timeframe structure</h3><small>M5 / M15 / H1 / H4</small></div>
        <ul className="modal-timeframes" aria-label="Multi-timeframe broker-candle evidence">
          {analysis.analysis_timeframes.map((evidence) => <li key={evidence.timeframe}>
            <div className="timeframe-label"><strong>{evidence.timeframe}</strong><span className={indicatorTone(evidence.structure)}>{structureLabel(evidence.structure)}</span></div>
            <small>{evidence.completed_candles}/{evidence.required_completed_candles} completed · {evidence.window_label} · {evidence.data_status}</small>
            <div className="timeframe-readings">
              <span>RSI {reading(evidence.indicators?.rsi_14, 1)}</span>
              <span>ADX {reading(evidence.indicators?.adx_14, 1)}</span>
              <span>ATR {reading(evidence.indicators?.atr_14)}</span>
            </div>
          </li>)}
        </ul>
      </section>

      <section className="modal-section" aria-labelledby="ensemble-title">
        <div className="modal-section-heading"><h3 id="ensemble-title">Independent-rule ensemble</h3><small>Confidence remains withheld</small></div>
        {analysis.strategy_ensemble ? <>
          <p className="indicator-unavailable">{analysis.strategy_ensemble.agreement_count}/{analysis.strategy_ensemble.required_agreement_count} independent rules agree. Model state: {analysis.strategy_ensemble.model_promotion_state}.</p>
          <ul className="modal-timeframes ensemble-votes">{analysis.strategy_ensemble.votes.map((vote) => <li key={vote.strategy_id}><div className="timeframe-label"><strong>{vote.strategy_id.replaceAll("_", " ")}</strong><span className={vote.decision === "WATCH_LONG" ? "positive" : vote.decision === "WATCH_SHORT" ? "negative" : "neutral"}>{vote.decision.replaceAll("_", " ")}</span></div><small>{vote.strategy_version} · completed-candle deterministic rule</small></li>)}</ul>
        </> : <p className="indicator-unavailable">The ensemble is unavailable because required source evidence is incomplete.</p>}
      </section>

      <section className="modal-section" aria-labelledby="paper-title">
        <div className="modal-section-heading"><h3 id="paper-title">Paper-trading evidence</h3><small>Background completed-M5 cycles only</small></div>
        <p className="indicator-unavailable">{analysis.paper_trading?.status ?? "NOT_CREATED"} · expected spread {reading(analysis.paper_trading?.expected_spread_points, 1)} points. Commission, slippage, and actual-fill quality remain unavailable until source-backed data exists.</p>
      </section>

      <footer className="analysis-modal-footer">
        <p>Indicators are descriptive research context, not a prediction or trading instruction.</p>
        <code>{analysis.analysis_mode} · {analysis.reason_codes.join(" / ")}</code>
      </footer>
    </section>
  </div>;
}
