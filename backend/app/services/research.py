from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.analysis.quality import assess_data_quality, classify_session_and_regime
from app.analysis.professional import professional_research
from app.analysis.technical import analyze_completed_candles
from app.adapters.calendar import ForexFactoryCalendarAdapter
from app.adapters.official_macro import OfficialMacroScheduleAdapter
from app.adapters.mt5 import MT5Adapter
from app.schemas.market import Candle, DataQualityReport, DataStatus, EventsResponse, LiveResearchWatchResponse, MarketAnalysisResponse, MarketDepthReport, OperationsStatus, PaperTradingReport, ProfessionalResearchReport, ResearchBotReport, ResearchResponse, StrategyEnsemble, StrategyVote, TechnicalIndicators, TimeframeEvidence
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


# Every window has enough completed candles for the MA60 context and the
# technical helpers. MT5 returns one additional forming candle.
TIMEFRAME_SPECS = (
    TimeframeSpec("M5", timedelta(minutes=5), 144, "12h"),
    TimeframeSpec("M15", timedelta(minutes=15), 96, "24h"),
    TimeframeSpec("H1", timedelta(hours=1), 72, "3d"),
    TimeframeSpec("H4", timedelta(hours=4), 60, "10d"),
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
    ) -> ResearchResponse:
        now = datetime.now(UTC)
        quote = self.adapter.quote(symbol)
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

        broker_ready = chart_bot.data_status == DataStatus.LIVE and chart_bot.state != "BLOCKED" and quality.status != "BLOCK"
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
            data_status=DataStatus.LIVE if broker_ready else chart_bot.data_status,
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
        return research.model_copy(update={
            "live_research_watch": self._build_live_research_watch(
                research,
                self._research_gates(quote, chart_bot, chart_evidence, calendar_bot, calendar_state, quality, professional),
            ),
        })

    def analyze_market(self, symbol: str | None) -> MarketAnalysisResponse:
        """Run the versioned research screen against fresh, source-backed inputs.

        This is intentionally a watchlist screen, not execution logic. It never
        produces price levels, sizing, or an order instruction.
        """
        now = datetime.now(UTC)
        quote = self.adapter.quote(symbol)
        chart_bot, anchor, chart = self._chart_bot(symbol, now)
        macro_sources = self.official_macro.snapshot() if self.official_macro else []
        calendar_bot, calendar_state = self._calendar_bot(now, macro_sources=macro_sources)
        primary_window = list(chart.primary.window) if chart else []
        quality = assess_data_quality(quote, primary_window, timeframe=TIMEFRAME_SPECS[0].duration, now=now)
        quality = self._with_session_transition(symbol, quality)
        regime = classify_session_and_regime(
            primary_window,
            structure=chart.structure if chart else "UNAVAILABLE",
            spread_state=quality.spread_state,
            now=now,
        )
        ensemble = self._strategy_ensemble(symbol, chart, quality, calendar_state)
        context = self.cross_market.snapshot() if self.cross_market else []
        professional = self._professional_analysis(
            symbol, quote, primary_window, calendar_state,
            cross_market_available=any(item.data_status == DataStatus.LIVE for item in context),
            data_quality=quality,
        )

        quote_live = quote.data_status == DataStatus.LIVE
        chart_ready = chart is not None and chart_bot.data_status == DataStatus.LIVE
        calendar_live = calendar_bot.data_status == DataStatus.LIVE
        integrity_eligible = quality.status != "BLOCK" and quality.spread_state != "ELEVATED"
        event_risk_clear = calendar_state not in {"HIGH_IMPACT_WINDOW", "ELEVATED_EVENT_WINDOW", "UNVERIFIED"}
        gates = self._research_gates(quote, chart_bot, chart, calendar_bot, calendar_state, quality, professional)
        facts = [
            f"Chart bot: {chart_bot.summary}",
            f"News bot: {calendar_bot.summary}",
            f"Session/regime: {regime.session_label} / {regime.market_regime} / {regime.volatility_regime}.",
            "Screen: completed candles and current source status only; no execution logic.",
        ]
        status = quote.data_status if not quote_live else (chart_bot.data_status if not chart_ready else calendar_bot.data_status)
        source_timestamp = self._conservative_source_timestamp(chart, quote.source_timestamp_utc)

        risk_reviewable = professional.risk_engine.state == "REVIEW_REQUIRED"
        if not (quote_live and integrity_eligible and chart_ready and calendar_live and event_risk_clear and risk_reviewable):
            reasons = ["RESEARCH_SCREEN_GATES_NOT_MET", "NO_ORDER_EXECUTION"]
            return MarketAnalysisResponse(
                observed_at_utc=now, source_timestamp_utc=source_timestamp, data_status=status,
                reason_codes=reasons, symbol=symbol, market_context=chart.structure if chart else "UNAVAILABLE",
                summary="No trade: one or more live-source, completed multi-timeframe, or event-risk gates are not clear.",
                gates=gates, analysis_timeframes=self._public_timeframe_evidence(chart), supporting_facts=facts,
                data_quality=quality, session_regime=regime, cross_market=context,
                official_macro_sources=macro_sources, event_risk_state=calendar_state,
                strategy_ensemble=ensemble, professional_analysis=professional,
                paper_trading=PaperTradingReport(
                    reason_codes=["BACKGROUND_COMPLETED_CANDLE_CYCLE_REQUIRED", "NO_ORDER_EXECUTION"],
                ),
            )

        primary = chart.primary
        decision = ensemble.decision
        quality_note = " A data-quality watch remains visible in this research result." if quality.status == "WATCH" else ""
        if decision == "WATCH_LONG":
            summary = "Watch-long research condition: independent completed-candle structure and momentum rules agree. This is not an execution instruction." + quality_note
            reasons = ["RESEARCH_SCREEN_V4_PROFESSIONAL_MODULES", "WATCH_CONDITION_MET", "UNVALIDATED_RESEARCH_SIGNAL", "NO_ORDER_EXECUTION"]
        elif decision == "WATCH_SHORT":
            summary = "Watch-short research condition: independent completed-candle structure and momentum rules agree. This is not an execution instruction." + quality_note
            reasons = ["RESEARCH_SCREEN_V4_PROFESSIONAL_MODULES", "WATCH_CONDITION_MET", "UNVALIDATED_RESEARCH_SIGNAL", "NO_ORDER_EXECUTION"]
        else:
            summary = "No trade: the independent deterministic rules do not reach the required agreement, or validation remains incomplete."
            reasons = ["RESEARCH_SCREEN_V4_PROFESSIONAL_MODULES", "ENSEMBLE_ABSTENTION", "NO_ORDER_EXECUTION"]

        facts.extend([
            f"Multi-timeframe structure: {chart.structure.replace('_', ' ').title()}",
            (
                f"M5 range position: {primary.close_location:.0f}%; recent up/down closes: "
                f"{primary.recent_up_closes}/{primary.recent_down_closes}"
            ),
            f"M5 moving-average context: {primary.moving_average_context}",
        ])
        return MarketAnalysisResponse(
            observed_at_utc=now, source_timestamp_utc=source_timestamp, data_status=DataStatus.LIVE,
            reason_codes=reasons, symbol=symbol, decision=decision, market_context=chart.structure,
            summary=summary, gates=gates, analysis_timeframes=self._public_timeframe_evidence(chart), supporting_facts=facts,
            data_quality=quality, session_regime=regime, cross_market=context,
            official_macro_sources=macro_sources, event_risk_state=calendar_state,
            strategy_ensemble=ensemble, professional_analysis=professional,
            paper_trading=PaperTradingReport(
                expected_spread_points=quote.spread_points,
                reason_codes=["BACKGROUND_COMPLETED_CANDLE_CYCLE_REQUIRED", "COMMISSION_UNAVAILABLE", "SLIPPAGE_UNAVAILABLE", "NO_ORDER_EXECUTION"],
            ),
        )

    def live_research_watch(self, symbol: str | None) -> LiveResearchWatchResponse:
        """Return the current automatic research-watch lifecycle without persisting a user review.

        The decision is recalculated from current source status and completed
        candles.  It intentionally exposes no entry, target, stop, sizing, or
        probability because this workstation is research-only and the rules
        have not been promoted through chronological validation.
        """
        research = self.snapshot(symbol, persist_evidence=False)
        if research.live_research_watch is not None:
            return research.live_research_watch
        return self._build_live_research_watch(research, [])

    def _build_live_research_watch(
        self,
        research: ResearchResponse,
        gates: list[dict[str, str]],
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

        if not has_live_sources:
            lifecycle = "UNAVAILABLE"
        elif expired:
            lifecycle = "EXPIRED"
        elif ensemble and ensemble.decision in {"WATCH_LONG", "WATCH_SHORT"}:
            lifecycle = "ACTIVE_RESEARCH_WATCH"
        else:
            lifecycle = "WITHHELD"

        blocked_gates = [
            f"{gate['label']}: {gate['reason']}"
            for gate in gates
            if gate["state"] == "BLOCK"
        ]
        score = self._watch_evidence_score_from_research(research)
        horizon, horizon_basis, horizon_review_at, horizon_reason_codes = self._research_horizon(
            research,
            lifecycle=lifecycle,
            direction=direction,
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
            summary = "Automatic research watch is withheld because the independent rules or safety gates do not currently support a directional research watch."
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
            active_from_utc=m5.source_timestamp_utc if m5 else None,
            scheduled_review_at_utc=scheduled_review_at,
            expires_at_utc=scheduled_review_at,
            summary=summary,
            invalidation_conditions=invalidation_conditions,
            gates=gates,
            analysis_timeframes=research.analysis_timeframes,
            data_quality=research.data_quality,
            event_risk_state=research.event_risk_state,
            strategy_ensemble=ensemble,
        )

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
        if primary.close_location is not None and primary.net_change is not None and primary.average_range_20 is not None:
            if primary.close_location >= 60 and primary.recent_up_closes >= 12 and primary.net_change > primary.average_range_20:
                range_decision = "WATCH_LONG"
            elif primary.close_location <= 40 and primary.recent_down_closes >= 12 and abs(primary.net_change) > primary.average_range_20:
                range_decision = "WATCH_SHORT"
        votes = [
            StrategyVote(strategy_id="STRUCTURE_ALIGNMENT", strategy_version="structure-alignment-v1", decision=structure_decision, reason_codes=structure_reasons + ["COMPLETED_CANDLES_ONLY"]),
            StrategyVote(strategy_id="MOMENTUM_ALIGNMENT", strategy_version="momentum-alignment-v1", decision=momentum_decision, reason_codes=["EMA_RSI_MACD_ADX_COMPLETED_CANDLES", "ABSTAIN_ON_DISAGREEMENT"]),
            StrategyVote(strategy_id="RANGE_BREAKOUT", strategy_version="range-breakout-v1", decision=range_decision, reason_codes=["COMPLETED_CANDLES_ONLY", "ABSTAIN_ON_INCOMPLETE_RANGE_CONTEXT"]),
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
            reason_codes = ["TWO_OR_MORE_INDEPENDENT_RULES_AGREE", "UNVALIDATED_RESEARCH_SIGNAL", "NO_ORDER_EXECUTION"]
        elif short_agreement >= 2:
            decision = "WATCH_SHORT"
            reason_codes = ["TWO_OR_MORE_INDEPENDENT_RULES_AGREE", "UNVALIDATED_RESEARCH_SIGNAL", "NO_ORDER_EXECUTION"]
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
            StrategyVote(strategy_id="RANGE_BREAKOUT", strategy_version="range-breakout-v1", decision="ABSTAIN", reason_codes=[reason]),
        ]

    def _chart_bot(self, symbol: str | None, now: datetime) -> tuple[ResearchBotReport, Candle | None, ChartEvidence | None]:
        assessments = tuple(self._timeframe_assessment(symbol, spec) for spec in TIMEFRAME_SPECS)
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

    def _timeframe_assessment(self, symbol: str | None, spec: TimeframeSpec) -> TimeframeAssessment:
        status, reasons, candles = self.adapter.candles(symbol, spec.timeframe, spec.required_completed_candles + 1)
        completed = sorted((candle for candle in candles if candle.completed), key=lambda candle: candle.open_time_utc)
        source_timestamp = completed[-1].open_time_utc + spec.duration if completed else None
        if status != DataStatus.LIVE or len(completed) < spec.required_completed_candles:
            assessment_status = DataStatus.HISTORY_INSUFFICIENT if status == DataStatus.LIVE else status
            reason_codes = tuple(reasons) or ("MULTI_TIMEFRAME_WINDOW_INSUFFICIENT",)
            return TimeframeAssessment(
                spec=spec,
                data_status=assessment_status,
                reason_codes=reason_codes,
                completed_candles=len(completed),
                source_timestamp_utc=source_timestamp,
                anchor=completed[-1] if completed else None,
            )

        window = completed[-spec.required_completed_candles:]
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
        technical = analyze_completed_candles(window, spec.duration)
        latest_event = technical.structure_events[-1] if technical.structure_events else None
        active_gaps = sum(gap.invalidated_at is None for gap in technical.fair_value_gaps)
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
        next_event = calendar.events[0] if calendar.events else None
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
        minutes_until = max(int((next_event.event_time_utc - now).total_seconds() // 60), 0)
        if next_event.impact == "High" and minutes_until <= 120:
            calendar_state = "HIGH_IMPACT_WINDOW"
            horizon = "High-impact event is within two hours"
        elif next_event.impact in {"High", "Medium"} and minutes_until <= 60:
            calendar_state = "ELEVATED_EVENT_WINDOW"
            horizon = f"{next_event.impact}-impact event is within one hour"
        else:
            calendar_state = "UPCOMING_USD_EVENT"
            horizon = "Upcoming event is outside the elevated-risk window"
        event_values = [
            f"Risk horizon: {horizon}",
            f"Due in approximately {minutes_until} minutes ({next_event.event_time_manila.strftime('%b %d %I:%M %p PHT')})",
            "Public-calendar values are informational; official schedules are retained separately.",
            *macro_facts,
        ]
        if next_event.forecast or next_event.previous or next_event.actual:
            event_values.append(f"Forecast: {next_event.forecast or '—'}; previous: {next_event.previous or '—'}; actual: {next_event.actual or 'pending'}")
        return (
            ResearchBotReport(
                bot_id="calendar", label="Macro & event watcher", source=calendar.source, source_url=calendar.source_url,
                data_status=calendar.data_status, state="WATCHING", source_timestamp_utc=calendar.source_timestamp_utc, updated_at_utc=now,
                summary=f"Next USD event: {next_event.title} ({next_event.impact} impact); {horizon.lower()}.",
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
