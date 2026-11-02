# Kronos validation contract

Kronos is currently disabled and has zero authority over PyonTrading research
states. This document defines the required gate before any optional enablement.

1. Inspect the official upstream repository, license, dependency pins, weight
   source, supported candle schema and model interface at the time of review.
2. Obtain explicit approval for model-weight download size, network source and
   local disk use. Record version, checksum, license and retrieval time.
3. Keep adapter and dependencies under `research/kronos/`; importing or
   starting the core FastAPI/MT5 application must not load it.
4. Supply only chronologically ordered, source-backed completed OHLCV. MT5
   tick volume remains labelled as a proxy.
5. Run shadow-only forecasts against naive last-price/random-walk and simple
   statistical baselines using identical cutoffs and horizons.
6. Use walk-forward validation plus untouched holdout, preserve seeds, record
   resource measurements and save forecasts before outcomes occur.
7. If no robust out-of-sample evidence exists, keep the component `UNPROVEN`
   and disabled. It can never create an order or override the risk gate.
