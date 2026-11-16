from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import isfinite
from pathlib import Path

from app.analysis.quality import assess_data_quality, classify_session_and_regime
from app.analysis.confluence import validate_top_down
from app.analysis.professional import professional_research
from app.analysis.technical import analyze_completed_candles
from app.adapters.calendar import ForexFactoryCalendarAdapter
from app.adapters.official_macro import OfficialMacroScheduleAdapter
from app.adapters.mt5 import MT5Adapter
from app.schemas.market import Candle, DataQualityReport, DataStatus, EventsResponse, LiveResearchWatchResponse, MarketAnalysisResponse, MarketDepthReport, OperationsStatus, PaperTradingReport, ProfessionalResearchReport, QuoteResponse, ResearchBotReport, ResearchReferenceLevels, ResearchResponse, ResearchSignalProof, ResearchSignalProofCheck, StrategyEnsemble, StrategyVote, TechnicalIndicators, TimeframeEvidence
from app.services.cross_market import CrossMarketContextService
from app.storage.database import (
    count_research_evidence,
    read_operations_status,
    read_strategy_settings,
    record_broker_session_state,
    record_research_evidence,
)


WINDOW_HOURS = 12


@dataclass(frozen=True)
class TimeframeSpec:
    timeframe: str
    duration: timedelta
    required_completed_candles: int
    window_label: str
    indicator_warmup_candles: int = 180


# Every window has enough completed candles for the MA60 context and the
# technical helpers. MT5 returns one additional forming candle.
TIMEFRAME_SPECS = (
    TimeframeSpec("M5", timedelta(minutes=5), 144, "12h"),
    TimeframeSpec("M15", timedelta(minutes=15), 96, "24h"),
    TimeframeSpec("H1", timedelta(hours=1), 72, "3d"),
    TimeframeSpec("H4", timedelta(hours=4), 60, "10d"),
)

AUXILIARY_TIMEFRAME_SPECS = (
    TimeframeSpec("D1", timedelta(days=1), 60, "60 broker days"),
    TimeframeSpec("M1", timedelta(minutes=1), 60, "1h"),
)


@dataclass(frozen=True)
class ChartEvidence:
    structure: str
    primary: "TimeframeAssessment"
    timeframes: tuple["TimeframeAssessment", ...]


@dataclass(frozen=True)
class TimeframeAssessment:
    spec: TimeframeSpec
    data_status: DataStatus
    reason_codes: tuple[str, ...]
    completed_candles: int
    source_timestamp_utc: datetime | None
    anchor: Candle | None = None
    structure: str = "UNAVAILABLE"
    moving_average_context: str = "UNAVAILABLE"
    close_location: float | None = None
    recent_up_closes: int = 0
    recent_down_closes: int = 0
    net_change: float | None = None
    average_range_20: float | None = None
    latest_break: str | None = None
    active_gaps: int = 0
    total_gaps: int = 0
    indicators: TechnicalIndicators | None = None
    window: tuple[Candle, ...] = ()
    setup_kind: str | None = None
    setup_known_at_utc: datetime | None = None
    invalidation_price: float | None = None


class ResearchCoordinator:
    """Coordinates separate evidence readers; it deliberately cannot issue a trade signal."""

    def __init__(
        self,
        adapter: MT5Adapter,
        calendar: ForexFactoryCalendarAdapter,
        database_path: Path,
        official_macro: OfficialMacroScheduleAdapter | None = None,
        cross_market: CrossMarketContextService | None = None,
    ) -> None:
        self.adapter = adapter
        self.calendar = calendar
        self.database_path = database_path
        self.official_macro = official_macro
        self.cross_market = cross_market

    def snapshot(
        self,
        symbol: str | None,
        calendar_response: EventsResponse | None = None,
        *,
        persist_evidence: bool = True,
        quote_snapshot: QuoteResponse | None = None,
    ) -> ResearchResponse:
        now = datetime.now(UTC)
        quote = quote_snapshot if quote_snapshot is not None else self.adapter.quote(symbol)
        chart_bot, anchor, chart_evidence = self._chart_bot(symbol, now)
        macro_sources = self.official_macro.snapshot() if self.official_macro else []
        calendar_bot, calendar_state = self._calendar_bot(now, calendar_response, macro_sources)
        primary_window = list(chart_evidence.primary.window) if chart_evidence else []
        quality = assess_data_quality(quote, primary_window, timeframe=TIMEFRAME_SPECS[0].duration, now=now)
        quality = self._with_session_transition(symbol, quality)
        regime = classify_session_and_regime(
            primary_window,
            structure=chart_evidence.structure if chart_evidence else "UNAVAILABLE",
            spread_state=quality.spread_state,
            now=now,
        )
        quality_bot = self._quality_bot(now, quality)
        momentum_bot = self._momentum_bot(now, chart_evidence)
        context = self.cross_market.snapshot() if self.cross_market else []
        context_bot = self._context_bot(now, context)
        professional = self._professional_analysis(
            symbol, quote, primary_window, calendar_state,
            cross_market_available=any(item.data_status == DataStatus.LIVE for item in context),
            data_quality=quality,
        )
        professional_bots = self._professional_bots(now, professional)
        evidence_count = count_research_evidence(self.database_path, symbol)
        ensemble = self._strategy_ensemble(symbol, chart_evidence, quality, calendar_state)
        strategy_bot = self._strategy_bot(now, chart_bot, calendar_bot, quality_bot, ensemble, evidence_count)

        if persist_evidence and symbol and anchor and chart_bot.data_status == DataStatus.LIVE:
            record_research_evidence(
                self.database_path,
                observed_at_utc=now,
                symbol=symbol,
                candle_open_utc=anchor.open_time_utc,
                chart_structure=chart_evidence.structure if chart_evidence else "UNAVAILABLE",
                calendar_state=calendar_state,
                consensus_state=ensemble.decision,
                source_statuses={
                    "chart": chart_bot.data_status.value,
                    "calendar": calendar_bot.data_status.value,
                    **{
                        f"chart_{assessment.spec.timeframe}": assessment.data_status.value
                        for assessment in chart_evidence.timeframes
                    },
                },
            )
            evidence_count = count_research_evidence(self.database_path, symbol)
            strategy_bot = self._strategy_bot(now, chart_bot, calendar_bot, quality_bot, ensemble, evidence_count)

        broker_ready = (
            quote.data_status == DataStatus.LIVE
            and chart_bot.data_status == DataStatus.LIVE
            and chart_bot.state != "BLOCKED"
            and quality.status != "BLOCK"
        )
        market_state = "DATA UNAVAILABLE"
        if broker_ready:
            market_state = "NO TRADE"
            if professional.risk_engine.state == "REVIEW_REQUIRED":
                market_state = {
                    "WATCH_LONG": "WATCH LONG",
                    "WATCH_SHORT": "WATCH SHORT",
                }.get(ensemble.decision, "NO TRADE")
        research = ResearchResponse(
            observed_at_utc=now,
            source_timestamp_utc=self._conservative_source_timestamp(chart_evidence, chart_bot.source_timestamp_utc),
            data_status=(
                quote.data_status if quote.data_status != DataStatus.LIVE
                else DataStatus.LIVE if broker_ready else chart_bot.data_status
            ),
            reason_codes=[*ensemble.reason_codes, "STRATEGY_VALIDATION_REQUIRED", "CONFIDENCE_WITHHELD"],
            symbol=symbol,
            market_state=market_state,
            analysis_timeframes=self._public_timeframe_evidence(chart_evidence),
            bots=[quality_bot, chart_bot, momentum_bot, calendar_bot, context_bot, *professional_bots, strategy_bot],
            evidence_observations=evidence_count,
            data_quality=quality,
            session_regime=regime,
            cross_market=context,
            official_macro_sources=macro_sources,
            event_risk_state=calendar_state,
            strategy_ensemble=ensemble,
            professional_analysis=professional,
            operations=OperationsStatus(**read_operations_status(self.database_path)),
        )
        gates = self._research_gates(quote, chart_bot, chart_evidence, calendar_bot, calendar_state, quality, professional)
        auxiliary = tuple(self._timeframe_assessment(symbol, spec, now=now) for spec in AUXILIARY_TIMEFRAME_SPECS)
        top_down = validate_top_down(
            [*research.analysis_timeframes, *self._public_timeframe_evidence_from_assessments(auxiliary)],
            observed_at=now, risk_clear=all(gate["state"] == "PASS" for gate in gates),
        )
        research = research.model_copy(update={"top_down": top_down})
        return research.model_copy(update={
            "live_research_watch": self._build_live_research_watch(
                research,
                gates,
                quote=quote,
                chart=chart_evidence,
            ),
        })

    def analyze_market(self, symbol: str | None) -> MarketAnalysisResponse:
        """Save an on-demand review of the same evidence and gates used by the live watch."""
        research = self.snapshot(symbol, persist_evidence=False)
        watch = research.live_research_watch
        ensemble = research.strategy_ensemble
        decision = ensemble.decision if (
            ensemble and watch and watch.lifecycle == "ACTIVE_RESEARCH_WATCH"
            and research.top_down and research.top_down.state == "CONFIRMED"
        ) else "NO_TRADE"
        structures = {item.structure for item in research.analysis_timeframes}
        context = next(iter(structures)) if len(structures) == 1 else "MIXED_STRUCTURE"
        if not research.analysis_timeframes or any(item.data_status != DataStatus.LIVE for item in research.analysis_timeframes):
            context = "UNAVAILABLE"
        bots = {bot.bot_id: bot for bot in research.bots}
        facts = [f"Chart bot: {bots['chart'].summary}", f"News bot: {bots['calendar'].summary}"]
        if research.session_regime:
            regime = research.session_regime
            facts.append(f"Session/regime: {regime.session_label} / {regime.market_regime} / {regime.volatility_regime}.")
        facts.append("Review uses the shared automatic evidence snapshot and top-down gates.")
        reasons = ["RESEARCH_SCREEN_V5_SHARED_TOP_DOWN", "NO_ORDER_EXECUTION"]
        if decision == "NO_TRADE":
            reasons.append("SHARED_RESEARCH_GATES_NOT_MET")
            summary = "No trade: required top-down confirmations, source integrity, risk checks or rule agreement are incomplete."
        else:
            reasons.extend(["WATCH_CONDITION_MET", "UNVALIDATED_RESEARCH_SIGNAL"])
            summary = "Directional research context passes the shared top-down review; publication proof and performance remain separate."
        return MarketAnalysisResponse(
            observed_at_utc=research.observed_at_utc, source_timestamp_utc=research.source_timestamp_utc,
            data_status=research.data_status, reason_codes=reasons, symbol=symbol, decision=decision,
            market_context=context, summary=summary, gates=watch.gates if watch else [],
            analysis_timeframes=research.analysis_timeframes, supporting_facts=facts,
            data_quality=research.data_quality, session_regime=research.session_regime,
            cross_market=research.cross_market, official_macro_sources=research.official_macro_sources,
            event_risk_state=research.event_risk_state, strategy_ensemble=ensemble,
            professional_analysis=research.professional_analysis, top_down=research.top_down,
            paper_trading=PaperTradingReport(
                expected_spread_points=research.data_quality.spread_points if research.data_quality else None,
                reason_codes=["BACKGROUND_COMPLETED_CANDLE_CYCLE_REQUIRED", "COMMISSION_UNAVAILABLE", "SLIPPAGE_UNAVAILABLE", "NO_ORDER_EXECUTION"],
            ),
        )

    def live_research_watch(self, symbol: str | None) -> LiveResearchWatchResponse:
        """Return the current automatic research-watch lifecycle without persisting a user review.

        The decision is recalculated from current source status and completed
        candles. Any reference levels are unvalidated context, not an order,
        size, probability, or performance claim.
        """
        research = self.snapshot(symbol, persist_evidence=False)
        if research.live_research_watch is not None:
            return research.live_research_watch
        return self._build_live_research_watch(research, [])

    def _build_live_research_watch(
        self,
        research: ResearchResponse,
        gates: list[dict[str, str]],
        *,
        quote: QuoteResponse | None = None,
        chart: ChartEvidence | None = None,
    ) -> LiveResearchWatchResponse:
        """Build an automatic watch from one already-read research snapshot.

        The endpoint and workstation use this same object.  That prevents a
        second competing set of MT5 reads and ensures that the chart bots and
        the watch always describe the exact same completed-candle evidence.
        """
        m5 = next((item for item in research.analysis_timeframes if item.timeframe == "M5"), None)
        scheduled_review_at = (
            m5.source_timestamp_utc + TIMEFRAME_SPECS[0].duration
            if m5 and m5.source_timestamp_utc else None
        )
        expired = scheduled_review_at is not None and research.observed_at_utc >= scheduled_review_at
        ensemble = research.strategy_ensemble
        direction = {
            "WATCH_LONG": "LONG_CONTEXT",
            "WATCH_SHORT": "SHORT_CONTEXT",
        }.get(ensemble.decision if ensemble else "NO_TRADE", "NONE")
        has_completed_evidence = bool(m5 and m5.data_status == DataStatus.LIVE)
        has_live_sources = research.data_status == DataStatus.LIVE and has_completed_evidence

        publication_stopped = bool(research.operations and (research.operations.kill_switch_enabled or not research.operations.research_pipeline_enabled))
        if not has_live_sources:
            lifecycle = "UNAVAILABLE"
        elif expired:
            lifecycle = "EXPIRED"
        elif publication_stopped:
            lifecycle = "WITHHELD"
        elif ensemble and ensemble.decision in {"WATCH_LONG", "WATCH_SHORT"}:
            lifecycle = "ACTIVE_RESEARCH_WATCH"
        else:
            lifecycle = "WITHHELD"

        blocked_gates = [
            f"{gate['label']}: {gate['reason']}"
            for gate in gates
            if gate["state"] == "BLOCK"
        ]
        if publication_stopped:
            blocked_gates.insert(0, "Automatic research publication is stopped by the local operator.")
        score = self._watch_evidence_score_from_research(research)
        horizon, horizon_basis, horizon_review_at, horizon_reason_codes = self._research_horizon(
            research,
            lifecycle=lifecycle,
            direction=direction,
        )
        reference_levels, levels_reason = self._reference_levels(
            quote, chart, direction if lifecycle == "ACTIVE_RESEARCH_WATCH" and research.top_down and research.top_down.state == "CONFIRMED" else "NONE",
            gates, research.observed_at_utc,
        )
        if lifecycle == "ACTIVE_RESEARCH_WATCH" and research.top_down and research.top_down.state != "CONFIRMED":
            levels_reason = "TOP_DOWN_CONFIRMATION_REQUIRED"
        signal_proof = self._signal_proof(
            research, quote, chart, lifecycle, direction, gates, reference_levels,
        )
        invalidation_conditions = [
            "A newer completed M5 candle triggers the next deterministic review.",
            "The watch is withdrawn if broker data becomes stale, a spread anomaly appears, or multi-timeframe rules disagree.",
            "The watch is withdrawn if the verified USD-event risk horizon becomes elevated.",
        ]
        if lifecycle == "UNAVAILABLE":
            summary = "Automatic research watch is unavailable because a required source or completed M5 evidence window is unavailable."
            invalidation_conditions = blocked_gates or ["Required source-backed evidence is unavailable."]
        elif lifecycle == "EXPIRED":
            summary = "The previous completed-candle research watch has expired and is waiting for its next source-backed M5 review."
        elif lifecycle == "ACTIVE_RESEARCH_WATCH":
            summary = (
                f"{ensemble.decision.replace('_', ' ').title()} is active as a completed-candle research watch until the next review. "
                "It is not a trade instruction, probability, or performance claim."
            )
        else:
            summary = "Automatic research watch is withheld because the deterministic readers or safety gates do not currently support a directional research watch."
            invalidation_conditions = blocked_gates or [
                "Independent completed-candle rules must reach the required agreement.",
                *invalidation_conditions,
            ]

        return LiveResearchWatchResponse(
            observed_at_utc=research.observed_at_utc,
            source_timestamp_utc=research.source_timestamp_utc,
            data_status=research.data_status,
            reason_codes=list(dict.fromkeys([
                *research.reason_codes,
                "AUTOMATIC_LIVE_RESEARCH_WATCH",
                "EVIDENCE_SCORE_NOT_PROBABILITY",
                "NO_ORDER_EXECUTION",
            ])),
            symbol=research.symbol,
            lifecycle=lifecycle,
            direction=direction if lifecycle == "ACTIVE_RESEARCH_WATCH" else "NONE",
            research_horizon=horizon,
            horizon_basis=horizon_basis,
            horizon_review_at_utc=horizon_review_at,
            horizon_reason_codes=horizon_reason_codes,
            evidence_score=score,
            reference_levels=reference_levels,
            reference_levels_reason=levels_reason,
            signal_proof=signal_proof,
            active_from_utc=m5.source_timestamp_utc if m5 else None,
            scheduled_review_at_utc=scheduled_review_at,
            expires_at_utc=scheduled_review_at,
            summary=summary,
            invalidation_conditions=invalidation_conditions,
            gates=gates,
            analysis_timeframes=research.analysis_timeframes,
            top_down=research.top_down,
            data_quality=research.data_quality,
            event_risk_state=research.event_risk_state,
            strategy_ensemble=ensemble,
        )

    @staticmethod
    def _signal_proof(
        research: ResearchResponse,
        quote: QuoteResponse | None,
        chart: ChartEvidence | None,
        lifecycle: str,
        direction: str,
        gates: list[dict[str, str]],
        levels: ResearchReferenceLevels | None,
    ) -> ResearchSignalProof:
        """Publish only source-backed research alerts; never infer a win probability."""
        observed_at = research.observed_at_utc
        quote_age = (observed_at - quote.observed_at_utc).total_seconds() if quote else None
        quote_fresh = bool(
            quote and quote.data_status == DataStatus.LIVE
            and quote.tick_age_seconds is not None and 0 <= quote.tick_age_seconds <= 5
            and quote_age is not None and -2 <= quote_age <= 5
            and quote.bid is not None and quote.ask is not None
        )
        timeframes = {item.timeframe: item for item in research.analysis_timeframes}
        aligned = [timeframes.get(timeframe) for timeframe in ("M5", "M15", "H1")]
        structures = {item.structure for item in aligned if item is not None}
        expected_structure = "UPWARD_STRUCTURE" if direction == "LONG_CONTEXT" else "DOWNWARD_STRUCTURE" if direction == "SHORT_CONTEXT" else None
        completed_context = (
            all(
                item is not None and item.data_status == DataStatus.LIVE
                and item.source_timestamp_utc is not None
                and item.completed_candles >= item.required_completed_candles
                for item in aligned
            )
            and len(structures) == 1
            and structures <= {"UPWARD_STRUCTURE", "DOWNWARD_STRUCTURE"}
            and (expected_structure is None or expected_structure in structures)
        )
        quality = research.data_quality
        calendar = next((bot for bot in research.bots if bot.bot_id == "calendar"), None)
        ensemble = research.strategy_ensemble
        expected_vote = "WATCH_LONG" if direction == "LONG_CONTEXT" else "WATCH_SHORT"
        opposing_vote = "WATCH_SHORT" if expected_vote == "WATCH_LONG" else "WATCH_LONG"
        aligned_votes = [vote for vote in ensemble.votes if vote.decision == expected_vote] if ensemble else []
        no_opposition = bool(
            ensemble and lifecycle == "ACTIVE_RESEARCH_WATCH"
            and ensemble.decision == expected_vote
            and len(aligned_votes) >= ensemble.required_agreement_count
            and not any(vote.decision == opposing_vote for vote in ensemble.votes)
        )
        m5_atr = timeframes.get("M5").indicators.atr_14 if timeframes.get("M5") and timeframes["M5"].indicators else None
        spread = quote.ask - quote.bid if quote and quote.ask is not None and quote.bid is not None else None
        reported_spread = quote.spread_points * quote.point if quote and quote.spread_points is not None and quote.point else None
        spread_buffer_clear = bool(
            spread is not None and reported_spread is not None and m5_atr is not None
            and isfinite(spread) and isfinite(reported_spread) and isfinite(m5_atr)
            and spread > 0 and m5_atr > 0
            and abs(spread - reported_spread) <= quote.point * 1.5
            and spread <= m5_atr * 0.25
        )
        completed_m5 = chart.primary.window if chart else ()
        close_triggered = ResearchCoordinator._completed_close_breakout(completed_m5, direction)
        checks = [
            ResearchSignalProofCheck(code="FRESH_BROKER_QUOTE", passed=quote_fresh, detail="Live bid/ask and broker tick age at the decision time"),
            ResearchSignalProofCheck(code="COMPLETED_MTF_ALIGNMENT", passed=completed_context, detail="Completed M5, M15 and H1 broker-candle structures align"),
            ResearchSignalProofCheck(code="DATA_QUALITY_CLEAR", passed=bool(quality and quality.status == "CLEAR" and quality.spread_state == "NORMAL"), detail="Integrity clear and spread within observed range"),
            ResearchSignalProofCheck(code="CALENDAR_RISK_CHECKED", passed=bool(calendar and calendar.data_status == DataStatus.LIVE and calendar.source_url and research.event_risk_state in {"NO_EVENT_IN_EXPORT", "UPCOMING_USD_EVENT"}), detail="Source-labelled USD calendar has no known elevated window; absence is not guaranteed"),
            ResearchSignalProofCheck(code="RULE_AGREEMENT_NO_OPPOSITION", passed=no_opposition, detail="At least two deterministic rules agree and none votes the opposite way"),
            ResearchSignalProofCheck(code="CENTRAL_RISK_GATE", passed=bool(gates) and all(gate["state"] == "PASS" for gate in gates), detail="All central research gates pass at this snapshot"),
            ResearchSignalProofCheck(code="SOURCE_BACKED_LEVELS", passed=bool(levels and quote and levels.quote_observed_at_utc == quote.observed_at_utc and timeframes.get("M5") and levels.source_candle_close_utc == timeframes["M5"].source_timestamp_utc), detail="Indicative levels use this quote and completed M5 ATR"),
            ResearchSignalProofCheck(code="SPREAD_BUFFER_WITHIN_ATR", passed=spread_buffer_clear, detail="Broker bid/ask spread agrees with reported points and is at most 25% of completed M5 ATR; this heuristic is not performance validated"),
            ResearchSignalProofCheck(code="COMPLETED_CLOSE_TRIGGER", passed=close_triggered, detail="Latest completed M5 close breaks the prior 20 completed closes in the research direction; continuation heuristic, not a fill"),
            ResearchSignalProofCheck(code="TOP_DOWN_CONFIRMATION", passed=bool(research.top_down and research.top_down.state == "CONFIRMED"), detail="D1/H4 bias, H1 direction, M15 setup, M5 completed trigger and risk gates; M1 is optional timing"),
            ResearchSignalProofCheck(code="OPERATIONS_ALLOW_PUBLICATION", passed=bool(research.operations and not research.operations.kill_switch_enabled and research.operations.research_pipeline_enabled), detail="Research worker enabled and emergency stop clear at this review"),
        ]
        failed = [check.code for check in checks if not check.passed]
        return ResearchSignalProof(
            publication_state="WITHHELD" if failed else "ELIGIBLE",
            checks=checks,
            rule_versions=[vote.strategy_version for vote in aligned_votes],
            reason_codes=[*failed, "PERFORMANCE_UNVALIDATED", "NO_ORDER_EXECUTION"],
        )

    @staticmethod
    def _completed_close_breakout(candles: tuple[Candle, ...], direction: str) -> bool:
        recent = candles[-21:]
        if len(recent) != 21 or not all(candle.completed for candle in recent):
            return False
        if direction in {"LONG_CONTEXT", "WATCH_LONG"}:
            return recent[-1].close > max(candle.close for candle in recent[:-1])
        if direction in {"SHORT_CONTEXT", "WATCH_SHORT"}:
            return recent[-1].close < min(candle.close for candle in recent[:-1])
        return False

    @staticmethod
    def _reference_levels(
        quote: QuoteResponse | None,
        chart: ChartEvidence | None,
        direction: str,
        gates: list[dict[str, str]],
        observed_at: datetime,
    ) -> tuple[ResearchReferenceLevels | None, str]:
        """Describe an unvalidated 1R/2R scenario only for a fresh, active watch."""
        if direction == "NONE" or any(gate["state"] == "BLOCK" for gate in gates):
            return None, "NO_ACTIVE_DIRECTIONAL_RESEARCH_WATCH"
        if not quote or quote.data_status != DataStatus.LIVE or quote.bid is None or quote.ask is None:
            return None, "LIVE_BROKER_QUOTE_REQUIRED"
        if quote.tick_age_seconds is None or quote.tick_age_seconds > 5 or (observed_at - quote.observed_at_utc).total_seconds() > 5:
            return None, "FRESH_BROKER_QUOTE_REQUIRED"
        primary = chart.primary if chart else None
        atr = primary.indicators.atr_14 if primary and primary.indicators else None
        if not primary or not primary.anchor or not atr or not isfinite(atr) or atr <= 0 or not primary.source_timestamp_utc:
            return None, "COMPLETED_M5_ATR_REQUIRED"
        entry = quote.ask if direction == "LONG_CONTEXT" else quote.bid
        if not isfinite(entry) or entry <= 0 or abs(entry - primary.anchor.close) > atr:
            return None, "QUOTE_OUTSIDE_COMPLETED_M5_ATR"
        sign = 1 if direction == "LONG_CONTEXT" else -1
        step = quote.tick_size or quote.point
        if not step or not isfinite(step) or step <= 0:
            return None, "BROKER_TICK_SIZE_REQUIRED"
        def aligned(value: float) -> float:
            return round(round(value / step) * step, 8)
        levels = ResearchReferenceLevels(
            entry=aligned(entry),
            stop_loss=aligned(entry - sign * atr),
            take_profit_1=aligned(entry + sign * atr),
            take_profit_2=aligned(entry + sign * 2 * atr),
            source_candle_close_utc=primary.source_timestamp_utc,
            quote_observed_at_utc=quote.observed_at_utc,
        )
        ordered = (
            levels.stop_loss < levels.entry < levels.take_profit_1 < levels.take_profit_2
            if sign == 1 else
            levels.stop_loss > levels.entry > levels.take_profit_1 > levels.take_profit_2
        )
        if not ordered:
            return None, "ATR_BELOW_BROKER_TICK_SIZE"
        return levels, "UNVALIDATED_REFERENCE_ONLY"

    @staticmethod
    def _research_horizon(
        research: ResearchResponse,
        *,
        lifecycle: str,
        direction: str,
    ) -> tuple[str, str, datetime | None, list[str]]:
        """Classify evidence breadth without suggesting a holding duration.

        The M5 review remains the fast safety/withdrawal cadence for every
        watch. This helper only tells the UI how much independently completed
        higher-timeframe context agrees with that watch.
        """
        if lifecycle != "ACTIVE_RESEARCH_WATCH" or direction == "NONE":
            return (
                "UNAVAILABLE",
                "NO_ACTIVE_DIRECTIONAL_RESEARCH_WATCH",
                None,
                ["NO_ACTIVE_DIRECTIONAL_RESEARCH_WATCH"],
            )

        expected_structure = "UPWARD_STRUCTURE" if direction == "LONG_CONTEXT" else "DOWNWARD_STRUCTURE"
        evidence_by_timeframe = {item.timeframe: item for item in research.analysis_timeframes}

        def aligned(timeframes: tuple[str, ...]) -> bool:
            return all(
                (item := evidence_by_timeframe.get(timeframe)) is not None
                and item.data_status == DataStatus.LIVE
                and item.structure == expected_structure
                for timeframe in timeframes
            )

        def next_review(timeframe: str) -> datetime | None:
            item = evidence_by_timeframe.get(timeframe)
            spec = next((candidate for candidate in TIMEFRAME_SPECS if candidate.timeframe == timeframe), None)
            if not item or not item.source_timestamp_utc or not spec:
                return None
            return item.source_timestamp_utc + spec.duration

        if aligned(("M5", "M15", "H1", "H4")):
            return (
                "MULTI_SESSION_CONTEXT",
                "M5_M15_H1_H4_COMPLETED_CANDLES_ALIGNED",
                next_review("H4"),
                ["M5_M15_H1_H4_COMPLETED_CANDLES_ALIGNED", "H4_CONTEXT_CONFIRMED"],
            )
        if aligned(("M5", "M15", "H1")):
            return (
                "INTRADAY_CONTEXT",
                "M5_M15_H1_COMPLETED_CANDLES_ALIGNED",
                next_review("H1"),
                ["M5_M15_H1_COMPLETED_CANDLES_ALIGNED", "H4_CONTEXT_NOT_ALIGNED_OR_UNAVAILABLE"],
            )
        if aligned(("M5", "M15")):
            return (
                "SHORT_HORIZON_CONTEXT",
                "M5_M15_COMPLETED_CANDLES_ALIGNED",
                next_review("M15"),
                ["M5_M15_COMPLETED_CANDLES_ALIGNED", "H1_H4_CONTEXT_NOT_ALIGNED_OR_UNAVAILABLE"],
            )
        return (
            "UNAVAILABLE",
            "MULTI_TIMEFRAME_CONTEXT_NOT_ALIGNED",
            None,
            ["MULTI_TIMEFRAME_CONTEXT_NOT_ALIGNED"],
        )

    @staticmethod
    def _watch_evidence_score_from_research(research: ResearchResponse) -> int:
        """Score source-backed evidence coverage only; never forecast likelihood."""
        score = 0
        if research.data_status == DataStatus.LIVE:
            score += 20
        if research.analysis_timeframes and all(item.data_status == DataStatus.LIVE for item in research.analysis_timeframes):
            score += 20
        if research.data_quality:
            score += 20 if research.data_quality.status == "CLEAR" else 10 if research.data_quality.status == "WATCH" else 0
        if research.event_risk_state not in {"HIGH_IMPACT_WINDOW", "ELEVATED_EVENT_WINDOW", "UNVERIFIED"}:
            score += 15
        ensemble = research.strategy_ensemble
        if ensemble and ensemble.required_agreement_count:
            score += round(min(ensemble.agreement_count, ensemble.required_agreement_count) / ensemble.required_agreement_count * 20)
            if ensemble.decision in {"WATCH_LONG", "WATCH_SHORT"}:
                score += 5
        return min(score, 100)

    @staticmethod
    def _research_gates(
        quote: object,
        chart_bot: ResearchBotReport,
        chart: ChartEvidence | None,
        calendar_bot: ResearchBotReport,
        calendar_state: str,
        quality: DataQualityReport,
        professional: ProfessionalResearchReport,
    ) -> list[dict[str, str]]:
        quote_status = getattr(quote, "data_status", DataStatus.SOURCE_ERROR)
        quote_live = quote_status == DataStatus.LIVE
        chart_ready = chart is not None and chart_bot.data_status == DataStatus.LIVE
        calendar_live = calendar_bot.data_status == DataStatus.LIVE
        event_risk_clear = calendar_state not in {"HIGH_IMPACT_WINDOW", "ELEVATED_EVENT_WINDOW", "UNVERIFIED"}
        integrity_eligible = quality.status != "BLOCK" and quality.spread_state != "ELEVATED"
        integrity_gate_state = "PASS" if quality.status == "CLEAR" else "WATCH" if integrity_eligible else "BLOCK"
        return [
            {"label": "Broker quote", "state": "PASS" if quote_live else "BLOCK", "reason": "LIVE" if quote_live else quote_status.value},
            {"label": "Tick / candle integrity", "state": integrity_gate_state, "reason": quality.status},
            {
                "label": "Completed M5 / M15 / H1 / H4 evidence",
                "state": "PASS" if chart_ready else "BLOCK",
                "reason": "MULTI_TIMEFRAME_COMPLETED" if chart_ready else chart_bot.data_status.value,
            },
            {"label": "USD calendar source", "state": "PASS" if calendar_live else "BLOCK", "reason": calendar_bot.data_status.value},
            {"label": "Event-risk horizon", "state": "PASS" if event_risk_clear else "BLOCK", "reason": calendar_state},
            {
                "label": "Central risk governor",
                "state": "PASS" if professional.risk_engine.state == "REVIEW_REQUIRED" else "BLOCK",
                "reason": professional.risk_engine.state,
            },
        ]

    @staticmethod
    def _quality_bot(now: datetime, quality: DataQualityReport) -> ResearchBotReport:
        state = "OBSERVING" if quality.status == "CLEAR" else "WATCHING" if quality.status == "WATCH" else "BLOCKED"
        return ResearchBotReport(
            bot_id="quality", label="Data quality sentinel", source="MT5", data_status=quality.quote_status,
            state=state, source_timestamp_utc=quality.checked_at_utc, updated_at_utc=now,
            summary=(
                "Tick freshness, completed-candle continuity, spread behavior, and broker-clock metadata are clear."
                if quality.status == "CLEAR" else
                "An observable broker-data integrity condition requires caution or abstention."
            ),
            skills=["Tick freshness", "Candle gap scan", "Spread anomaly scan", "Clock-drift retention"],
            facts=[
                f"Integrity state: {quality.status}; quote: {quality.quote_status.value}.",
                f"Candle gaps: {quality.candle_gap_count}; spread state: {quality.spread_state}.",
                f"Broker session observation: {quality.broker_session_state}.",
            ],
            reason_codes=quality.reason_codes or ["DATA_QUALITY_CLEAR"], evidence_count=0,
        )

    def _with_session_transition(self, symbol: str | None, quality: DataQualityReport) -> DataQualityReport:
        changed = record_broker_session_state(
            self.database_path, symbol=symbol, state=quality.broker_session_state, observed_at_utc=quality.checked_at_utc,
        )
        if not changed:
            return quality
        return quality.model_copy(update={
            "reason_codes": [*quality.reason_codes, "BROKER_SESSION_STATE_CHANGED"],
        })

    def _professional_analysis(
        self,
        symbol: str | None,
        quote: object,
        primary_window: list[Candle],
        calendar_state: str,
        cross_market_available: bool = False,
        data_quality: DataQualityReport | None = None,
    ) -> ProfessionalResearchReport:
        """Collect optional broker-depth capability separately from price data.

        Test adapters and older connector implementations do not need a depth
        method.  Their deterministic result remains explicitly unavailable.
        """
        from app.schemas.market import QuoteResponse

        if not isinstance(quote, QuoteResponse):
            raise TypeError("PROFESSIONAL_RESEARCH_REQUIRES_QUOTE_RESPONSE")
        read_depth = getattr(self.adapter, "market_depth", None)
        if callable(read_depth):
            depth = read_depth(symbol)
        else:
            depth = MarketDepthReport(
                data_status=DataStatus.NOT_CONFIGURED,
                summary="This MT5 adapter has no broker-depth capability reader.",
                reason_codes=["MT5_BROKER_DEPTH_ADAPTER_UNAVAILABLE", "LICENSED_FUTURES_ORDER_FLOW_NOT_CONFIGURED"],
            )
        return professional_research(
            primary_window, quote, calendar_state, depth,
            cross_market_available=cross_market_available,
            data_quality=data_quality,
        )

    @staticmethod
    def _professional_bots(now: datetime, report: ProfessionalResearchReport) -> list[ResearchBotReport]:
        def bot_state(state: str) -> str:
            if state == "UNAVAILABLE":
                return "BLOCKED"
            if state in {"ARMED", "TRIGGERED"}:
                return "WATCHING"
            return "OBSERVING"

        liquidity = report.liquidity_sweep
        momentum = report.volume_momentum
        depth = report.market_depth
        risk = report.risk_engine
        flow_status = DataStatus.LIVE if report.estimated_order_flow.data_status == DataStatus.LIVE else report.estimated_order_flow.data_status
        return [
            ResearchBotReport(
                bot_id="liquidity", label="Liquidity reversal analyst", source="MT5_COMPLETED_CANDLES",
                data_status=liquidity.data_status, state=bot_state(liquidity.state), updated_at_utc=now,
                summary="Confirmed liquidity-sweep/reclaim research with strict no-absorption claim without executed futures flow.",
                skills=["Confirmed swing levels", "Sweep/reclaim", "Structure-shift gate", "Absorption provenance"],
                facts=[
                    f"State: {liquidity.state}; direction: {liquidity.direction or 'none'}.",
                    f"Absorption: {liquidity.absorption_state}.",
                ], reason_codes=liquidity.reason_codes, evidence_count=0,
            ),
            ResearchBotReport(
                bot_id="volume", label="Volume & auction analyst", source="MT5_BROKER_TICK_ACTIVITY",
                data_status=momentum.data_status, state=bot_state(momentum.state), updated_at_utc=now,
                summary="VWAP, participation and profile are labelled broker tick-activity proxies, not executed market volume.",
                skills=["Tick-proxy VWAP", "Relative activity", "Close-bucket profile", "Opening range"],
                facts=[
                    f"VWAP basis: {momentum.vwap_basis}.",
                    f"Profile: {report.volume_profile.profile_basis}.",
                    f"Opening range: {report.opening_range.session} / {report.opening_range.state}.",
                ], reason_codes=[*momentum.reason_codes, *report.volume_profile.reason_codes], evidence_count=0,
            ),
            ResearchBotReport(
                bot_id="order_flow", label="Order-flow analyst", source="LICENSED_FUTURES_PROVIDER_REQUIRED",
                data_status=flow_status if depth.source_category.value == "UNAVAILABLE" else depth.data_status,
                state="BLOCKED" if depth.source_category.value == "UNAVAILABLE" else "OBSERVING", updated_at_utc=now,
                summary="Estimated delta is separated from genuine futures executed flow, footprint and market depth.",
                skills=["Estimated delta", "Session CVD", "Footprint gate", "Depth provenance"],
                facts=[
                    f"Estimated CVD: {report.estimated_order_flow.session_cvd if report.estimated_order_flow.session_cvd is not None else 'unavailable'}.",
                    depth.summary,
                ], reason_codes=[*report.estimated_order_flow.reason_codes, *depth.reason_codes], evidence_count=0,
            ),
            ResearchBotReport(
                bot_id="risk", label="Independent risk manager", source="MT5_CONTRACT_METADATA",
                data_status=DataStatus.LIVE if risk.quote_freshness_available else DataStatus.SOURCE_ERROR,
                state="BLOCKED" if risk.state in {"REJECTED", "DATA_UNAVAILABLE"} else "COLLECTING_EVIDENCE", updated_at_utc=now,
                summary="Independent non-bypassable review rejects incomplete or conflicting research; it cannot approve an order.",
                skills=["Quote freshness", "Contract metadata", "Spread check", "Event-risk gate", "Cost completeness"],
                facts=[
                    f"Review state: {risk.state}; lifecycle: {risk.lifecycle_state}.",
                    f"Costs complete: {'yes' if risk.costs_complete else 'no'}; event risk clear: {'yes' if risk.event_risk_clear else 'no'}.",
                ], reason_codes=risk.reason_codes, evidence_count=0,
            ),
            ResearchBotReport(
                bot_id="postmortem", label="Strategy research & postmortem analyst", source="PYONTRADING2_LOCAL_AUDIT",
                data_status=DataStatus.LIVE, state="COLLECTING_EVIDENCE", updated_at_utc=now,
                summary="Versioned candidates are frozen and outcome-labelled later; no strategy self-promotes from recent outcomes.",
                skills=["Immutable decision snapshots", "Delayed outcomes", "Walk-forward review", "Manual promotion"],
                facts=["Candidate state is research-only.", "Actual fills remain separate and unavailable because no execution exists."],
                reason_codes=["CHRONOLOGICAL_LABELS_ONLY", "MANUAL_MODEL_PROMOTION", "NO_ORDER_EXECUTION"], evidence_count=0,
            ),
        ]

    @staticmethod
    def _momentum_bot(now: datetime, chart: ChartEvidence | None) -> ResearchBotReport:
        primary = chart.primary if chart else None
        indicators = primary.indicators if primary else None
        if not indicators:
            return ResearchBotReport(
                bot_id="momentum", label="Momentum analyst", source="MT5", data_status=DataStatus.HISTORY_INSUFFICIENT,
                state="BLOCKED", updated_at_utc=now,
                summary="Completed M5 indicator context is unavailable; momentum is not inferred.",
                skills=["EMA", "RSI", "MACD", "ADX", "ATR", "Disagreement detection"],
                reason_codes=["MOMENTUM_HISTORY_INSUFFICIENT"], evidence_count=0,
            )
        directional_parts = [
            "EMA+" if indicators.ema_20 is not None and indicators.ema_60 is not None and indicators.ema_20 > indicators.ema_60 else "EMA-",
            "MACD+" if (indicators.macd_histogram or 0) > 0 else "MACD-",
            "RSI+" if (indicators.rsi_14 or 50) >= 55 else "RSI-" if (indicators.rsi_14 or 50) <= 45 else "RSI neutral",
        ]
        return ResearchBotReport(
            bot_id="momentum", label="Momentum analyst", source="MT5", data_status=DataStatus.LIVE,
            state="OBSERVING", source_timestamp_utc=primary.source_timestamp_utc, updated_at_utc=now,
            summary="Completed M5 EMA, RSI, MACD, ADX and ATR context is measured; disagreements cause abstention.",
            skills=["EMA trend", "RSI", "MACD", "ADX", "ATR", "Disagreement detection"],
            facts=[
                f"Directional readings: {' / '.join(directional_parts)}.",
                f"ADX: {indicators.adx_14 if indicators.adx_14 is not None else 'unavailable'}; ATR: {indicators.atr_14 if indicators.atr_14 is not None else 'unavailable'}.",
                "Measurements use completed candles only; they are not a prediction.",
            ],
            reason_codes=["COMPLETED_CANDLES_ONLY", "MOMENTUM_DISAGREEMENT_CHECK", "DESCRIPTIVE_CONTEXT_ONLY"],
            evidence_count=0,
        )

    @staticmethod
    def _context_bot(now: datetime, features: list[object]) -> ResearchBotReport:
        configured = [item for item in features if getattr(item, "configured_symbol", None)]
        available = [item for item in configured if getattr(item, "data_status", None) == DataStatus.LIVE]
        status = DataStatus.LIVE if configured and len(available) == len(configured) else DataStatus.NOT_CONFIGURED if not configured else DataStatus.DELAYED
        return ResearchBotReport(
            bot_id="context", label="Cross-market context", source="MT5_CONFIGURED_CONTEXT", data_status=status,
            state="WATCHING" if configured else "OBSERVING", updated_at_utc=now,
            summary=(
                "Configured broker reference symbols are available as contextual features only."
                if configured else "DXY, yield, oil, and volatility context needs exact broker-symbol configuration."
            ),
            skills=["DXY context", "Yield context", "Oil context", "Volatility context", "Source labeling"],
            facts=[
                f"Configured features: {len(configured)}/4; live features: {len(available)}/4.",
                "Contextual features are not treated as causal certainty or an execution trigger.",
            ],
            reason_codes=["CONTEXT_ONLY_NOT_CAUSAL", "CROSS_MARKET_SYMBOLS_EXPLICIT_ONLY"], evidence_count=0,
        )

    def _strategy_ensemble(
        self,
        symbol: str | None,
        chart: ChartEvidence | None,
        quality: DataQualityReport,
        calendar_state: str,
    ) -> StrategyEnsemble:
        promotion = str(read_operations_status(self.database_path)["model_promotion_state"])
        if not chart:
            votes = self._abstaining_votes("MULTI_TIMEFRAME_EVIDENCE_UNAVAILABLE")
            return StrategyEnsemble(votes=votes, model_promotion_state=promotion, reason_codes=["MULTI_TIMEFRAME_EVIDENCE_UNAVAILABLE", "ENSEMBLE_ABSTENTION", "NO_ORDER_EXECUTION"])
        primary = chart.primary
        indicators = primary.indicators
        structure_decision = "WATCH_LONG" if chart.structure == "UPWARD_STRUCTURE" else "WATCH_SHORT" if chart.structure == "DOWNWARD_STRUCTURE" else "ABSTAIN"
        structure_reasons = ["MULTI_TIMEFRAME_STRUCTURE_ALIGNED"] if structure_decision != "ABSTAIN" else ["MULTI_TIMEFRAME_STRUCTURE_MIXED"]
        momentum_decision = "ABSTAIN"
        if indicators and indicators.ema_20 is not None and indicators.ema_60 is not None and indicators.rsi_14 is not None and indicators.macd_histogram is not None and indicators.adx_14 is not None:
            if indicators.ema_20 > indicators.ema_60 and indicators.rsi_14 >= 55 and indicators.macd_histogram > 0 and indicators.adx_14 >= 18:
                momentum_decision = "WATCH_LONG"
            elif indicators.ema_20 < indicators.ema_60 and indicators.rsi_14 <= 45 and indicators.macd_histogram < 0 and indicators.adx_14 >= 18:
                momentum_decision = "WATCH_SHORT"
        range_decision = "ABSTAIN"
        long_breakout = self._completed_close_breakout(primary.window, "WATCH_LONG")
        short_breakout = self._completed_close_breakout(primary.window, "WATCH_SHORT")
        if primary.close_location is not None and primary.net_change is not None and primary.average_range_20 is not None:
            if long_breakout and primary.close_location >= 60 and primary.recent_up_closes >= 12 and primary.net_change > primary.average_range_20:
                range_decision = "WATCH_LONG"
            elif short_breakout and primary.close_location <= 40 and primary.recent_down_closes >= 12 and abs(primary.net_change) > primary.average_range_20:
                range_decision = "WATCH_SHORT"
        range_reasons = ["COMPLETED_CANDLES_ONLY"]
        if range_decision != "ABSTAIN":
            range_reasons.append("COMPLETED_20_CLOSE_BREAKOUT")
        elif long_breakout or short_breakout:
            range_reasons.append("RANGE_CONTEXT_NOT_CONFIRMED")
        else:
            range_reasons.append("NO_COMPLETED_CLOSE_BREAKOUT")
        votes = [
            StrategyVote(strategy_id="STRUCTURE_ALIGNMENT", strategy_version="structure-alignment-v1", decision=structure_decision, reason_codes=structure_reasons + ["COMPLETED_CANDLES_ONLY"]),
            StrategyVote(strategy_id="MOMENTUM_ALIGNMENT", strategy_version="momentum-alignment-v1", decision=momentum_decision, reason_codes=["EMA_RSI_MACD_ADX_COMPLETED_CANDLES", "ABSTAIN_ON_DISAGREEMENT"]),
            StrategyVote(strategy_id="RANGE_BREAKOUT", strategy_version="range-breakout-v2", decision=range_decision, reason_codes=range_reasons),
        ]
        configured = read_strategy_settings(self.database_path, symbol=symbol)
        votes = [
            vote.model_copy(update={
                "decision": "ABSTAIN",
                "reason_codes": [*vote.reason_codes, "STRATEGY_DISABLED_BY_LOCAL_OWNER"],
            })
            if configured.get(vote.strategy_id, {}).get("enabled") is False else vote
            for vote in votes
        ]
        long_agreement = sum(vote.decision == "WATCH_LONG" for vote in votes)
        short_agreement = sum(vote.decision == "WATCH_SHORT" for vote in votes)
        event_clear = calendar_state not in {"HIGH_IMPACT_WINDOW", "ELEVATED_EVENT_WINDOW", "UNVERIFIED"}
        quality_blocks = quality.status == "BLOCK" or quality.spread_state == "ELEVATED"
        if quality_blocks or not event_clear:
            decision = "NO_TRADE"
            reason_codes = ["ABSTENTION_GATE_ACTIVE", "DATA_QUALITY_OR_EVENT_RISK_BLOCK", "NO_ORDER_EXECUTION"]
        elif long_agreement >= 2:
            decision = "WATCH_LONG"
            reason_codes = ["TWO_OR_MORE_DETERMINISTIC_RULES_AGREE", "UNVALIDATED_RESEARCH_SIGNAL", "NO_ORDER_EXECUTION"]
        elif short_agreement >= 2:
            decision = "WATCH_SHORT"
            reason_codes = ["TWO_OR_MORE_DETERMINISTIC_RULES_AGREE", "UNVALIDATED_RESEARCH_SIGNAL", "NO_ORDER_EXECUTION"]
        else:
            decision = "NO_TRADE"
            reason_codes = ["ENSEMBLE_DISAGREEMENT", "ABSTAIN_ON_CONFLICT", "NO_ORDER_EXECUTION"]
        if quality.status == "WATCH" and not quality_blocks:
            reason_codes.append("DATA_QUALITY_WATCH_NON_BLOCKING")
        if any("STRATEGY_DISABLED_BY_LOCAL_OWNER" in vote.reason_codes for vote in votes):
            reason_codes.append("LOCAL_STRATEGY_CONFIGURATION_APPLIED")
        return StrategyEnsemble(
            decision=decision, votes=votes, agreement_count=max(long_agreement, short_agreement),
            model_promotion_state=promotion if promotion in {"REVIEW_REQUIRED", "NOT_APPROVED"} else "REVIEW_REQUIRED",
            reason_codes=reason_codes,
        )

    @staticmethod
    def _abstaining_votes(reason: str) -> list[StrategyVote]:
        return [
            StrategyVote(strategy_id="STRUCTURE_ALIGNMENT", strategy_version="structure-alignment-v1", decision="ABSTAIN", reason_codes=[reason]),
            StrategyVote(strategy_id="MOMENTUM_ALIGNMENT", strategy_version="momentum-alignment-v1", decision="ABSTAIN", reason_codes=[reason]),
            StrategyVote(strategy_id="RANGE_BREAKOUT", strategy_version="range-breakout-v2", decision="ABSTAIN", reason_codes=[reason]),
        ]

    def _chart_bot(self, symbol: str | None, now: datetime) -> tuple[ResearchBotReport, Candle | None, ChartEvidence | None]:
        assessments = tuple(self._timeframe_assessment(symbol, spec, now=now) for spec in TIMEFRAME_SPECS)
        unavailable = next((assessment for assessment in assessments if assessment.data_status != DataStatus.LIVE), None)
        public_evidence = self._public_timeframe_evidence_from_assessments(assessments)

        if unavailable:
            facts = [
                (
                    f"{evidence.timeframe}: {evidence.completed_candles}/"
                    f"{evidence.required_completed_candles} completed ({evidence.window_label}) "
                    f"· {evidence.data_status.value}"
                )
                for evidence in public_evidence
            ]
            return (
                ResearchBotReport(
                    bot_id="chart", label="Chart analyst", source="MT5", data_status=unavailable.data_status,
                    state="BLOCKED", updated_at_utc=now,
                    summary=(
                        "Multi-timeframe broker context is incomplete; no directional research "
                        "condition can be evaluated."
                    ),
                    skills=["Completed-candle validation", "Multi-timeframe source checks"],
                    facts=facts,
                    reason_codes=list(unavailable.reason_codes) or ["MULTI_TIMEFRAME_WINDOW_INSUFFICIENT"],
                    evidence_count=0,
                ),
                None,
                ChartEvidence(structure="UNAVAILABLE", primary=assessments[0], timeframes=assessments),
            )

        structures = {assessment.structure for assessment in assessments}
        if structures == {"UPWARD_STRUCTURE"}:
            structure = "UPWARD_STRUCTURE"
            alignment = "bullish alignment"
        elif structures == {"DOWNWARD_STRUCTURE"}:
            structure = "DOWNWARD_STRUCTURE"
            alignment = "bearish alignment"
        else:
            structure = "MIXED_STRUCTURE"
            alignment = "mixed structure"

        primary = assessments[0]
        chart_evidence = ChartEvidence(structure=structure, primary=primary, timeframes=assessments)
        facts = [
            (
                f"{evidence.timeframe}: {evidence.structure.replace('_', ' ').title()} · "
                f"{evidence.completed_candles}/{evidence.required_completed_candles} completed "
                f"({evidence.window_label})"
            )
            for evidence in public_evidence
        ]
        return (
            ResearchBotReport(
                bot_id="chart", label="Chart analyst", source="MT5", data_status=DataStatus.LIVE,
                state="OBSERVING", source_timestamp_utc=self._conservative_source_timestamp(chart_evidence, None),
                updated_at_utc=now,
                summary=(
                    f"{alignment.title()} across completed MT5 M5, M15, H1 and H4 broker-candle windows."
                ),
                skills=[
                    "Completed-candle validation", "Multi-timeframe alignment", "Confirmed swing structure",
                    "BOS / CHOCH timing", "Fair value gap scan", "EMA trend", "RSI / ATR context",
                ],
                facts=facts,
                reason_codes=[
                    "MULTI_TIMEFRAME_COMPLETED_CANDLES_ONLY", "CONFIRMATION_TIMESTAMPS_RETAINED",
                    "DESCRIPTIVE_CONTEXT_ONLY", "NOT_A_TRADE_SIGNAL",
                ],
                evidence_count=count_research_evidence(self.database_path, symbol),
            ),
            primary.anchor,
            chart_evidence,
        )

    def _timeframe_assessment(self, symbol: str | None, spec: TimeframeSpec, *, now: datetime | None = None) -> TimeframeAssessment:
        requested_completed_candles = spec.required_completed_candles + spec.indicator_warmup_candles
        try:
            status, reasons, candles = self.adapter.candles(symbol, spec.timeframe, requested_completed_candles + 1)
        except Exception as error:
            return TimeframeAssessment(spec=spec, data_status=DataStatus.SOURCE_ERROR, reason_codes=("TIMEFRAME_READ_FAILED", type(error).__name__), completed_candles=0, source_timestamp_utc=None)
        completed = [candle for candle in candles if candle.completed]
        source_timestamp = completed[-1].open_time_utc + spec.duration if completed else None
        checked_at = now or datetime.now(UTC)
        forming = next((candle for candle in reversed(candles) if not candle.completed), None)
        prior_session_context = bool(
            source_timestamp and forming
            and source_timestamp <= forming.open_time_utc
            and forming.open_time_utc <= checked_at < forming.open_time_utc + spec.duration
            and spec.duration + timedelta(seconds=60) < checked_at - source_timestamp <= timedelta(days=3)
        )
        timing_reason = None
        if any(later.open_time_utc <= earlier.open_time_utc for earlier, later in zip(completed, completed[1:])):
            timing_reason = "DUPLICATE_OR_UNORDERED_TIMEFRAME"
        elif source_timestamp and source_timestamp > checked_at + timedelta(seconds=2):
            timing_reason = "FUTURE_COMPLETED_TIMEFRAME"
        elif source_timestamp and checked_at - source_timestamp > spec.duration + timedelta(seconds=60) and not prior_session_context:
            # A live tick does not establish that a broker history window is current.
            timing_reason = "STALE_COMPLETED_TIMEFRAME"
        if status == DataStatus.LIVE and timing_reason:
            return TimeframeAssessment(
                spec=spec, data_status=DataStatus.STALE if timing_reason == "STALE_COMPLETED_TIMEFRAME" else DataStatus.SOURCE_ERROR,
                reason_codes=(timing_reason, *reasons), completed_candles=len(completed),
                source_timestamp_utc=source_timestamp,
            )
        if prior_session_context:
            reasons = [*reasons, "PRIOR_BROKER_SESSION_CONTEXT"]
        if status != DataStatus.LIVE or len(completed) < spec.required_completed_candles:
            assessment_status = DataStatus.HISTORY_INSUFFICIENT if status == DataStatus.LIVE else status
            reason_codes = tuple(reasons) or ("MULTI_TIMEFRAME_WINDOW_INSUFFICIENT",)
            return TimeframeAssessment(
                spec=spec,
                data_status=assessment_status,
                reason_codes=reason_codes,
                completed_candles=min(len(completed), spec.required_completed_candles),
                source_timestamp_utc=source_timestamp,
                anchor=completed[-1] if completed else None,
            )

        if len(completed) < requested_completed_candles:
            return TimeframeAssessment(
                spec=spec,
                data_status=DataStatus.HISTORY_INSUFFICIENT,
                reason_codes=("INDICATOR_WARMUP_INSUFFICIENT", *reasons),
                completed_candles=spec.required_completed_candles,
                source_timestamp_utc=source_timestamp,
                anchor=completed[-1],
            )

        indicator_window = completed[-requested_completed_candles:]
        window = indicator_window[-spec.required_completed_candles:]
        closes = [candle.close for candle in window]
        average_20 = sum(closes[-20:]) / 20
        average_60 = sum(closes[-60:]) / 60
        latest = closes[-1]
        net_change = latest - closes[0]
        window_high = max(candle.high for candle in window)
        window_low = min(candle.low for candle in window)
        total_range = window_high - window_low
        close_location = ((latest - window_low) / total_range * 100) if total_range else 50.0
        recent_up_closes = sum(candle.close > candle.open for candle in window[-20:])
        recent_down_closes = sum(candle.close < candle.open for candle in window[-20:])
        average_range_20 = sum(candle.high - candle.low for candle in window[-20:]) / 20
        technical = analyze_completed_candles(indicator_window, spec.duration)
        latest_event = technical.structure_events[-1] if technical.structure_events else None
        active_gaps = sum(gap.invalidated_at is None for gap in technical.fair_value_gaps)
        close_breakout = self._completed_close_breakout(tuple(window), "WATCH_LONG" if net_change > 0 else "WATCH_SHORT")
        recent_break = latest_event if (
            latest_event and latest_event.direction == ("BULLISH" if net_change > 0 else "BEARISH")
            and timedelta(0) <= source_timestamp - latest_event.known_at <= spec.duration * 3
        ) else None
        setup_kind = recent_break.kind if recent_break else "COMPLETED_20_CLOSE_BREAKOUT" if close_breakout else None
        setup_known_at = recent_break.known_at if recent_break else source_timestamp if close_breakout else None
        prior = window[-21:-1]
        invalidation = min(bar.low for bar in prior) if net_change > 0 else max(bar.high for bar in prior)
        if latest > average_20 > average_60 and net_change > 0:
            structure = "UPWARD_STRUCTURE"
            moving_average_context = "close > MA20 > MA60"
        elif latest < average_20 < average_60 and net_change < 0:
            structure = "DOWNWARD_STRUCTURE"
            moving_average_context = "close < MA20 < MA60"
        else:
            structure = "MIXED_STRUCTURE"
            moving_average_context = "moving averages are not aligned"
        return TimeframeAssessment(
            spec=spec,
            data_status=DataStatus.LIVE,
            reason_codes=("COMPLETED_CANDLES_ONLY", *reasons),
            completed_candles=len(completed),
            source_timestamp_utc=window[-1].open_time_utc + spec.duration,
            anchor=window[-1],
            structure=structure,
            moving_average_context=moving_average_context,
            close_location=close_location,
            recent_up_closes=recent_up_closes,
            recent_down_closes=recent_down_closes,
            net_change=net_change,
            average_range_20=average_range_20,
            latest_break=f"{latest_event.direction} {latest_event.kind}" if latest_event else None,
            active_gaps=active_gaps,
            total_gaps=len(technical.fair_value_gaps),
            indicators=TechnicalIndicators(
                ema_20=technical.ema_20,
                ema_60=technical.ema_60,
                rsi_14=technical.rsi_14,
                atr_14=technical.atr_14,
                macd_histogram=technical.macd_histogram,
                adx_14=technical.adx_14,
                range_position_percent=close_location,
                latest_structure_event=f"{latest_event.direction} {latest_event.kind}" if latest_event else None,
                active_fair_value_gaps=active_gaps,
            ),
            window=tuple(window),
            setup_kind=setup_kind,
            setup_known_at_utc=setup_known_at,
            invalidation_price=invalidation if setup_kind else None,
        )

    @staticmethod
    def _public_timeframe_evidence(chart: ChartEvidence | None) -> list[TimeframeEvidence]:
        return ResearchCoordinator._public_timeframe_evidence_from_assessments(chart.timeframes if chart else ())

    @staticmethod
    def _public_timeframe_evidence_from_assessments(
        assessments: tuple[TimeframeAssessment, ...],
    ) -> list[TimeframeEvidence]:
        return [
            TimeframeEvidence(
                timeframe=assessment.spec.timeframe,
                window_label=assessment.spec.window_label,
                required_completed_candles=assessment.spec.required_completed_candles,
                completed_candles=assessment.completed_candles,
                data_status=assessment.data_status,
                source_timestamp_utc=assessment.source_timestamp_utc,
                structure=assessment.structure,
                indicators=assessment.indicators,
                reason_codes=list(assessment.reason_codes),
                setup_kind=assessment.setup_kind,
                setup_known_at_utc=assessment.setup_known_at_utc,
                invalidation_price=assessment.invalidation_price,
            )
            for assessment in assessments
        ]

    @staticmethod
    def _conservative_source_timestamp(
        chart: ChartEvidence | None,
        fallback: datetime | None,
    ) -> datetime | None:
        timestamps = [
            assessment.source_timestamp_utc
            for assessment in chart.timeframes
            if assessment.source_timestamp_utc is not None
        ] if chart else []
        return min(timestamps) if timestamps else fallback

    def _calendar_bot(
        self,
        now: datetime,
        calendar_response: EventsResponse | None = None,
        macro_sources: list[object] | None = None,
    ) -> tuple[ResearchBotReport, str]:
        calendar = calendar_response or self.calendar.upcoming_usd_events()
        macro_facts = [
            f"Official {getattr(item, 'provider', 'source')}: {getattr(item, 'data_status', DataStatus.SOURCE_ERROR).value}."
            for item in (macro_sources or [])
        ]
        risk_events = [event for event in [*calendar.risk_events, *calendar.events] if
                       (event.impact == "High" and -timedelta(minutes=30) <= event.event_time_utc - now <= timedelta(hours=2))
                       or (event.impact == "Medium" and -timedelta(minutes=15) <= event.event_time_utc - now <= timedelta(hours=1))]
        next_event = min(risk_events, key=lambda event: (event.impact != "High", abs((event.event_time_utc - now).total_seconds()))) if risk_events else min(calendar.events, key=lambda event: event.event_time_utc, default=None)
        if calendar.data_status not in {DataStatus.LIVE, DataStatus.DELAYED}:
            return (
                ResearchBotReport(
                    bot_id="calendar", label="Macro & event watcher", source=calendar.source, source_url=calendar.source_url,
                    data_status=calendar.data_status, state="BLOCKED", updated_at_utc=now,
                    summary="USD calendar data is unavailable; news risk remains unverified.",
                    skills=["Calendar freshness", "Official schedule provenance", "Event-risk screening"],
                    facts=macro_facts,
                    reason_codes=calendar.reason_codes or ["NEWS_CHECK_UNVERIFIED"], evidence_count=0,
                ),
                "UNVERIFIED",
            )
        if not next_event:
            return (
                ResearchBotReport(
                    bot_id="calendar", label="Macro & event watcher", source=calendar.source, source_url=calendar.source_url,
                    data_status=calendar.data_status, state="WATCHING", updated_at_utc=now,
                    summary="No future USD item appears in the provider's current weekly export.",
                    skills=["Calendar freshness", "Event impact", "PHT event schedule"],
                    facts=["This does not prove there is no news risk.", *macro_facts], reason_codes=calendar.reason_codes, evidence_count=0,
                ),
                "NO_EVENT_IN_EXPORT",
            )
        signed_minutes = int((next_event.event_time_utc - now).total_seconds() // 60)
        minutes_until = max(signed_minutes, 0)
        if next_event.impact == "High" and minutes_until <= 120:
            calendar_state = "HIGH_IMPACT_WINDOW"
            horizon = "High-impact event is within two hours"
        elif next_event.impact in {"High", "Medium"} and minutes_until <= 60:
            calendar_state = "ELEVATED_EVENT_WINDOW"
            horizon = f"{next_event.impact}-impact event is within one hour"
        else:
            calendar_state = "UPCOMING_USD_EVENT"
            horizon = "Upcoming event is outside the elevated-risk window"
        if signed_minutes < 0:
            horizon = f"{next_event.impact}-impact scheduled release is in its post-event cooling window"
        event_values = [
            f"Risk horizon: {horizon}",
            f"{'Occurred approximately' if signed_minutes < 0 else 'Due in approximately'} {abs(signed_minutes)} minutes{' ago' if signed_minutes < 0 else ''} ({next_event.event_time_manila.strftime('%b %d %I:%M %p PHT')})",
            "Public-calendar values are informational; official schedules are retained separately.",
            *macro_facts,
        ]
        if next_event.forecast or next_event.previous or next_event.actual:
            event_values.append(f"Forecast: {next_event.forecast or '—'}; previous: {next_event.previous or '—'}; actual: {next_event.actual or 'pending'}")
        return (
            ResearchBotReport(
                bot_id="calendar", label="Macro & event watcher", source=calendar.source, source_url=calendar.source_url,
                data_status=calendar.data_status, state="WATCHING", source_timestamp_utc=calendar.source_timestamp_utc, updated_at_utc=now,
                summary=f"{'Recent' if signed_minutes < 0 else 'Next risk-relevant'} USD event: {next_event.title} ({next_event.impact} impact); {horizon.lower()}.",
                skills=["Calendar freshness", "Event impact", "PHT event schedule"],
                facts=event_values,
                reason_codes=calendar.reason_codes, evidence_count=0,
            ),
            calendar_state,
        )

    @staticmethod
    def _strategy_bot(
        now: datetime,
        chart: ResearchBotReport,
        calendar: ResearchBotReport,
        quality: ResearchBotReport,
        ensemble: StrategyEnsemble,
        evidence_count: int,
    ) -> ResearchBotReport:
        status = DataStatus.LIVE if chart.data_status == DataStatus.LIVE else chart.data_status
        blocked = chart.state == "BLOCKED" or calendar.state == "BLOCKED" or quality.state == "BLOCKED"
        inputs = f"quality={quality.state.lower()}, chart={chart.state.lower()}, calendar={calendar.state.lower()}"
        summary = (
            "Validation is blocked because a required evidence source is unavailable."
            if blocked
            else "Versioned deterministic rules vote independently; confidence remains withheld pending chronological validation and manual review."
        )
        return ResearchBotReport(
            bot_id="strategy", label="Strategy ensemble & abstention", source="PYONTRADING2", data_status=status,
            state="BLOCKED" if blocked else "COLLECTING_EVIDENCE", updated_at_utc=now,
            summary=summary,
            skills=["Independent rule votes", "Abstention gate", "Walk-forward tracking", "Manual promotion"],
            facts=[
                f"Connected inputs: {inputs}",
                f"Stored completed-window observations: {evidence_count}",
                f"Current ensemble: {ensemble.decision}; agreement: {ensemble.agreement_count}/{ensemble.required_agreement_count}.",
                "Decision state: confidence withheld; no order instruction is issued.",
            ],
            reason_codes=[*ensemble.reason_codes, "OUT_OF_SAMPLE_VALIDATION_REQUIRED", "NO_CONFIDENCE_SCORE", "NO_ORDER_EXECUTION"], evidence_count=evidence_count,
        )
