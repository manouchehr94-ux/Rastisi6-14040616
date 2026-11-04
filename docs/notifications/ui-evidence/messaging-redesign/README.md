# UI evidence — unified «پیام‌رسانی» (Settings → Messaging) redesign

Captured from the running QA server (fake providers, seeded `qa-bike` store) on branch
`kiro/messaging-settings-ux-20261104`. These show the five-subsection unified messaging experience the product owner asked
for, replacing the previous split between Marketing → Notifications and Settings → SMS.

The five subsections (exact Persian labels): رویدادها و قالب‌ها · کانال‌های ارسال · فرستنده‌ی ایمیل و دامنه · سرویس پیامک و
اعتبار · تاریخچه و صف ارسال. The identical sub-navigation bar now appears on every messaging page, including the SMS
provider/credits page that used to live on its own.

| file | page | width |
|---|---|---|
| `msgux_1_events_templates_desktop.png` | Events & Templates — the event list with SMS + Email status per event | 1280 |
| `msgux_1_events_templates_mobile.png` | Events & Templates | 390 |
| `msgux_2_event_editor_order_created_desktop.png` | Unified event editor (`order.created`): SMS card + Email card (subject / plain / HTML), preview, one save, revisions, test-send | 1280 |
| `msgux_5_sms_provider_desktop.png` | SMS Provider & Credits — **now carrying the unified sub-navigation** (the key consolidation) | 1280 |
| `msgux_5_sms_provider_mobile.png` | SMS Provider & Credits, responsive stack | 390 |
| `msgux_6_history_desktop.png` | Delivery History & Queue (with links to the SMS phone-gateway queue/logs) | 1280 |

> The Persian glyphs render as boxes in these standalone PNGs because the Vazirmatn web font is not embedded in the
> captured snapshot; on the live server (and in a real browser) the text renders normally. The snapshots still faithfully
> show layout, RTL direction, the active sub-tab, spacing and all controls.

**Before:** SMS provider/credits lived under Settings → «پیامک» with no link to the notification event/template pages, which
lived under Marketing → «اعلان‌ها و پیام‌ها»; the two had separate, inconsistent navigation and a duplicate SMS-template
edit surface. **After:** one «پیام‌رسانی» experience with a shared five-subsection bar on every page, a single unified
per-event editor for SMS+Email, and the SMS settings page pointing at that editor instead of duplicating it.
