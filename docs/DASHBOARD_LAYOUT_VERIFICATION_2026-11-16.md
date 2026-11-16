# Dashboard layout verification - 2026-11-16 PHT

## Scope

Presentation-only market-desk update. Signal gates, publication criteria, price
calculations, source provenance, polling, WebSocket subscriptions, chart viewport
storage and the signal-only boundary were not changed.

- Removed the workstation width cap and reduced outer gutters/header spacing.
- Combined chart context/title and placed indicator controls beside timeframes.
- Made the desktop chart fill the remaining viewport rather than use a fixed
  minimum canvas height. Tablet/mobile content stacks without horizontal overflow.
- Kept setup status, indicative levels or pending stages, actual primary blocker,
  and four key facts visible. Removed repeated pending/confirmation boilerplate.
- Grouped full publication proof, top-down confirmation, bot coverage and
  invalidation conditions under a default-closed native disclosure.
- Used existing theme tokens and a dedicated `styles/market-desk.css` owner for
  the desk layout. No new UI library or additional data requests.

## Verification

- `npm.cmd test`: 20 tests passed in seven files.
- `npm.cmd run build`: TypeScript and Vite production build passed.
- Final targeted Playwright rerun: 18 passed, one worker, desktop/tablet/mobile.
  Covers viewport sizing, fully visible setup actions, keyboard disclosure,
  AJAX updates preserving open review panels, historical top-down labeling,
  overlays, review modal flow and indicative reference-level presentation.
- The earlier full 129-case exploratory run had 128 passes and one layout-test
  startup failure. Follow-up runs also exposed time-dependent active-source
  fixtures: frozen quotes/nested top-down timestamps correctly became stale during
  slower UI checks. Continuously-live scenarios now refresh their mock timestamps;
  explicit stale-source tests remain unchanged. Final affected cases passed;
  the entire 129-case suite was not repeated after the last copy/fixture edits.
- Live browser inspections covered 375, 768, 1024, 1366 and 1920px widths with
  no horizontal overflow or browser page errors. Final desktop confirmation:
  - 1280x720: chart canvas 422px high; setup card client/scroll height both 530px;
    save button bottom 642px, inside the card and viewport.
  - 1920x1080: chart canvas 782px high; setup card client/scroll height both 890px;
    save button bottom 1002px, inside the card and viewport.
- A final live interaction check confirmed the same chart DOM node remained after
  an automatic refresh, the evidence disclosure stayed open, and the mouse-wheel
  viewport range survived both live refresh and a document reload unchanged
  (`from: 213.3365039090909`, `to: 311.427413`).

Screenshots: `output/audit-2026-11-16/market-desk-1280-final.png` and
`output/audit-2026-11-16/market-desk-1920-final.png`; other inspected widths use
`market-desk-<width>.png` in the same directory.

## Boundaries

The live terminal remained MT5 MetaQuotes-Demo. The observed short setup was
pending with a reported completed-M5 candle gap and unconfirmed close/risk checks.
This redesign does not resolve missing market evidence, manufacture entry levels,
validate strategy profitability, or enable broker orders. No commit or push.
