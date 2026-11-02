# Risk boundary — Phase 1

PyonTrading 2 is analysis-first and read-only. It never sends broker orders, never suggests a trade from missing data, and does not present an entry, stop, target, volume, profitability claim or confidence score.

The research screen can display `WATCH_LONG` or `WATCH_SHORT` only as an unvalidated description of strict completed multi-timeframe conditions. It does not provide entry, stop, target, size, confidence percentage or order instruction. A background chronological calibration is `REVIEW_REQUIRED` until a human-reviewed validation and promotion policy exists; it cannot enable execution.

Calendar absence is labeled `NEWS_CHECK_UNVERIFIED`; it cannot become a clean news check. Missing broker history, incomplete cost information, disconnected MT5, stale quotes, or unavailable calendar data must continue to produce an explicit unavailable or `NO TRADE` state.

The deterministic ensemble requires at least two independent completed-candle rules to agree before it can show a research-only `WATCH_LONG` or `WATCH_SHORT`. It must abstain for incomplete or conflicting evidence, integrity warnings, or elevated verified calendar risk. Its `confidence_state` remains `WITHHELD`; no probability or high-accuracy claim is displayed.

Paper candidates are research records, not orders or fill simulations. They preserve a contemporaneous bid/ask spread and fixed-horizon outcome label where later completed bars exist, but they do not claim commission, slippage, swaps, latency, or observed fill quality. Metrics remain `REVIEW_REQUIRED`; no model self-promotes from recent labels.

The paper kill switch is fail-safe local control. It can prevent new hypothetical candidate records and it is audited, but it is not an execution kill switch because PyonTrading 2 has no execution code. Any future model-promotion or order-decision workflow requires separately designed authentication, explicit human approval, rollback evidence, and a new security review.

