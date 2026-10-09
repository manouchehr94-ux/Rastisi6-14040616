"""Merchant-admin information architecture — the single source of truth.

Two-level model:

* **Level 1** — the main sidebar: nine major work areas (``SECTIONS``).
* **Level 2** — section tabs: the related screens of the *current* section,
  rendered as a horizontal tab bar next to the page header.

Everything the shell renders (sidebar, tab bar, the ``Ctrl + K`` command
palette's destinations and path labels) is derived from this module, so the
three can never drift apart. Nothing here owns a URL, a view or a permission:

* every destination is an existing ``dashboard:*`` route (``Tab.url_name``);
* visibility reuses the ``can_*`` flags that
  ``apps.dashboard.context_processors.merchant_permissions`` already computes
  from the request's ``StoreMembership`` — a tab (and a whole section whose
  tabs are all hidden) is never rendered for a user who cannot open it.
  The views keep enforcing permissions themselves; this module only decides
  what to *show*;
* which tab/section is "active" is decided from the resolved URL name (plus a
  few query-string refinements), so detail/edit/POST-redisplay pages light up
  the tab of the list they belong to without the views knowing anything.

Pure Python — no database access — so it is cheap and trivially testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Optional

from django.urls import reverse

# Score weights for the URL-name matcher (higher wins).
_EXACT = 1000
_GET_BONUS = 500


@dataclass(frozen=True)
class Match:
    """One way a tab claims a resolved URL name.

    ``names``    exact ``url_name`` values.
    ``prefixes`` ``url_name`` prefixes (longest prefix wins across tabs).
    ``get``      required query-string values, ``{param: (allowed, ...)}``.
    ``get_not``  query-string values that disqualify the match.
    """

    names: tuple = ()
    prefixes: tuple = ()
    get: Optional[Mapping[str, tuple]] = None
    get_not: Optional[Mapping[str, tuple]] = None


@dataclass(frozen=True)
class Tab:
    key: str
    label: str
    url_name: str
    perms: tuple = ()  # any-of context flags; empty = always visible
    query: str = ""  # e.g. "?kind=campaigns"
    matches: tuple = ()
    pages: tuple = ()  # legacy ``active_page`` values — last-resort fallback
    pages_first: tuple = ()  # ``active_page`` values that outrank URL names
    keywords: str = ""  # extra command-palette search terms
    badge: str = ""  # context variable holding a count to show (hidden if 0)


@dataclass(frozen=True)
class Section:
    key: str
    label: str
    tabs: tuple
    icon: str = ""  # key of the sidebar glyph (see ``_admin_sidebar.html``)
    badge: str = ""  # context variable holding a count to show on the sidebar


@dataclass(frozen=True)
class PaletteExtra:
    """Command-palette-only destinations (deep links that are not tabs)."""

    title: str
    path: str
    url_name: str
    query: str = ""
    perms: tuple = ()
    keywords: str = ""
    icon: str = "↗"


def _m(*names, prefix=(), get=None, get_not=None):
    if isinstance(prefix, str):
        prefix = (prefix,)
    return Match(names=tuple(names), prefixes=tuple(prefix), get=get, get_not=get_not)


# Tabs whose visibility also depends on a feature switch, not only on the member's permissions (they are hidden for
# everyone while the feature is off — e.g. the RastiChat links, see apps.chat_integration.context_processors).
FEATURE_GATED_FLAGS = frozenset({"can_chat_customers", "can_chat_platform_support"})

SECTIONS: tuple = (
    Section(
        key="dashboard", label="داشبورد", icon="grid",
        tabs=(
            Tab("dashboard", "نمای کلی", "dashboard",
                matches=(_m("dashboard", "sales-chart"),), pages=("dashboard",),
                keywords="خانه داشبورد فروش امروز سفارش امروز"),
        ),
    ),
    Section(
        key="orders", label="سفارش‌ها", icon="bag", badge="nav_pending_order_count",
        tabs=(
            Tab("orders", "همه سفارش‌ها", "order-list", perms=("can_view_orders",),
                matches=(_m(prefix="order-"),), pages=("orders",),
                keywords="سفارش سفارشات سفارش جدید پردازش order"),
            Tab("returns", "مرجوعی‌ها", "return-list", perms=("can_view_returns",),
                matches=(_m(prefix="return-"),), pages=("returns",),
                keywords="مرجوعی بازگشت کالا مرجوع return"),
        ),
    ),
    Section(
        key="products", label="کالاها", icon="box",
        tabs=(
            Tab("products", "همه کالاها", "product-list", perms=("can_view_products",),
                matches=(_m(prefix="product-"),), pages=("products",), badge="nav_product_count",
                keywords="کالا محصول محصولات ویرایش محصول product"),
            Tab("categories", "دسته‌بندی‌ها", "category-list", perms=("can_manage_categories",),
                matches=(_m(prefix="category-"),), pages=("categories",),
                keywords="دسته دسته بندی گروه بندی کالاها category"),
            Tab("brands", "برندها", "brand-list", perms=("can_manage_brands",),
                matches=(_m(prefix="brand-"),), pages=("brands",), keywords="برند مارک brand"),
            Tab("attributes", "ویژگی‌ها", "attribute-list", perms=("can_manage_attributes",),
                matches=(_m(prefix="attribute-"),), pages=("attributes",),
                keywords="ویژگی مشخصات attribute"),
            Tab("inventory", "موجودی", "inventory-list", perms=("can_manage_inventory",),
                matches=(_m(prefix="inventory-"),), pages=("inventory",),
                keywords="انبار موجودی دفتر موجودی stock inventory"),
            Tab("warehouses", "انبارها", "warehouse-list", perms=("can_view_warehouses",),
                matches=(_m(prefix="warehouse-"),), pages=("warehouses",),
                keywords="انبار انبارها warehouse"),
            Tab("reservations", "رزرو موجودی", "reservation-list", perms=("can_view_reservations",),
                matches=(_m(prefix="reservation-"),), pages=("reservations",),
                keywords="رزرو موجودی رزرو سفارش reservation"),
            Tab("transfers", "انتقال انبار", "transfer-list", perms=("can_view_transfers",),
                matches=(_m(prefix="transfer-"),), pages=("transfers",),
                keywords="انتقال انبار حواله transfer"),
        ),
    ),
    Section(
        key="finance", label="فاکتورها و مالی", icon="receipt",
        tabs=(
            Tab("invoices", "فاکتورها", "invoice-list", perms=("can_view_orders",),
                matches=(_m(prefix="invoice-"),), pages=("invoices",),
                keywords="فاکتور صورتحساب invoice"),
            Tab("payments", "پرداخت‌ها", "payment-list", perms=("can_view_orders",),
                matches=(_m("payment-list", "payment-table"),), pages=("payments",),
                keywords="پرداخت تراکنش درگاه payment"),
            Tab("payment-reconciliations", "تطبیق پرداخت‌ها", "payment-reconciliations",
                perms=("can_view_orders",),
                matches=(_m(prefix="payment-reconciliation"),), pages=("payment-reconciliations",),
                keywords="تطبیق پرداخت مغایرت reconciliation"),
        ),
    ),
    Section(
        key="customers", label="مشتریان", icon="users",
        tabs=(
            Tab("customers", "مشتریان", "customer-list", perms=("can_view_customers",),
                matches=(_m(prefix="customer-"),), pages=("customers",),
                keywords="مشتری مشتریان برچسب مشتری customer"),
            Tab("segments", "سگمنت‌ها", "segment-list", perms=("can_view_segments",),
                matches=(_m(prefix="segment-"),), pages=("segments",),
                keywords="سگمنت بخش بندی مشتریان segment"),
            Tab("chat-customers", "گفتگوی مشتریان", "chat-customers", perms=("can_chat_customers",),
                matches=(_m("chat-customers"),), keywords="گفتگو چت پیام مشتری پشتیبانی آنلاین chat"),
            Tab("chat-support", "پشتیبانی پلتفرم", "chat-support", perms=("can_chat_platform_support",),
                matches=(_m("chat-support"),), keywords="گفتگو پشتیبانی پلتفرم راستی‌سی چت support"),
        ),
    ),
    Section(
        key="marketing", label="بازاریابی", icon="target",
        tabs=(
            Tab("campaigns", "کمپین‌ها", "campaign-list", perms=("can_view_coupons",),
                query="?kind=campaigns",
                matches=(_m("campaign-list", get={"kind": ("campaigns",)}), _m(prefix="campaign-")),
                pages=("campaigns",), pages_first=("campaigns",),
                keywords="کمپین کمپین تخفیف تخفیف هوشمند campaign"),
            Tab("occasions", "مناسبت‌ها و هدیه‌ها", "campaign-list", perms=("can_view_coupons",),
                query="?kind=occasions",
                matches=(_m("campaign-list", get={"kind": ("occasions",)}),),
                pages=("occasions",), pages_first=("occasions",),
                keywords="تولد مناسبت هدیه سالگرد birthday occasion"),
            Tab("coupons", "کدهای تخفیف", "coupon-list", perms=("can_view_coupons",),
                matches=(_m(prefix="coupon-"),), pages=("coupons",),
                keywords="تخفیف کوپن کد تخفیف جشنواره coupon"),
            Tab("notifications", "اعلان‌ها و پیام‌ها", "notification-templates",
                perms=("can_manage_settings",),
                matches=(_m(prefix="notification-"),), pages=("notifications",),
                keywords="اعلان پیام قالب پیام پیامک ایمیل اطلاع رسانی notification"),
        ),
    ),
    Section(
        key="store", label="فروشگاه", icon="palette",
        tabs=(
            Tab("appearance", "ظاهر و طراحی", "storefront-builder-r4-editor",
                perms=("can_manage_storefront_layout",), query="?panel=appearance",
                matches=(
                    _m("storefront-builder-r4-editor", get={"panel": ("appearance",)}),
                    _m("storefront-builder-appearance", "storefront-builder-apply-preset",
                       "storefront-builder-appearance-field-reset"),
                ),
                keywords="ظاهر رنگ پالت فونت استایل appearance palette"),
            Tab("builder", "سازنده فروشگاه", "storefront-builder-r4-editor",
                perms=("can_manage_storefront_layout",),
                matches=(_m(prefix="storefront-builder-"),), pages=("storefront_builder",),
                keywords="سازنده storefront builder طراحی صفحه سکشن section هیرو ادیتور"),
            Tab("templates", "قالب‌های آماده", "storefront-builder-templates",
                perms=("can_manage_storefront_layout",),
                matches=(_m("storefront-builder-templates", "storefront-builder-template-live-preview",
                            "storefront-builder-r4-switch-template"),),
                keywords="قالب تم template ready آماده"),
            Tab("collections", "کالکشن‌ها", "collection-list", perms=("can_manage_collections",),
                matches=(_m(prefix="collection-"),), pages=("collections",),
                keywords="کالکشن مجموعه محصولات collection"),
            Tab("content", "محتوا", "page-list", perms=("can_manage_content",),
                matches=(_m(prefix="page-"),), pages=("pages",),
                keywords="محتوا صفحه صفحات بلاگ content"),
            Tab("homepage", "صفحه اصلی", "hero-list", perms=("can_manage_content",),
                matches=(_m(prefix=("hero-", "banner-")),), pages=("homepage",),
                keywords="صفحه اصلی اسلاید بنر هیرو homepage banner slider"),
            Tab("menus", "منوها", "menu-list", perms=("can_manage_content",),
                matches=(_m(prefix="menu-"),), pages=("menus",),
                keywords="منو مگامنو منوها navigation menu"),
            Tab("footer", "فوتر", "footer-settings", perms=("can_manage_content",),
                matches=(_m(prefix="footer-"),), pages=("footer",),
                keywords="فوتر پایین صفحه نماد اعتماد footer"),
            Tab("social", "شبکه‌های اجتماعی", "social-link-list", perms=("can_manage_content",),
                matches=(_m(prefix="social-link-"),), pages=("social_links",),
                keywords="شبکه اجتماعی اینستاگرام تلگرام social"),
        ),
    ),
    Section(
        key="reports", label="گزارش‌ها", icon="chart",
        tabs=(
            Tab("reports", "گزارش‌های حرفه‌ای", "report-list", perms=("can_view_reports",),
                matches=(_m(prefix="report-"),), pages=("reports",),
                keywords="گزارش آمار فروش تحلیل report"),
            Tab("audit-log", "گزارش رخدادها", "audit-log-list", perms=("can_view_audit_log",),
                matches=(_m(prefix="audit-log-"),), pages=("audit-log",),
                keywords="رخداد لاگ تاریخچه تغییرات audit log"),
        ),
    ),
    Section(
        key="settings", label="تنظیمات", icon="gear",
        tabs=(
            Tab("settings-general", "تنظیمات عمومی", "settings", perms=("can_manage_settings",),
                matches=(
                    _m("settings", get_not={"section": ("finance", "sms")}),
                    _m(prefix="settings-"),
                ),
                pages=("settings",),
                keywords="تنظیمات دامنه پرداخت اطلاعات فروشگاه صنف درگاه یکپارچه‌سازی settings"),
            Tab("shipping", "ارسال", "shipping-setup", perms=("can_view_shipping_settings",),
                matches=(_m(prefix="shipping-"),), pages=("shipping",),
                keywords="ارسال پست روش ارسال هزینه ارسال shipping"),
            Tab("tax", "مالیات", "tax-settings", perms=("can_view_tax_settings",),
                matches=(_m(prefix="tax-"),), pages=("tax",),
                keywords="مالیات ارزش افزوده tax"),
            Tab("settings-finance", "تنظیمات مالی", "settings", perms=("can_manage_settings",),
                query="?section=finance",
                matches=(
                    _m("settings", get={"section": ("finance",)}),
                    _m("settings-finance", "settings-gift-wrap", "settings-order-expiry",
                       "gift-wrap-products", "gift-wrap-product-update"),
                ),
                keywords="مالی تنظیمات مالی کادوپیچی بسته بندی هدیه انقضای سفارش finance gift wrap"),
            Tab("sms", "پیامک", "settings", perms=("can_manage_settings",), query="?section=sms",
                matches=(
                    _m("settings", get={"section": ("sms",)}),
                    _m(prefix=("settings-sms", "settings-smsrasti", "sms-")),
                ),
                keywords="پیامک sms اس ام اس اتصال پیامک پنل پیامکی ارسال آزمایشی"),
            Tab("staff", "اعضای تیم", "staff-list", perms=("can_manage_staff",),
                matches=(_m(prefix="staff-"),), pages=("staff",),
                keywords="اعضا تیم کارمند نقش دسترسی staff"),
            Tab("subscription", "اشتراک", "subscription-overview", perms=("can_view_subscription",),
                matches=(_m(prefix="subscription-"),), pages=("subscription",),
                keywords="اشتراک پلن ارتقا subscription plan"),
            Tab("billing", "صورتحساب اشتراک", "billing-overview", perms=("can_view_billing",),
                matches=(_m(prefix="billing-"),), pages=("billing",),
                keywords="صورتحساب فاکتور اشتراک پرداخت اشتراک billing"),
            Tab("usage", "مصرف و سقف‌ها", "usage-overview", perms=("can_view_usage",),
                matches=(_m(prefix="usage-"),), pages=("usage",),
                keywords="مصرف سقف محدودیت usage limits"),
            Tab("imports", "ورود اطلاعات", "import-list", perms=("can_view_imports",),
                matches=(_m(prefix="import-"),), pages=("imports",),
                keywords="ورود اطلاعات اکسل آپلود بارگذاری فایل ورود کالا موجودی import"),
            Tab("exports", "خروج اطلاعات", "export-list", perms=("can_view_exports",),
                matches=(_m(prefix="export-"),), pages=("exports",),
                keywords="خروج اطلاعات خروجی اکسل دانلود دریافت فایل export"),
        ),
    ),
)

# Deep links for the command palette that are not tabs themselves.
PALETTE_EXTRAS: tuple = (
    PaletteExtra("لوگو", "فروشگاه ← ظاهر و طراحی ← هدر ← لوگو", "storefront-builder-r4-editor",
                 "?panel=header&focus=logo", ("can_manage_storefront_layout",),
                 "لوگو آرم نشان فروشگاه logo header", "R"),
    PaletteExtra("هدر فروشگاه", "فروشگاه ← ظاهر و طراحی ← هدر", "storefront-builder-r4-editor",
                 "?panel=header", ("can_manage_storefront_layout",),
                 "هدر سربرگ جستجو سبد حساب کاربری header", "⌃"),
    PaletteExtra("فوتر فروشگاه", "فروشگاه ← ظاهر و طراحی ← فوتر", "storefront-builder-r4-editor",
                 "?panel=footer", ("can_manage_storefront_layout",),
                 "فوتر پایین صفحه شبکه اجتماعی footer", "⌄"),
    PaletteExtra("گزارش پیامک‌ها", "تنظیمات ← پیامک ← گزارش ارسال", "sms-log-list", "",
                 ("can_manage_settings",),
                 "پیامک sms گزارش لاگ پیامک ارسال شده ناموفق retry", "≡"),
    PaletteExtra("صندوق خروجی پیامک", "تنظیمات ← پیامک ← صندوق خروجی", "sms-outbox-list", "",
                 ("can_manage_settings",),
                 "پیامک sms صندوق خروجی صف ارسال outbox", "⇢"),
    PaletteExtra("تاریخچه اعلان‌ها", "بازاریابی ← اعلان‌ها و پیام‌ها ← تاریخچه", "notification-history", "",
                 ("can_manage_settings",), "اعلان تاریخچه پیام ارسال شده", "≡"),
    PaletteExtra("کادوپیچی کالاها", "تنظیمات ← تنظیمات مالی ← کادوپیچی", "gift-wrap-products", "",
                 ("can_manage_settings",), "کادوپیچی کادو بسته بندی هدیه gift wrap", "🎁"),
    PaletteExtra("برچسب‌های مشتری", "مشتریان ← مشتریان ← برچسب‌ها", "customer-tag-list", "",
                 ("can_view_customers",), "برچسب تگ مشتری tag", "#"),
    PaletteExtra("ادیتور قدیمی فروشگاه", "فروشگاه ← سازنده فروشگاه ← ادیتور قدیمی",
                 "storefront-builder-editor", "", ("can_manage_storefront_layout",),
                 "ادیتور قدیمی تنظیمات پیشرفته legacy editor", "✎"),
)

# Dashboard URL names that are not navigable pages (auth/handoff plumbing).
NON_NAVIGATIONAL_URL_NAMES = frozenset({"login", "handoff", "exit-support-mode"})


# --------------------------------------------------------------------------- #
# Resolution
# --------------------------------------------------------------------------- #

def _get_value(get, param):
    if get is None:
        return None
    if hasattr(get, "get"):
        value = get.get(param)
        if isinstance(value, (list, tuple)):
            return value[0] if value else None
        return value
    return None


def _get_ok(match: Match, get) -> bool:
    if match.get:
        for param, allowed in match.get.items():
            if _get_value(get, param) not in allowed:
                return False
    if match.get_not:
        for param, banned in match.get_not.items():
            if _get_value(get, param) in banned:
                return False
    return True


def _score(match: Match, url_name: str, get) -> int:
    if not url_name or not _get_ok(match, get):
        return 0
    best = 0
    if url_name in match.names:
        best = _EXACT + len(url_name)
    for prefix in match.prefixes:
        if url_name.startswith(prefix):
            best = max(best, len(prefix))
    if best and match.get:
        best += _GET_BONUS
    return best


def resolve_active(url_name: str, get=None, active_page: str = "") -> tuple:
    """Return ``(section_key, tab_key)`` for a resolved dashboard page, or
    ``(None, None)`` if it belongs to no navigable section.

    Order: (1) ``pages_first`` — a view that explicitly declared its
    ``active_page`` for a tab whose URL it shares with a sibling (campaigns vs
    occasions); (2) best URL-name match; (3) legacy ``active_page`` fallback.
    """
    if active_page:
        for section in SECTIONS:
            for tab in section.tabs:
                if active_page in tab.pages_first:
                    return section.key, tab.key
    best = (0, None, None)
    for section in SECTIONS:
        for tab in section.tabs:
            for match in tab.matches:
                score = _score(match, url_name, get)
                if score > best[0]:
                    best = (score, section.key, tab.key)
    if best[1]:
        return best[1], best[2]
    if active_page:
        for section in SECTIONS:
            for tab in section.tabs:
                if active_page in tab.pages:
                    return section.key, tab.key
    return None, None


def tab_href(tab: Tab) -> str:
    return reverse(f"dashboard:{tab.url_name}") + tab.query


def _tab_visible(tab: Tab, flags: Mapping[str, object]) -> bool:
    return not tab.perms or any(bool(flags.get(flag)) for flag in tab.perms)


def _count(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


@dataclass
class NavTab:
    key: str
    label: str
    href: str
    active: bool = False
    badge: int = 0


@dataclass
class NavSection:
    key: str
    label: str
    href: str
    icon: str
    active: bool = False
    badge: int = 0
    tabs: list = field(default_factory=list)


@dataclass
class Navigation:
    sections: list
    active_section: Optional[NavSection]
    active_tab: Optional[NavTab]

    @property
    def show_tabs(self) -> bool:
        """A tab bar for a single destination would be noise."""
        return bool(self.active_section and len(self.active_section.tabs) > 1)


def build_navigation(
    flags: Mapping[str, object],
    url_name: str = "",
    get=None,
    active_page: str = "",
    counts: Optional[Mapping[str, object]] = None,
) -> Navigation:
    """Build the permission-filtered navigation model for one request.

    ``flags`` is the ``can_*`` mapping from the ``merchant_permissions``
    context processor; ``counts`` supplies badge numbers by variable name.
    """
    counts = counts or {}
    active_section_key, active_tab_key = resolve_active(url_name, get, active_page)
    sections, active_section, active_tab = [], None, None
    for section in SECTIONS:
        tabs = []
        for tab in section.tabs:
            if not _tab_visible(tab, flags):
                continue
            nav_tab = NavTab(
                key=tab.key, label=tab.label, href=tab_href(tab),
                active=(section.key == active_section_key and tab.key == active_tab_key),
                badge=_count(counts.get(tab.badge)) if tab.badge else 0,
            )
            tabs.append(nav_tab)
        if not tabs:
            continue
        nav_section = NavSection(
            key=section.key, label=section.label, href=tabs[0].href, icon=section.icon,
            active=(section.key == active_section_key),
            badge=_count(counts.get(section.badge)) if section.badge else 0,
            tabs=tabs,
        )
        sections.append(nav_section)
        if nav_section.active:
            active_section = nav_section
            active_tab = next((t for t in tabs if t.active), None)
    return Navigation(sections=sections, active_section=active_section, active_tab=active_tab)


@dataclass
class PaletteItem:
    title: str
    path: str
    href: str
    keywords: str
    icon: str


def build_palette(flags: Mapping[str, object]) -> list:
    """Permission-filtered command-palette destinations, with ``Section ←
    Tab`` path labels generated from the same IA as the sidebar."""
    items = []
    for section in SECTIONS:
        for tab in section.tabs:
            if not _tab_visible(tab, flags):
                continue
            if section.key == "dashboard":
                path = section.label
            elif tab.label == section.label:
                path = section.label
            else:
                path = f"{section.label} ← {tab.label}"
            items.append(PaletteItem(tab.label, path, tab_href(tab), tab.keywords, "◦"))
    for extra in PALETTE_EXTRAS:
        if extra.perms and not any(bool(flags.get(flag)) for flag in extra.perms):
            continue
        items.append(PaletteItem(
            extra.title, extra.path, reverse(f"dashboard:{extra.url_name}") + extra.query,
            extra.keywords, extra.icon,
        ))
    return items
