# UI evidence — unified «پیام‌رسانی» (Settings → Messaging) redesign

Captured from the running QA server (fake providers, seeded `qa-bike` store) on branch
`kiro/messaging-settings-ux-20261104`. The `fx_*` set is rendered in a real headless browser with the **Vazirmatn web font
embedded**, so Persian text renders correctly (the earlier `msgux_*` set showed glyph boxes because the font was not
embedded in the snapshot — superseded by these).

## Real-font screenshots at the required widths
| file | page | width |
|---|---|---|
| `fx_messaging_home_1440.png` | Canonical **Settings → پیام‌رسانی** center (KPIs + 5 subsection cards with live status) | 1440 |
| `fx_messaging_home_1280.png` | same | 1280 |
| `fx_messaging_home_390.png` | same, mobile stack | 390 |
| `fx_event_editor_1440.png` | Unified `order.created` editor — **side-by-side** SMS \| Email | 1440 |
| `fx_event_editor_1280.png` | same — side-by-side at 1280 | 1280 |
| `fx_event_editor_768.png` | same — stacked (tablet; side-by-side breakpoint is 1100px) | 768 |
| `fx_event_editor_390.png` | same — stacked (mobile) | 390 |

## Duplicate-nav fix (round 3)
`fx_fix_messaging_home_1440.png` — the Messaging Center after removing the duplicate subsection bar: exactly **one**
subsection navigation row sits immediately below the Settings tabs; the search area and KPI cards follow with no second
bar. Verified over HTTP on all 7 messaging pages: `admin-subtabs` bar = 1, old `msg-subnav` = 0, active subtab = 1.

## What the screenshots demonstrate
- **Canonical section:** the Settings section tab row shows «پیام‌رسانی» active (its own real route `settings/messaging/`),
  with a KPI summary (events / SMS-on / email-on / customised / failed) and five cards that each show live status and link
  into the subsection. This is a real management center, not just a nav bar.
- **Redesigned editor:** full content width (max 1500px), genuinely two balanced columns at ≥1100px (1280 and 1440 shown),
  stacked below; toggle switches, per-channel effective-status badges, SMS character + segment counter, click-to-insert
  variable chips, subject/plain/HTML for email, previews, one atomic sticky save bar, RTL Persian typography.
- No horizontal overflow at any width; controls readable; stacking is clean on tablet/mobile.

> Note: in the full-page captures the sticky save bar (`position:sticky; bottom:0`) appears mid-content because a full-page
> screenshot flattens the scroll viewport; in a live browser it is pinned to the bottom of the viewport while scrolling.
