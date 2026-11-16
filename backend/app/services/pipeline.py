from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import perf_counter
from typing import Callable
from uuid import uuid4

from app.adapters.calendar import ForexFactoryCalendarAdapter
from app.adapters.official_macro import OfficialMacroScheduleAdapter
from app.adapters.mt5 import MT5Adapter
from app.analysis.training import MIN_TRAINING_CANDLES, calibrate_strategies
from app.config import settings
from app.schemas.market import Candle, DataStatus, QuoteResponse
from app.services.research import AUXILIARY_TIMEFRAME_SPECS, ResearchCoordinator, TIMEFRAME_SPECS
from app.schemas.market import WalkForwardStrategyResult
from app.storage.database import (
    PAPER_OUTCOME_LABEL_VERSION,
    claim_next_research_job,
    complete_research_job,
    count_completed_candles,
    enqueue_research_job,
    fail_research_job,
    invalidate_research_job,
    read_completed_candles,
    read_operations_status,
    read_pipeline_summary,
    read_research_coverage,
    read_pending_signal_followups,
    read_unlabelled_research_runs,
    record_calendar_snapshot,
    record_model_version,
    record_outcome_label,
    record_frozen_research_decision,
    record_research_run,
    record_signal_history,
    record_signal_followup,
    record_strategy_journal_events,
    recover_interrupted_research_jobs,
    store_completed_candles,
    write_operation_control,
    label_mature_frozen_decisions,
)


FEATURE_SET_VERSION = "mtf-research-v7-top-down-confirmation"
OUTCOME_LABEL_VERSION = "m5-close-direction-v2-contiguous"
OUTCOME_HORIZON_BARS = 12
RESEARCH_JOB_TYPE = "RESEARCH_SNAPSHOT_V2_TIMESTAMP_NORMALIZED"
M5_HISTORY_BOOTSTRAP_LIMIT = 30_001
LABEL_BACKFILL_ARCHIVE_LIMIT = 50_000
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ArchiveSpec:
    timeframe: str
    seconds: int
    bootstrap_limit: int
    minimum_for_calibration: int = 0


ARCHIVE_SPECS = (
    # Enough M5 bars to request roughly 90 calendar days of trading history when the broker retains it.
    # The archive coverage service still checks the actual returned time span before enabling walk-forward readiness.
    ArchiveSpec("M5", 300, M5_HISTORY_BOOTSTRAP_LIMIT, MIN_TRAINING_CANDLES),
    ArchiveSpec("M15", 900, 2_001),
    ArchiveSpec("H1", 3_600, 1_001),
    ArchiveSpec("H4", 14_400, 601),
    ArchiveSpec("D1", 86_400, 401),
    ArchiveSpec("M1", 60, 2_001),
)


class ResearchPipeline:
    """Durable, read-only researchers that operate independently from HTTP requests.

    The workers never submit trades, never promote a calibration automatically,
    and only save completed broker bars. Every cross-bot review is queued from
    a newly observed completed M5 bar and can be recovered after a restart.
    """

    def __init__(
        self,
        adapter: MT5Adapter,
        calendar: ForexFactoryCalendarAdapter,
        coordinator: ResearchCoordinator,
        database_path: Path,
        configured_symbol: Callable[[], str | None],
        official_macro: OfficialMacroScheduleAdapter | None = None,
    ) -> None:
        self.adapter = adapter
        self.calendar = calendar
        self.coordinator = coordinator
        self.database_path = database_path
        self.configured_symbol = configured_symbol
        self.official_macro = official_macro
        self._task: asyncio.Task[None] | None = None
        self._started_at_utc: datetime | None = None
        self._last_cycle_at_utc: datetime | None = None
        self._last_error: str | None = None
        self._last_bootstrap_at: dict[str, datetime] = {}
        self._last_calibration_at: dict[str, datetime] = {}
        self._label_backfilled_sources: set[tuple[str, str]] = set()
        self._broker_servers: dict[str, str] = {}
        self._last_connection_status: str | None = None
        self._last_market_data_status: str | None = None
        self._last_quote_source_timestamp_utc: datetime | None = None
        self._worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pyon-research")
        self._cycle_future: asyncio.Future[None] | None = None
        self._cycle_started_monotonic: float | None = None
        self._last_cycle_duration_ms: float | None = None
        self._last_quote_latency_ms: float | None = None
        self._last_m5_collection_latency_ms: float | None = None
        self._event_loop_lag_ms: float | None = None
        self._worker_failures = 0
        self._retry_delay_seconds = settings.research_poll_seconds
        self._control_changed = asyncio.Event()
        self._macro_worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pyon-official-schedules")
        self._macro_future: Future | None = None
        self._macro_error: str | None = None

    async def start(self) -> None:
        recover_interrupted_research_jobs(self.database_path)
        self._started_at_utc = datetime.now(UTC)
        self._task = asyncio.create_task(self._poll(), name="research-worker-pipeline")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        self._worker.shutdown(wait=False, cancel_futures=True)
        self._macro_worker.shutdown(wait=False, cancel_futures=True)

    async def _poll(self) -> None:
        loop = asyncio.get_running_loop()
        scheduled_at = loop.time()
        while True:
            self._control_changed.clear()
            try:
                enabled = self._enabled()
            except Exception as error:
                # A failed control-store read must stop new work, not kill the worker.
                self._last_error = type(error).__name__
                self._worker_failures += 1
                try:
                    await asyncio.wait_for(self._control_changed.wait(), timeout=self._retry_delay_seconds)
                except TimeoutError:
                    pass
                continue
            if not enabled:
                await self._control_changed.wait()
                scheduled_at = loop.time()
                continue
            self._event_loop_lag_ms = max(0.0, (loop.time() - scheduled_at) * 1_000)
            completed = await self._run_cycle()
            self._last_cycle_at_utc = datetime.now(UTC)
            if completed:
                self._retry_delay_seconds = settings.research_poll_seconds
            else:
                self._retry_delay_seconds = min(
                    max(settings.research_poll_seconds, self._retry_delay_seconds * 2),
                    settings.research_retry_max_seconds,
                )
            scheduled_at = loop.time() + self._retry_delay_seconds
            try:
                await asyncio.wait_for(self._control_changed.wait(), timeout=self._retry_delay_seconds)
            except TimeoutError:
                pass

    async def _run_cycle(self) -> bool:
        """Run a synchronous research cycle on one worker without blocking the event loop.

        If a cycle outlives its bounded wait, the next poll records backpressure
        instead of launching another adapter/database cycle concurrently.
        """
        loop = asyncio.get_running_loop()
        active = self._cycle_future
        if active and not active.done():
            self._last_error = "RESEARCH_CYCLE_BACKPRESSURE"
            return False
        if active and active.done():
            try:
                active.result()
            except Exception as error:
                self._last_error = type(error).__name__
                self._worker_failures += 1
                self._cycle_future = None
                return False
            self._cycle_future = None

        self._cycle_started_monotonic = loop.time()
        future = loop.run_in_executor(self._worker, self.run_once)
        self._cycle_future = future
        try:
            await asyncio.wait_for(asyncio.shield(future), timeout=settings.research_cycle_timeout_seconds)
        except TimeoutError:
            self._last_error = "RESEARCH_CYCLE_TIMEOUT"
            self._worker_failures += 1
            return False
        except Exception as error:  # retain an observable failure and keep workers available
            logger.exception("Research cycle failed")
            self._last_error = type(error).__name__
            self._worker_failures += 1
            self._cycle_future = None
            return False
        finally:
            if future.done() and self._cycle_started_monotonic is not None:
                self._last_cycle_duration_ms = (loop.time() - self._cycle_started_monotonic) * 1_000
        self._last_error = None
        self._cycle_future = None
        return True

    def run_once(self) -> None:
        """Run one bounded collection/research/label/calibration cycle for tests and the worker."""
        if not self._enabled():
            return
        symbol = self.configured_symbol()
        if not symbol:
            return
        now = datetime.now(UTC)
        self._schedule_optional_macro_refresh()
        broker_server = self._broker_server(symbol)
        quote_started = perf_counter()
        quote = self.adapter.quote(symbol)
        self._last_quote_latency_ms = (perf_counter() - quote_started) * 1_000
        self._last_market_data_status = quote.data_status.value
        self._last_quote_source_timestamp_utc = quote.source_timestamp_utc
        if quote.data_status != DataStatus.LIVE:
            self._label_mature_runs(symbol, broker_server, now)
            self._calibrate_if_due(symbol, broker_server, quote, now)
            return
        self._bootstrap_history_if_due(symbol, broker_server, now)
        collection_started = perf_counter()
        latest_m5 = self._collect_recent_completed_candles(symbol, broker_server, now)
        self._last_m5_collection_latency_ms = (perf_counter() - collection_started) * 1_000
        if latest_m5 is not None:
            enqueue_research_job(
                self.database_path,
                job_id=str(uuid4()),
                job_type=RESEARCH_JOB_TYPE,
                symbol=symbol,
                anchor_time_utc=latest_m5.open_time_utc,
                created_at_utc=now,
                payload={
                    "feature_set_version": FEATURE_SET_VERSION,
                    "source": "MT5",
                    "broker_server": broker_server,
                    "timeframes": [spec.timeframe for spec in TIMEFRAME_SPECS],
                },
            )
        if latest_m5 is not None:
            job = claim_next_research_job(self.database_path)
            if job:
                if (
                    job["symbol"] != symbol
                    or job["anchor_time_utc"] != latest_m5.open_time_utc
                    or job["payload"].get("broker_server", broker_server) != broker_server
                ):
                    invalidate_research_job(
                        self.database_path, job_id=str(job["job_id"]),
                        reason_codes=["ASOF_CANDLE_MISMATCH", "HISTORICAL_REPLAY_NOT_AVAILABLE"],
                    )
                else:
                    self._run_research_job(job, now, quote)
        self._label_mature_runs(symbol, broker_server, now)
        self._calibrate_if_due(symbol, broker_server, quote, now)

    def _schedule_optional_macro_refresh(self) -> None:
        if not self.official_macro or self._macro_future and not self._macro_future.done():
            return
        if self._macro_future:
            try:
                self._macro_future.result()
                self._macro_error = None
            except Exception as error:
                self._macro_error = type(error).__name__
        self._macro_future = self._macro_worker.submit(self.official_macro.refresh_if_due)

    def status(self) -> dict[str, object]:
        symbol = self.configured_symbol()
        persisted = read_pipeline_summary(self.database_path, symbol=symbol)
        coverage = read_research_coverage(
            self.database_path, symbol=symbol,
            broker_server=self._broker_servers.get(symbol, "") if symbol else None,
        )
        latest_bar_text = coverage["latest_completed_m5_open_utc"]
        latest_bar_open = datetime.fromisoformat(latest_bar_text) if latest_bar_text else None
        if self._last_market_data_status and self._last_market_data_status != DataStatus.LIVE.value:
            coverage["state"] = "SOURCE_UNAVAILABLE"
        elif (
            coverage["state"] in {"CURRENT", "CURRENT_WITH_GAPS"}
            and latest_bar_open is not None
            and self._last_quote_source_timestamp_utc is not None
            and self._last_quote_source_timestamp_utc >= latest_bar_open + 2 * TIMEFRAME_SPECS[0].duration
        ):
            coverage["state"] = "BAR_LAGGING"
        enabled = self._enabled()
        process_state = "RUNNING" if self._task and not self._task.done() else "STOPPED"
        if process_state == "RUNNING" and not enabled:
            process_state = "PAUSING" if self._cycle_future and not self._cycle_future.done() else "PAUSED"
        worker_health = process_state
        if process_state == "RUNNING":
            last_heartbeat = self._last_cycle_at_utc or self._started_at_utc
            stale_after = max(
                2 * settings.research_poll_seconds,
                settings.research_retry_max_seconds + settings.research_cycle_timeout_seconds,
            )
            if self._last_error:
                worker_health = "ERROR"
            elif last_heartbeat and (datetime.now(UTC) - last_heartbeat).total_seconds() > stale_after:
                worker_health = "STALE"
            else:
                worker_health = "RUNNING" if self._last_cycle_at_utc else "STARTING"
        coverage["worker_health"] = worker_health
        coverage["publication_state"] = (
            "CHECK_PROOF"
            if worker_health == "RUNNING" and self._last_market_data_status == DataStatus.LIVE.value
            and coverage["state"] in {"CURRENT", "CURRENT_WITH_GAPS"}
            else "BLOCKED"
        )
        worker_state = (
            process_state if process_state in {"PAUSED", "PAUSING", "STOPPED"}
            else "WAITING_FOR_SYMBOL" if not symbol
            else "BLOCKED_SOURCE" if self._last_market_data_status and self._last_market_data_status != DataStatus.LIVE.value
            else process_state
        )
        return {
            "state": process_state,
            "enabled": enabled,
            "started_at_utc": self._started_at_utc,
            "last_cycle_at_utc": self._last_cycle_at_utc,
            "last_error": self._last_error,
            "last_connection_status": self._last_connection_status,
            "last_market_data_status": self._last_market_data_status,
            "last_quote_source_timestamp_utc": self._last_quote_source_timestamp_utc,
            "symbol": symbol,
            "coverage": coverage,
            "metrics": {
                "optional_macro_refresh_error": self._macro_error,
                "last_cycle_duration_ms": self._last_cycle_duration_ms,
                "quote_latency_ms": self._last_quote_latency_ms,
                "m5_collection_latency_ms": self._last_m5_collection_latency_ms,
                "worker_failures": self._worker_failures,
                "event_loop_lag_ms": self._event_loop_lag_ms,
                "pending_jobs": sum(count for state, count in persisted["jobs"].items() if state in {"QUEUED", "RUNNING"}),
            },
            "workers": [
                {"id": "source-collector", "state": worker_state, "role": "Completed MT5 candle archive"},
                {"id": "data-quality-sentinel", "state": worker_state, "role": "Tick, candle-gap, spread, and clock checks"},
                {"id": "chart-researcher", "state": worker_state, "role": "Queued multi-timeframe completed-bar structure review"},
                {"id": "momentum-researcher", "state": worker_state, "role": "Completed-bar EMA, RSI, MACD, ADX, and ATR context"},
                {"id": "macro-researcher", "state": worker_state, "role": "Public calendar plus official BLS, BEA, and Federal Reserve schedule provenance"},
                {"id": "context-researcher", "state": worker_state, "role": "Explicitly configured cross-market broker context"},
                {
                    "id": "strategy-ensemble-validator",
                    "state": worker_state if worker_state in {"PAUSED", "PAUSING", "STOPPED", "BLOCKED_SOURCE"} else "REVIEW_REQUIRED",
                    "role": "Frozen decisions, paper candidates, chronological labels; no auto-promotion",
                },
            ],
            **persisted,
        }

    def _enabled(self) -> bool:
        return bool(read_operations_status(self.database_path)["research_pipeline_enabled"])

    def notify_completed_bar(self, symbol: str | None, candle: Candle) -> None:
        """Wake the existing serialized worker after an observed broker M5 close."""
        if candle.completed and symbol == self.configured_symbol():
            self._control_changed.set()

    def set_enabled(self, enabled: bool) -> None:
        if self._enabled() == enabled:
            return
        write_operation_control(
            self.database_path,
            key="research_pipeline_enabled",
            value="true" if enabled else "false",
            actor="LOCAL_OPERATOR",
            action="RESEARCH_PIPELINE_RESUMED" if enabled else "RESEARCH_PIPELINE_PAUSED",
        )
        self._control_changed.set()

    def _broker_server(self, symbol: str) -> str:
        connection = self.adapter.connection(symbol)
        self._last_connection_status = connection.data_status.value
        if connection.data_status == DataStatus.LIVE:
            self._broker_servers[symbol] = connection.broker_server or ""
        return self._broker_servers.get(symbol, "")

    def _bootstrap_history_if_due(self, symbol: str, broker_server: str, now: datetime) -> None:
        last_attempt = self._last_bootstrap_at.get(symbol)
        if last_attempt and now - last_attempt < timedelta(seconds=settings.research_bootstrap_retry_seconds):
            return
        needs_history = any(
            count_completed_candles(
                self.database_path,
                symbol=symbol,
                timeframe=spec.timeframe,
                broker_server=broker_server,
            ) < spec.bootstrap_limit - 1
            for spec in ARCHIVE_SPECS
        )
        if not needs_history:
            return
        self._last_bootstrap_at[symbol] = now
        for spec in ARCHIVE_SPECS:
            stored = count_completed_candles(
                self.database_path,
                symbol=symbol,
                timeframe=spec.timeframe,
                broker_server=broker_server,
            )
            if stored >= spec.bootstrap_limit - 1:
                continue
            status, _reasons, candles = self.adapter.candles(symbol, spec.timeframe, spec.bootstrap_limit)
            if status == DataStatus.LIVE:
                store_completed_candles(
                    self.database_path,
                    source="MT5",
                    broker_server=broker_server,
                    symbol=symbol,
                    timeframe=spec.timeframe,
                    candles=candles,
                    timeframe_seconds=spec.seconds,
                    observed_at_utc=now,
                )

    def _collect_recent_completed_candles(
        self,
        symbol: str,
        broker_server: str,
        now: datetime,
    ) -> Candle | None:
        latest_m5: Candle | None = None
        for spec, research_spec in zip(ARCHIVE_SPECS, (*TIMEFRAME_SPECS, *AUXILIARY_TIMEFRAME_SPECS), strict=True):
            status, _reasons, candles = self.adapter.candles(
                symbol,
                spec.timeframe,
                research_spec.required_completed_candles + research_spec.indicator_warmup_candles + 1,
            )
            if status != DataStatus.LIVE:
                continue
            store_completed_candles(
                self.database_path,
                source="MT5",
                broker_server=broker_server,
                symbol=symbol,
                timeframe=spec.timeframe,
                candles=candles,
                timeframe_seconds=spec.seconds,
                observed_at_utc=now,
            )
            if spec.timeframe == "M5":
                completed = [candle for candle in candles if candle.completed]
                latest_m5 = max(completed, key=lambda candle: candle.open_time_utc) if completed else None
        return latest_m5

    def _run_research_job(self, job: dict[str, object], now: datetime, quote: QuoteResponse) -> None:
        job_id = str(job["job_id"])
        symbol = str(job["symbol"])
        anchor_time_utc = job["anchor_time_utc"]
        if not isinstance(anchor_time_utc, datetime):
            raise ValueError("RESEARCH_JOB_ANCHOR_INVALID")
        try:
            calendar = self.calendar.upcoming_usd_events()
            record_calendar_snapshot(
                self.database_path,
                snapshot_id=str(uuid4()),
                observed_at_utc=now,
                source=calendar.source,
                source_url=calendar.source_url,
                source_timestamp_utc=calendar.source_timestamp_utc,
                data_status=calendar.data_status.value,
                reason_codes=calendar.reason_codes,
                payload=calendar.model_dump(mode="json"),
            )
            response = self.coordinator.snapshot(symbol, calendar_response=calendar, quote_snapshot=quote)
            m5_evidence = next(
                (item for item in response.analysis_timeframes if item.timeframe == "M5"), None
            )
            if (
                m5_evidence is None
                or m5_evidence.source_timestamp_utc != anchor_time_utc + TIMEFRAME_SPECS[0].duration
            ):
                invalidate_research_job(
                    self.database_path, job_id=job_id,
                    reason_codes=["ASOF_CANDLE_MISMATCH", "HISTORICAL_REPLAY_NOT_AVAILABLE"],
                )
                return
            source_statuses = {
                "calendar": calendar.data_status.value,
                **{f"bot_{bot.bot_id}": bot.data_status.value for bot in response.bots},
                **{f"timeframe_{item.timeframe}": item.data_status.value for item in response.analysis_timeframes},
            }
            record_research_run(
                self.database_path,
                run_id=str(uuid4()),
                job_id=job_id,
                observed_at_utc=now,
                symbol=symbol,
                anchor_time_utc=anchor_time_utc,
                trigger="COMPLETED_M5_BAR",
                data_status=response.data_status.value,
                feature_set_version=FEATURE_SET_VERSION,
                source_statuses=source_statuses,
                response=response.model_dump(mode="json"),
                reason_codes=response.reason_codes,
            )
            self._freeze_research_decision(
                symbol=symbol,
                anchor_time_utc=anchor_time_utc,
                observed_at_utc=now,
                quote_snapshot=quote,
                response=response,
            )
            self._record_eligible_signal(symbol, anchor_time_utc, now, response)
            if response.professional_analysis:
                record_strategy_journal_events(
                    self.database_path,
                    observed_at_utc=now,
                    symbol=symbol,
                    candle_open_utc=anchor_time_utc,
                    disposition=response.professional_analysis.risk_engine.state,
                    modules=[item.model_dump(mode="json") for item in response.professional_analysis.strategy_modules],
                )
            complete_research_job(self.database_path, job_id=job_id, reason_codes=response.reason_codes)
        except Exception as error:
            fail_research_job(
                self.database_path,
                job_id=job_id,
                reason_codes=["RESEARCH_WORKER_ERROR", type(error).__name__],
            )
            raise

    def _record_eligible_signal(self, symbol: str, anchor_time_utc: datetime, now: datetime, response: object) -> None:
        """Freeze one qualified research alert for its completed M5 candle."""
        from app.schemas.market import ResearchResponse

        if not isinstance(response, ResearchResponse):
            return
        controls = read_operations_status(self.database_path)
        if controls["kill_switch_enabled"] or not controls["research_pipeline_enabled"]:
            return
        watch = response.live_research_watch
        proof = watch.signal_proof if watch else None
        broker_server = self._broker_servers.get(symbol, "")
        if not (
            broker_server and watch and proof and proof.publication_state == "ELIGIBLE"
            and watch.lifecycle == "ACTIVE_RESEARCH_WATCH" and watch.reference_levels
            and watch.active_from_utc == anchor_time_utc + TIMEFRAME_SPECS[0].duration
            and watch.expires_at_utc and now < watch.expires_at_utc
            and response.data_status == DataStatus.LIVE
        ):
            return
        decision = "WATCH_LONG" if watch.direction == "LONG_CONTEXT" else "WATCH_SHORT" if watch.direction == "SHORT_CONTEXT" else None
        if decision is None:
            return
        payload = {
            "broker_server": broker_server,
            "feature_set_version": FEATURE_SET_VERSION,
            "watch": watch.model_dump(mode="json"),
        }
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        identity = f"{broker_server}|{symbol}|{anchor_time_utc.isoformat()}|{decision}|{FEATURE_SET_VERSION}"
        record_signal_history(
            self.database_path,
            signal_id="auto-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:32],
            provided_at_utc=watch.observed_at_utc,
            symbol=symbol,
            source=watch.source,
            source_timestamp_utc=watch.source_timestamp_utc,
            data_status=watch.data_status.value,
            analysis_mode="AUTOMATIC_RESEARCH_WATCH_V1",
            decision=decision,
            market_context="UPWARD_STRUCTURE" if decision == "WATCH_LONG" else "DOWNWARD_STRUCTURE",
            summary=watch.summary,
            event_risk_state=watch.event_risk_state,
            paper_status="NOT_CREATED",
            input_fingerprint=hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
            reason_codes=list(dict.fromkeys([*watch.reason_codes, *proof.reason_codes])),
            payload=payload,
        )

    def _label_mature_runs(self, symbol: str, broker_server: str, now: datetime) -> None:
        source_key = (symbol, broker_server)
        first_backfill = source_key not in self._label_backfilled_sources
        pending = read_unlabelled_research_runs(
            self.database_path,
            symbol=symbol,
            label_version=OUTCOME_LABEL_VERSION,
            horizon_bars=OUTCOME_HORIZON_BARS,
        )
        candles = read_completed_candles(
            self.database_path,
            symbol=symbol,
            timeframe="M5",
            limit=LABEL_BACKFILL_ARCHIVE_LIMIT if first_backfill else 6_000,
            broker_server=broker_server,
        )
        candle_by_open_time = {candle.open_time_utc: (index, candle) for index, candle in enumerate(candles)}
        for signal in read_pending_signal_followups(self.database_path, symbol=symbol):
            if signal["broker_server"] != broker_server:
                continue
            anchor_open_utc = signal["anchor_close_utc"] - TIMEFRAME_SPECS[0].duration
            entry = candle_by_open_time.get(anchor_open_utc)
            if not entry:
                continue
            index, anchor = entry
            outcome_index = index + OUTCOME_HORIZON_BARS
            if outcome_index >= len(candles):
                continue
            expected_opens = [anchor_open_utc + TIMEFRAME_SPECS[0].duration * step
                              for step in range(OUTCOME_HORIZON_BARS + 1)]
            if [candle.open_time_utc for candle in candles[index:outcome_index + 1]] != expected_opens:
                continue
            outcome = candles[outcome_index]
            direction = 1 if signal["decision"] == "WATCH_LONG" else -1
            movement = round((outcome.close - anchor.close) * direction, 8)
            record_signal_followup(
                self.database_path, signal_id=signal["signal_id"], broker_server=broker_server,
                anchor_close_utc=signal["anchor_close_utc"],
                outcome_close_utc=outcome.open_time_utc + TIMEFRAME_SPECS[0].duration,
                anchor_close=anchor.close, outcome_close=outcome.close,
                directional_change=movement,
                directional_state="FAVORABLE" if movement > 0 else "ADVERSE" if movement < 0 else "FLAT",
                labelled_at_utc=now,
            )
        for run in pending:
            entry = candle_by_open_time.get(run["anchor_time_utc"])
            if not entry:
                continue
            index, anchor = entry
            outcome_index = index + OUTCOME_HORIZON_BARS
            if outcome_index >= len(candles):
                continue
            expected_opens = [anchor.open_time_utc + TIMEFRAME_SPECS[0].duration * step
                              for step in range(OUTCOME_HORIZON_BARS + 1)]
            if [candle.open_time_utc for candle in candles[index:outcome_index + 1]] != expected_opens:
                continue
            record_outcome_label(
                self.database_path,
                run_id=run["run_id"],
                label_version=OUTCOME_LABEL_VERSION,
                horizon_bars=OUTCOME_HORIZON_BARS,
                anchor_close=anchor.close,
                outcome_close=candles[outcome_index].close,
                labelled_at_utc=now,
            )
        label_mature_frozen_decisions(
            self.database_path,
            symbol=symbol,
            candles=candles,
            horizon_bars=OUTCOME_HORIZON_BARS,
            label_version=PAPER_OUTCOME_LABEL_VERSION,
            labelled_at_utc=now,
        )
        self._label_backfilled_sources.add(source_key)

    def _freeze_research_decision(
        self,
        *,
        symbol: str,
        anchor_time_utc: datetime,
        observed_at_utc: datetime,
        quote_snapshot: QuoteResponse,
        response: object,
    ) -> None:
        """Persist a decision-time evidence bundle for later paper outcome labelling."""
        from app.schemas.market import ResearchResponse

        if not isinstance(response, ResearchResponse) or not response.strategy_ensemble or not response.data_quality:
            return
        quote = quote_snapshot
        controls = read_operations_status(self.database_path)
        decision = response.strategy_ensemble.decision
        professional_risk = response.professional_analysis.risk_engine if response.professional_analysis else None
        if decision == "NO_TRADE":
            paper_status = "NOT_CREATED"
        elif controls["kill_switch_enabled"]:
            paper_status = "KILL_SWITCH_ENABLED"
        elif not professional_risk or professional_risk.state != "REVIEW_REQUIRED":
            paper_status = "NOT_CREATED"
        elif not professional_risk.costs_complete:
            # A watch state is useful evidence but is not a paper candidate
            # until expected trading costs are source-backed.
            paper_status = "NOT_CREATED"
        else:
            paper_status = "RECORDED"
        feature_snapshot = {
            "analysis_timeframes": [item.model_dump(mode="json") for item in response.analysis_timeframes],
            "top_down": response.top_down.model_dump(mode="json") if response.top_down else None,
            "data_quality": response.data_quality.model_dump(mode="json"),
            "session_regime": response.session_regime.model_dump(mode="json") if response.session_regime else None,
            "cross_market": [item.model_dump(mode="json") for item in response.cross_market],
            "official_macro_sources": [item.model_dump(mode="json") for item in response.official_macro_sources],
            "event_risk_state": response.event_risk_state,
            "professional_analysis": response.professional_analysis.model_dump(mode="json") if response.professional_analysis else None,
            "source_status": response.data_status.value,
        }
        serialized = json.dumps(feature_snapshot, sort_keys=True, separators=(",", ":"))
        fingerprint = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        record_frozen_research_decision(
            self.database_path,
            decision_id=str(uuid4()), observed_at_utc=observed_at_utc, symbol=symbol,
            anchor_time_utc=anchor_time_utc, decision=decision, feature_set_version=FEATURE_SET_VERSION,
            input_fingerprint=fingerprint, quote_source_timestamp_utc=quote.source_timestamp_utc,
            quote_bid=quote.bid, quote_ask=quote.ask, spread_points=quote.spread_points,
            data_quality_state=response.data_quality.status,
            event_risk_state=response.event_risk_state,
            session_regime=response.session_regime.market_regime if response.session_regime else "UNAVAILABLE",
            model_promotion_state=response.strategy_ensemble.model_promotion_state,
            paper_status=paper_status, feature_snapshot=feature_snapshot,
            ensemble=response.strategy_ensemble.model_dump(mode="json"),
            costs={
                "spread_points": quote.spread_points,
                "commission_points": None,
                "slippage_points": None,
                "swap_points": None,
                "status": "COSTS_INCOMPLETE",
            },
            reason_codes=[
                "FROZEN_COMPLETED_CANDLE_EVIDENCE", "COMMISSION_UNAVAILABLE", "SLIPPAGE_UNAVAILABLE",
                "PAPER_CANDIDATE_BLOCKED_UNTIL_COSTS_SOURCE_BACKED", "NO_ORDER_EXECUTION",
            ],
        )

    def _calibrate_if_due(
        self,
        symbol: str,
        broker_server: str,
        quote: QuoteResponse,
        now: datetime,
    ) -> None:
        last_calibration = self._last_calibration_at.get(symbol)
        if last_calibration and now - last_calibration < timedelta(seconds=settings.training_interval_seconds):
            return
        candles = read_completed_candles(
            self.database_path,
            symbol=symbol,
            timeframe="M5",
            limit=6_000,
            broker_server=broker_server,
        )
        point = quote.point if quote.point is not None and quote.point > 0 else None
        calibrations, reason_codes = calibrate_strategies(candles, point)
        dataset_start = candles[0].open_time_utc if candles else None
        dataset_end = candles[-1].open_time_utc if candles else None
        state = "REVIEW_REQUIRED" if calibrations else "INSUFFICIENT_DATA"
        record_model_version(
            self.database_path,
            model_version_id=str(uuid4()),
            created_at_utc=now,
            model_kind="DETERMINISTIC_STRATEGY_CALIBRATION",
            model_version="m5-chronological-calibration-v2-nonoverlap",
            state=state,
            symbol=symbol,
            timeframe="M5",
            dataset_start_utc=dataset_start,
            dataset_end_utc=dataset_end,
            dataset_candles=len(candles),
            feature_set_version=FEATURE_SET_VERSION,
            metrics={"calibration_count": len(calibrations), "minimum_candles": MIN_TRAINING_CANDLES},
            payload={"calibrations": [WalkForwardStrategyResult(**asdict(item)).model_dump(mode="json") for item in calibrations]},
            reason_codes=list(reason_codes),
        )
        self._last_calibration_at[symbol] = now
