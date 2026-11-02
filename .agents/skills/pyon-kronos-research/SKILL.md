---
name: pyon-kronos-research
description: Govern any optional PyonTrading Kronos forecasting experiment as a disabled-by-default shadow component.
---

# Pyon Kronos research

## Procedure

1. Inspect upstream license, compatibility, model weights and CPU resource cost
   before installation. Obtain explicit approval for any weight download.
2. Keep adapter/dependencies outside core startup and feed it only verified
   chronologically ordered completed OHLCV.
3. Benchmark saved shadow forecasts against naive/statistical baselines with
   walk-forward validation and untouched holdout.

## Inputs and outputs

- Inputs: approved model, source-backed completed candles, retained seed/model
  metadata and a bounded runner.
- Output: labelled experimental paths or an explicit disabled state.

## Failure modes

Missing approval, model, data, resource budget or validation evidence means
`NOT_AVAILABLE`/`UNPROVEN`. Kronos has no signal, risk or order authority.

## Tests and references

Verify `/api/kronos/status` and `/api/kronos/forecasts` return typed disabled
states until an audited adapter exists. See `docs/KRONOS_VALIDATION.md`.
