# Desktop layout and session clock - 2026-11-16 PHT

## Changes

- Replaced the desktop chart's viewport-minus-constant height with a page grid:
  header, navigation, flexible main row and a reserved 124px support row. Long
  calendar/error content can scroll inside its card instead of being discarded.
- Chart and calendar share a column; setup and latest observation share the other.
  Tablet/mobile retain natural vertical scrolling with no horizontal overflow.
- Removed the stretched inner sidebar frame and automatic bottom action margin.
  Used one surface, grouped blocker/entry state, compact fact rows, readable type
  and a default-closed evidence disclosure. Quote/spread details remain available
  inside that disclosure; MT5 live/closed status stays visible in the header.
- Preserved actual failed proof detail when a quality check fails despite the
  aggregate quality status being CLEAR. Other condition descriptions are labeled
  as unmet requirements, not claims that those checks passed.
- Added a session label beside the existing PHT clock, using the same one-second
  UI clock. No new polling, provider calls, data storage or trading logic.

## Session-hour basis

Source: [FOREX.com local session table](https://www.forex.com/en-au/forex-trading/forex-market-hours/),
retrieved 2026-11-16; publication/effective date not supplied. Display convention:
Sydney 08:00-16:00, Tokyo 09:00-18:00, London 08:00-16:00 and New York 08:00-17:00,
each on its own local weekdays. Browser IANA time zones handle independent DST
changes; simultaneous windows show an overlap. The indicative weekend runs from
Friday 17:00 to Sunday 17:00 New York time.

This is time-based FX context, not an exchange feed, holiday calendar, XAUUSD
broker schedule or execution permission. It does not replace MT5 status or alter
the backend's separate regime/opening-range strategy windows. Schedule sources
use differing session conventions; this clock explicitly uses the table above.

## Verification

- `npm.cmd test`: 37 passed in eight files, including 17 session-clock cases for
  exact boundaries, independent DST changes, Sydney, overlaps, weekends and an
  invalid clock.
- `npm.cmd run build`: TypeScript and Vite production build passed.
- Full exploratory Playwright run: 127/132 passed. Three failures expected quote
  details in their former location; one live-source fixture aged into STALE;
  one multi-workspace/modal flow exceeded its original 30-second test budget.
  Expectations now check both the visible closed status and on-demand detail;
  the intended live fixture refreshes timestamps, and only the lengthy full-flow
  test has a 60-second budget. Production freshness limits were not relaxed.
- Final targeted rerun: 30/30 passed across desktop, tablet and mobile, including
  every failed scenario, viewport fit, fully visible controls, keyboard disclosure,
  top-down AJAX updates, stale evidence, calendar/observation refresh, indicative
  levels and live session changes without reloading.
- Live inspections at 375, 768, 1024, 1100, 1280, 1366, 1440 and 1920px had no
  horizontal overflow or browser page errors. At 1280x720, the document height
  was exactly 720px, the canvas about 294px high, and both support cards ended at
  712px. The research-network button ended at 569px inside its sidebar. At
  1920x1080, document height was 1080px, the canvas about 654px high, and support
  cards ended at 1072px. Final screenshots were visually inspected:
  `output/audit-2026-11-16/session-layout-1280-final.png` and
  `output/audit-2026-11-16/session-layout-1920-final.png`.
- A final live interaction check kept the same chart node through an automatic
  refresh; the zoom range also survived a document reload unchanged. No chart
  reset or new chart instance was introduced by the layout wrapper.

The complete 132-case suite was not repeated after the final presentation/test
edits; the 30-case final run supersedes its affected cases. No backend algorithm,
signal publication criterion, database, credentials or broker-order code changed.
