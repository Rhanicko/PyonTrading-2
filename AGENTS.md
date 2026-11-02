# PyonTrading 2 agent guide

## Precedence

1. Data integrity and safety: use source-labelled inputs, completed candles for
   analysis, explicit unavailable states, localhost-only operation, and no
   broker order placement.
2. Phase order: strengthen the XAUUSD read-only workflow before adding a new
   market, paid source, model, or experimental forecasting component.
3. Repository conventions: FastAPI routes stay thin; the MT5 adapter is the
   only broker boundary; SQLite writes are forward-only migrations; React
   consumes typed API payloads; preserve the existing terminal visual system.
4. Load a relevant project-local `.agents/skills/*/SKILL.md` only for its task.

## Product boundary

- Never call or add `mt5.order_send`; do not place, amend, cancel, simulate,
  or authorize broker orders.
- Do not invent quotes, candles, volume, order flow, calendar data, fills,
  profitability, or confidence. Use `UNAVAILABLE`, `NO_TRADE`, or a clearly
  labelled proxy when evidence is missing.
- MT5 bar zero is forming. Only previous completed bars may influence research,
  replay, strategy votes, or journals.
- Tick volume is a broker proxy. It is not global XAUUSD volume, COMEX executed
  volume, a footprint, CVD, institutional positioning, or a consolidated book.
- Preserve raw and normalized timestamps, source URLs, source status, reason
  codes, strategy versions, and decision-time evidence.

## Change procedure

1. Trace request -> validation -> service -> adapter/storage -> returned UI
   state before editing.
2. Make the smallest compatible change. Use a new SQLite migration for schema
   changes; never rewrite earlier migrations or mutate audit evidence.
3. Add focused tests for source failures, stale/missing data, and changed
   invariants. Run backend tests/Ruff and relevant frontend checks.
4. State verified local evidence separately from live MT5/provider evidence.

## Optional integrations

Kronos, licensed futures flow, external skills, provider credentials, and
model weights remain optional. Inspect their official source, license,
dependencies, resource cost, and data contract before adding them. Core live
research must still run if any optional component is disabled.
