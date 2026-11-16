from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any, Callable

from fastapi import WebSocket

from app.adapters.mt5 import MT5Adapter
from app.config import settings
from app.schemas.market import Candle, DataStatus, QuoteResponse
from app.storage.database import record_evaluation


class LiveService:
    def __init__(self, adapter: MT5Adapter, configured_symbol: str | None, database_path=None) -> None:
        self.adapter = adapter
        self.configured_symbol = configured_symbol
        self.sequence = 0
        self.clients: set[WebSocket] = set()
        self._task: asyncio.Task[None] | None = None
        self._forming_m5: Candle | None = None
        self._poll_count = 0
        self.database_path = database_path
        self.latest_quote: QuoteResponse | None = None
        self._source_generation = 0
        self.on_completed_bar: Callable[[str | None, Candle], None] | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._poll(), name="mt5-quote-poller")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        shutdown = getattr(self.adapter, "shutdown", None)
        if callable(shutdown):
            shutdown()

    async def _poll(self) -> None:
        while True:
            try:
                generation, symbol = self._source_generation, self.configured_symbol
                quote = await asyncio.to_thread(self.adapter.quote, symbol)
                if generation == self._source_generation:
                    self.latest_quote = quote
                    await self.broadcast("quote", quote.model_dump(mode="json"))
                    if quote.data_status == DataStatus.LIVE and generation == self._source_generation:
                        await self._publish_m5_bar_state(quote)
                    self._poll_count += 1
                    if self._poll_count % 5 == 0 and generation == self._source_generation:
                        await self.broadcast("heartbeat", {"data_status": quote.data_status.value, "reason_codes": quote.reason_codes})
            except Exception as error:  # keep polling observable without presenting fake data
                await self.broadcast("provider_status", {"data_status": "SOURCE_ERROR", "reason_codes": ["QUOTE_POLLER_ERROR", type(error).__name__]})
            await asyncio.sleep(settings.quote_poll_seconds)

    async def _publish_m5_bar_state(self, quote: QuoteResponse | None = None) -> None:
        """Publish a bounded M5 forming-bar stream without recalculating history per tick."""
        generation, symbol = self._source_generation, self.configured_symbol
        if quote and quote.symbol != symbol:
            return
        status, reasons, candles = await asyncio.to_thread(self.adapter.candles, symbol, "M5", 2)
        if generation != self._source_generation or status != DataStatus.LIVE or not candles:
            return
        forming = candles[-1]
        payload = {
            "symbol": symbol,
            "timeframe": "M5",
            "data_status": status.value,
            "reason_codes": reasons,
            "candle": forming.model_dump(mode="json"),
        }
        completed = candles[-2] if len(candles) > 1 else None
        if completed:
            await asyncio.to_thread(self._record_completed_observation, completed, quote, symbol)
        if generation != self._source_generation:
            return
        if self._forming_m5 and completed and completed.open_time_utc == self._forming_m5.open_time_utc and forming.open_time_utc > completed.open_time_utc:
            closed_bar = completed.model_copy(update={"completed": True})
            if self.on_completed_bar:
                self.on_completed_bar(symbol, closed_bar)
            await self.broadcast("bar_closed", {**payload, "candle": closed_bar.model_dump(mode="json")})
        self._forming_m5 = forming
        await self.broadcast("bar_update", payload)

    def _record_completed_observation(self, candle: Candle, quote: QuoteResponse | None, symbol: str | None) -> None:
        if not self.database_path or not symbol or not quote:
            return
        record_evaluation(
            self.database_path,
            evaluation_at_utc=datetime.now(UTC),
            symbol=symbol,
            candle_open_utc=candle.open_time_utc,
            quote_source_timestamp_utc=quote.source_timestamp_utc,
            quote_bid=quote.bid,
            quote_ask=quote.ask,
            quote_status=quote.data_status.value,
            reason_codes=["PHASE_2_STRATEGY_NOT_IMPLEMENTED", "NO_ORDER_EXECUTION"],
        )

    def set_configured_symbol(self, symbol: str | None) -> None:
        if symbol == self.configured_symbol:
            return
        self._source_generation += 1
        self.configured_symbol = symbol
        self._forming_m5 = None
        self.latest_quote = None

    async def register(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.clients.add(websocket)
        quote = self.latest_quote
        if quote is None:
            status, reasons = "CONNECTING", ["QUOTE_NOT_YET_OBSERVED"]
        elif quote.data_status == DataStatus.LIVE and (datetime.now(UTC) - quote.observed_at_utc).total_seconds() > 6:
            status, reasons = DataStatus.STALE.value, ["QUOTE_SNAPSHOT_STALE"]
        else:
            status, reasons = quote.data_status.value, quote.reason_codes
        await self.send(websocket, "heartbeat", {"data_status": status, "reason_codes": reasons})

    def unregister(self, websocket: WebSocket) -> None:
        self.clients.discard(websocket)

    async def send(self, websocket: WebSocket, event_type: str, payload: dict[str, Any]) -> None:
        self.sequence += 1
        await websocket.send_json({"type": event_type, "sequence": self.sequence, "observed_at_utc": datetime.now(UTC).isoformat(), "payload": payload})

    async def broadcast(self, event_type: str, payload: dict[str, Any]) -> None:
        for client in list(self.clients):
            try:
                await self.send(client, event_type, payload)
            except Exception:
                self.unregister(client)

