# Risk boundary — Phase 1

PyonTrading 2 is analysis-first and read-only. It never sends broker orders or suggests a trade from missing data. It does not provide position size, a profitability claim, or a calibrated confidence score.

The research screen can display `WATCH_LONG` or `WATCH_SHORT` only as an unvalidated description of completed multi-timeframe conditions. An active watch may display an indicative entry at the fresh broker ask (long) or bid (short), with stop at one completed-M5 ATR and TP1/TP2 at one/two ATR in the watch direction. These are deterministic reference levels, not validated predictions, guaranteed fills, or order instructions. They are absent when the watch is withheld, a source is blocked, the quote is stale, or the quote is more than one ATR from the last completed M5 close. A background chronological calibration remains `REVIEW_REQUIRED` until a human-reviewed validation and promotion policy exists; it cannot enable execution.

Calendar absence is labeled `NEWS_CHECK_UNVERIFIED`; it cannot become a clean news check. Missing broker history, incomplete cost information, disconnected MT5, stale quotes, or unavailable calendar data must continue to produce an explicit unavailable or `NO TRADE` state.

The deterministic ensemble requires at least two agreeing completed-candle rules before it can show a research-only `WATCH_LONG` or `WATCH_SHORT`. The rules are not statistically independent: momentum and range-breakout share M5 inputs. Publication also requires completed multi-timeframe alignment and an explicit proof. It must abstain for incomplete or conflicting evidence, integrity warnings, or elevated verified calendar risk. Its `confidence_state` remains `WITHHELD`; no probability or high-accuracy claim is displayed.

Paper candidates are research records, not orders or fill simulations. They preserve a contemporaneous bid/ask spread and fixed-horizon outcome label where later completed bars exist, but they do not claim commission, slippage, swaps, latency, or observed fill quality. Metrics remain `REVIEW_REQUIRED`; no model self-promotes from recent labels.

The paper kill switch is fail-safe local control. It can prevent new hypothetical candidate records and it is audited, but it is not an execution kill switch because PyonTrading 2 has no execution code. Any future model-promotion or order-decision workflow requires separately designed authentication, explicit human approval, rollback evidence, and a new security review.

