# Merchant admin navigation v1 — two-level information architecture

Branch: `redesign/admin-navigation-v1`. Scope: the navigation chrome of
`apps/dashboard/templates/dashboard/base_admin.html`. No URL, view, permission
check, model or tenant-isolation logic changed.

## Model

* **Level 1 — sidebar:** nine flat links, no accordions, no nested items.
* **Level 2 — section tabs:** a horizontal tab bar under the page header listing
  the related screens of the *current* section (hidden when the section has a
  single permitted screen). Scrolls horizontally on phones; the active tab is
  scrolled into view.
* **`Ctrl + K` palette:** same destinations, with `بخش ← تب` path labels.

Single source of truth: `apps/dashboard/navigation.py` (`SECTIONS`, `PALETTE_EXTRAS`).
Rendering: `apps/dashboard/templatetags/dashboard_nav.py` →
`partials/_admin_sidebar_nav.html`, `_admin_section_tabs.html`, `_admin_command_index.html`.

## Navigation map

| Sidebar | Tabs (→ existing route) |
| --- | --- |
| داشبورد | — |
| سفارش‌ها | همه سفارش‌ها (`order-list`) · مرجوعی‌ها (`return-list`) |
| کالاها | همه کالاها · دسته‌بندی‌ها · برندها · ویژگی‌ها · موجودی · انبارها · رزرو موجودی · انتقال انبار |
| فاکتورها و مالی | فاکتورها · پرداخت‌ها · تطبیق پرداخت‌ها |
| مشتریان | مشتریان · سگمنت‌ها |
| بازاریابی | کمپین‌ها · مناسبت‌ها و هدیه‌ها · کدهای تخفیف · اعلان‌ها و پیام‌ها |
| فروشگاه | ظاهر و طراحی · سازنده فروشگاه · قالب‌های آماده · کالکشن‌ها · محتوا · صفحه اصلی · منوها · فوتر · شبکه‌های اجتماعی |
| گزارش‌ها | گزارش‌های حرفه‌ای · گزارش رخدادها |
| تنظیمات | تنظیمات عمومی · ارسال · مالیات · تنظیمات مالی · پیامک · اعضای تیم · اشتراک · صورتحساب اشتراک · مصرف و سقف‌ها · واردات داده · صادرات داده |

## Permissions

Visibility reuses the `can_*` flags from `merchant_permissions` (computed from the
request's `StoreMembership`). A tab is rendered only if one of its flags is true; a
sidebar section only if at least one of its tabs is; its link goes to its first
permitted tab. Views keep enforcing their own `permission_required` checks —
navigation only decides what to *show*.

## Active state

Decided from the resolved URL name (longest/most specific match wins), refined by a
few query-string rules (`?kind=`, `?section=`, `?panel=`), with the views' legacy
`active_page` as a last-resort fallback. Detail/edit/POST-redisplay pages therefore
light up the tab of the list they belong to. `test_admin_navigation.py` asserts that
**every** named dashboard route belongs to a section.

## Placement decisions / routes that don't fit cleanly

* **تنظیمات مالی** is listed once, under تنظیمات (`settings?section=finance`), not
  duplicated under فاکتورها و مالی. It also owns `gift-wrap-*` (linked from that page).
* **واردات / صادرات داده** are two tabs, not one: `export-list` had no in-page entry
  point other than the old sidebar link, and exports have a different permission.
* **صورتحساب اشتراک** (`billing-*`, the merchant's invoices *from RastiSi*) is a
  separate tab under تنظیمات next to اشتراک — not under فاکتورها و مالی, which is
  about the merchant's own orders/payments. `billing-overview` is only reachable from
  the billing pages themselves otherwise.
* **اعلان‌ها و پیام‌ها** (`notification-*`) sits under بازاریابی; **پیامک** (connection,
  logs, outbox) under تنظیمات.
* **ادیتور قدیمی**, `customer-tag-list`, `notification-history`, `sms-log-list`,
  `sms-outbox-list` and `gift-wrap-products` are not tabs; they stay reachable from
  their parent screens and from the command palette.
* The Settings screen keeps its own in-page pill navigation (general / finance /
  delivery-payment / …). It overlaps with the new tabs (finance, sms) and could be
  trimmed in a follow-up.
* Removed: product-count badge on the sidebar (it moved onto the «همه کالاها» tab) and
  the old collapsible-group JS (`sidebarNav`). The pending-orders badge stays on
  سفارش‌ها.
