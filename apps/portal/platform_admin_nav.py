"""منبعِ یگانه‌ی ناوبریِ پنلِ مالکِ پلتفرم.

همه‌ی صفحه‌هایِ ``portal/platform_admin`` یک سایدبارِ واحد را از همین تعریف می‌گیرند (تگِ ``{% pa_sidebar %}``)؛ هیچ صفحه‌ای
سایدبارِ جدا ندارد. صفحه‌یِ فعال از ``request.resolver_match.url_name`` تشخیص داده می‌شود (نه از متغیرِ دستیِ هر view)، پس صفحه‌هایِ
زیرمجموعه (ویرایش/جزئیات) هم آیتمِ والدشان را فعال می‌کنند.

آیتم‌هایِ ``optional=True`` فقط وقتی نمایش داده می‌شوند که نامِ URL در این شاخه وجود داشته باشد (برایِ ماژول‌هایِ مالیِ PR #40 که
هنوز ادغام نشده‌اند)؛ این‌گونه ادغامِ آن‌ها نیازی به ویرایشِ ناوبری ندارد."""

from dataclasses import dataclass, field

from django.urls import NoReverseMatch, reverse

NS = "portal_platform_admin"


@dataclass(frozen=True)
class NavItem:
    label: str
    url_name: str
    icon: str = "dot"
    also: tuple = ()          # نامِ URLهایِ زیرمجموعه که همین آیتم را فعال می‌کنند
    optional: bool = False

    @property
    def matches(self):
        return {self.url_name, *self.also}


@dataclass(frozen=True)
class NavGroup:
    key: str
    label: str
    icon: str
    items: tuple = field(default_factory=tuple)


NAV = (
    NavGroup("overview", "نمای کلی", "home", (
        NavItem("داشبورد", "home", "home", also=("inbox-home", "inbox-preferences")),
    )),
    NavGroup("customers", "فروشگاه‌ها و کاربران", "store", (
        NavItem("فروشگاه‌ها", "stores", "store", also=("store-detail",)),
        NavItem("کاربران", "users", "users", also=("user-detail",)),
        NavItem("دامنه‌ها", "domains", "globe"),
        NavItem("صنف‌ها و قالب‌ها", "industries", "layers", also=("industry-detail",)),
    )),
    NavGroup("pricing", "اشتراک و قیمت‌گذاری", "tag", (
        NavItem("دوره‌ی آزمایشی (Trial)", "trial-settings", "clock"),
        NavItem("پلن‌ها و نسخه‌ها", "plans", "tag", also=("plan-add", "plan-edit", "plan-migration")),
        NavItem("کاتالوگِ قابلیت‌ها", "features", "puzzle", also=("feature-add", "feature-edit")),
        NavItem("تخصیصِ قابلیت به پلن", "assignment-matrix", "grid"),
        NavItem("محتوایِ صفحه‌ی تعرفه", "pricing-content", "file"),
        NavItem("اشتراکِ فروشگاه‌ها", "subscriptions", "repeat"),
    )),
    NavGroup("finance", "مالی و پرداخت", "card", (
        NavItem("پرداخت‌ها و فاکتورها", "payments", "card", also=("payment-invoice-detail", "payment-manual-add")),
        # ماژول‌هایِ PR #40 (فقط اگر در این شاخه ثبت شده باشند):
        NavItem("درگاه‌هایِ پرداختِ پلتفرم", "payment-gateways", "card", also=("billing-zibal-settings",), optional=True),
        NavItem("تراکنش‌هایِ پلتفرم", "payment-transactions", "list", optional=True),
        NavItem("تطبیقِ پرداخت‌ها", "payment-reconciliation", "check", optional=True),
        NavItem("ادعایِ پرداختِ دستی", "manual-claims", "file", also=("manual-claim-detail",), optional=True),
        NavItem("خریدِ بسته‌یِ پیامک", "sms-purchases", "message", optional=True),
    )),
    NavGroup("sms", "پیامک", "message", (
        NavItem("شرکت‌هایِ پیامکی", "sms-providers", "settings", also=("sms-settings",)),
        NavItem("قالب‌هایِ پیامک", "sms-templates", "file", also=("sms-template-edit",)),
        NavItem("بسته‌هایِ پیامک", "sms-packages", "tag", also=("sms-package-add", "sms-package-edit")),
        NavItem("اعتبارِ فروشگاه‌ها", "sms-credits", "card"),
        NavItem("پیامک‌هایِ ارسالی", "sms-messages", "list", also=("sms-logs",)),
    )),
    NavGroup("notifications", "اعلان‌ها (پیامک و ایمیل)", "bell", (
        NavItem("رویدادها و قالب‌ها", "notification-catalog", "bell", also=("notification-platform-template",)),
        NavItem("هویتِ فرستنده‌یِ ایمیل", "notification-senders", "shield"),
        NavItem("ارسال‌ها و شکست‌ها", "notification-delivery", "list"),
        NavItem("تاریخچه‌یِ تغییرات", "notification-audit", "clock"),
    )),
    NavGroup("site", "سایتِ عمومی", "image", (
        NavItem("متن و ظاهر", "public-site", "type", also=("public-site-edit",)),
        NavItem("تصاویر", "public-photos", "image", also=("public-photo-edit",)),
    )),
    NavGroup("system", "سیستم", "shield", (
        NavItem("گزارشِ رخدادها", "audit-log", "shield"),
        NavItem("تنظیماتِ پلتفرم", "configuration", "settings"),
    )),
)


def _reverse(url_name):
    try:
        return reverse(f"{NS}:{url_name}")
    except NoReverseMatch:
        return None


def build_nav(current_url_name):
    """ساختارِ آماده‌یِ رندر: گروه‌ها با آیتم‌هایِ دارایِ URL، وضعیتِ فعال و گسترده. آیتمِ بدونِ URL (optional) حذف می‌شود."""
    groups, active_item, active_group = [], None, None
    for group in NAV:
        items = []
        for item in group.items:
            url = _reverse(item.url_name)
            if url is None:
                if item.optional:
                    continue
                raise NoReverseMatch(f"nav item {item.url_name!r} has no URL")
            is_active = current_url_name in item.matches
            row = {"label": item.label, "url": url, "icon": item.icon, "active": is_active, "name": item.url_name}
            items.append(row)
            if is_active:
                active_item, active_group = row, group
        if items:
            groups.append({"key": group.key, "label": group.label, "icon": group.icon, "items": items,
                           "open": any(i["active"] for i in items), "single": len(items) == 1})
    crumb = None
    if active_item is not None:
        crumb = {"group": active_group.label, "item": active_item["label"], "url": active_item["url"]}
    return {"groups": groups, "breadcrumb": crumb}


def all_nav_url_names():
    return {name for g in NAV for i in g.items for name in i.matches}
