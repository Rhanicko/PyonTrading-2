# CSS Architecture Audit

Date: 2026-11-03 (local workspace execution)

## Scope and method

This audit inspected `frontend/src/styles.css`, every `className` use in the
application/components, and rendered computed styles using Chromium at 1440 px
and 390 px. It is an inventory for incremental repair, not a claim that the
stylesheet has been fully rewritten.

## Static inventory

| Item | Finding |
| --- | --- |
| Main stylesheet | 1,490 lines after removing two obsolete broad hiding rules |
| Parsed CSS rule blocks | 940 |
| Shared tokens | 11 colour/surface tokens, moved to `frontend/src/styles/tokens.css` |
| Component `className` sites | 124 across `App.tsx` and `src/components` |
| Repeated layout selectors | `.workstation` 11, `.topbar` 24, `.workspace-grid` 24, `.chart-panel` 14, `.research-panel` 40, `.lower-grid` 18 |

The remaining `display: none` declarations are intentional: React's `[hidden]`
contract, collapsed WebKit markers/scrollbars, desktop-only navigation text,
mobile-only legend detail, and the deliberately suppressed raw bot skill chips.
The two former positional rules that hid broad research-panel child sets have
been removed. Visibility is now owned by the JSX view conditions and `[hidden]`.

## Runtime inspection

Chromium at 1440 x 960 produced the following computed layout on the locally
served application with unavailable live data:

| Selector | Display | Width | Height |
| --- | --- | ---: | ---: |
| `.workstation` | block | 1440 px | 1242 px |
| `.topbar` | grid | 1380 px | 64 px |
| `.workspace-grid` | grid | 1380 px | 827 px |
| `.chart-panel` | block | 1034 px | 676 px |
| `.research-panel` | flex / sticky | 330 px | 827 px |
| `.live-research-watch` | flex | 308 px | 766 px |

At 390 x 844, the page had a 390 px document width (no horizontal overflow).
The chart and research panel each used the available 370 px content width in a
single-column layout.

## Repair status

Completed in this pass:

- Extracted the current shared visual tokens into `styles/tokens.css`.
- Removed legacy positional child-hiding selectors instead of continuing to
  override them with `!important` rules.
- Kept the chart largest on desktop and verified the small-screen layout has no
  horizontal overflow.

Still intentionally deferred:

- Feature-by-feature CSS extraction. The remaining cascade is large and has
  repeated historical overrides; moving it without a selector-by-selector
  regression suite would be a risky visual rewrite.
- Replacing every repeated selector with component-scoped styles. That is a
  Phase 2 follow-up after visual-regression coverage is expanded.
