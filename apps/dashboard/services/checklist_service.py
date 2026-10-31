"""چک‌لیست راه‌اندازی فروشگاه (Store Setup Checklist) — تشخیص خودکار وضعیت
تکمیل هر مرحله مستقیماً از داده‌ی واقعیِ سیستم، بدون هیچ فیلد/مدلِ جداگانه‌ی
«انجام‌شده/نشده». هر بررسی همان مدل/سرویسی را می‌خواند که خودِ صفحه‌ی مربوطه
برای نمایش وضعیتش استفاده می‌کند (ShopSettings، Category، Attribute، Brand،
Product، ProductImage، ProductVariant، ShippingMethod، PaymentGatewayConfig،
TaxRate، StoreDomain، StoreIndustryInstallation، publication_service) — این
ماژول چیزی تولید یا ذخیره نمی‌کند، فقط می‌پرسد.

ترتیبِ مراحلِ کاتالوگ (صنف → قالب صنف → گروه‌های کالا → دسته‌بندی/زیردسته →
ویژگی‌ها → برندها → اولین کالا → تصاویر → تنوع‌ها → موجودی → انتشار کالا)
عمداً همان زنجیره‌ی واقعیِ پیش‌نیازیِ ساختِ یک کالا را دنبال می‌کند — «اولین
کالا» هرگز نباید پیش از پیش‌نیازهایش (دسته‌بندی/ویژگی/برند) نمایش داده شود."""

from dataclasses import dataclass
from typing import Callable

from django.conf import settings as django_settings
from django.urls import reverse

from apps.catalog.models import Attribute, Brand, Category, Product, ProductImage, ProductVariant, StoreIndustryInstallation
from apps.core.models import ShopSettings, ShopSettingsNotProvisionedError
from apps.orders.models import PaymentGatewayConfig, ShippingMethod
from apps.stores.models import StoreDomain
from apps.stores.services.publication_service import is_publicly_visible

#: مقادیرِ پیش‌فرضِ رنگِ ShopSettings (دقیقاً همان‌هایی که در تعریفِ مدل
#: آمده‌اند) — «تم» وقتی تکمیل‌شده حساب می‌شود که دست‌کم یکی از رنگ‌ها از
#: پیش‌فرضش تغییر کرده باشد، چون فیلدِ صریحِ «تم سفارشی‌سازی شد؟» وجود ندارد.
_DEFAULT_COLORS = {
    "primary_color": "#6D28D9",
    "accent_color": "#FF4D77",
    "secondary_color": "#7C3AED",
    "background_color": "#F7F5FC",
    "surface_color": "#FFFFFF",
    "text_color": "#241C3A",
    "muted_text_color": "#8B86A3",
}


def _shop_settings(store):
    try:
        return ShopSettings.load(store=store)
    except ShopSettingsNotProvisionedError:
        return None


def _platform_url(request, path):
    """آدرسِ مطلقِ روی میزبانِ پرتالِ مالک — همان الگویی که
    ``apps.dashboard.context_processors.platform_link`` برایِ لینکِ «بازگشت
    به راستیسی» استفاده می‌کند؛ چون این صفحات (اتصالِ دامنه، انتشارِ
    فروشگاه) در اپ ``apps.portal`` هستند، نه در پنلِ مدیریتِ همین Store."""
    return f"{request.scheme}://{django_settings.RASTISI_PLATFORM_PRIMARY_HOST}{path}"


def _store_information_complete(store, shop):
    return bool(shop and shop.description.strip())


def _active_industry_installation(store):
    """نصبِ صنفِ این Store، فقط اگر واقعاً به یک ``IndustryTemplate`` فعال
    وصل باشد — نگاه کنید به گزارشِ باگ: پیش از این، این دو مرحله صرفاً از
    روی عبورِ ``onboarding_stage`` از INDUSTRY تشخیص داده می‌شدند، که
    می‌توانست بدونِ هیچ ``StoreIndustryInstallation``ای هم ✅ نشان دهد. صرفِ
    وجودِ دسته‌بندی/ویژگی/برند/کالا هم عمداً این‌جا خوانده نمی‌شود — تنها
    منبعِ حقیقتِ «صنف نصب شده؟» همین رکورد است."""
    return (
        StoreIndustryInstallation.objects.select_related("industry_template")
        .filter(store=store, industry_template__is_active=True)
        .first()
    )


def _industry_complete(store, shop):
    """«انتخاب صنف» فقط با وجودِ یک نصبِ واقعی (به قالبِ فعال) تکمیل حساب
    می‌شود — نه صرفِ رد یا عبور از مرحله‌ی آنبوردینگ."""
    return _active_industry_installation(store) is not None


def _industry_template_complete(store, shop):
    """«نصب قالب صنف» فقط وقتی تکمیل است که وضعیتِ نصب واقعاً
    ``COMPLETED`` باشد — نصبِ ``FAILED`` (یا نبودِ هیچ نصبی) هرگز این مرحله
    را تکمیل‌شده نشان نمی‌دهد."""
    installation = _active_industry_installation(store)
    return installation is not None and installation.status == StoreIndustryInstallation.Status.COMPLETED


def _product_groups_complete(store, shop):
    """«گروه‌های کالا» = دسته‌بندیِ سطحِ اول (بدون والد) — نگاه کنید به
    برچسبِ ناوبریِ موجود «گروه‌بندی کالاها» که دقیقاً همین Category را نشان
    می‌دهد."""
    return Category.objects.filter(store=store, parent__isnull=True).exists()


def _product_subcategories_complete(store, shop):
    """کالا فقط می‌تواند به یک زیردسته (نه دسته‌ی سطحِ اول) وصل شود —
    نگاه کنید به ``leaf_categories`` در catalog_admin_service — پس این
    همان پیش‌نیازِ واقعیِ «اولین کالا» ست، نه صرفِ وجودِ هر دسته‌ای."""
    return Category.objects.filter(store=store, parent__isnull=False).exists()


def _attributes_complete(store, shop):
    return Attribute.objects.filter(store=store).exists()


def _brands_complete(store, shop):
    return Brand.objects.filter(store=store).exists()


def _product_images_complete(store, shop):
    return ProductImage.objects.filter(product__store=store).exists()


def _variants_complete(store, shop):
    return ProductVariant.objects.filter(store=store).exists()


def _inventory_complete(store, shop):
    return Product.objects.filter(store=store, stock__gt=0, is_draft_placeholder=False).exists()


def _product_publish_complete(store, shop):
    return Product.objects.filter(
        store=store, status=Product.Status.ACTIVE, is_draft_placeholder=False,
    ).exists()


def _contact_complete(store, shop):
    return bool(shop and (shop.contact_phone.strip() or shop.contact_email.strip()))


def _logo_complete(store, shop):
    return bool(shop and shop.logo)


def _theme_complete(store, shop):
    if shop is None:
        return False
    return any(getattr(shop, field) != default for field, default in _DEFAULT_COLORS.items())


def _first_product_complete(store, shop):
    return Product.objects.filter(store=store, is_draft_placeholder=False).exists()


def _shipping_complete(store, shop):
    """«حداقل یک روش ارسال یا گزینه‌ی دریافتِ حضوریِ فعال» — پیش از این،
    صرفِ وجودِ هر ``ShippingMethod``ای (حتی غیرِفعال) کافی بود؛ اکنون فقط
    روش‌های واقعاً ``is_active=True`` شمرده می‌شوند."""
    return ShippingMethod.objects.filter(store=store, is_active=True).exists()


def _payment_gateway_complete(store, shop):
    return PaymentGatewayConfig.objects.filter(store=store, is_active=True).exists()


def _tax_complete(store, shop):
    """مالیات اختیاری است، اما مدیر باید صراحتاً تصمیم بگیرد — نه صرفِ
    وجودِ ``ShopSettings`` (که ``tax_enabled`` پیش‌فرضش True است و به‌تنهایی
    نمی‌تواند «هنوز انتخاب نشده» را از «آگاهانه روشن نگه داشته شده» تشخیص
    دهد). تنها منبعِ حقیقتِ این مرحله، ذخیره‌ی صریحِ صفحه‌ی «مالیات ندارم/
    دارم» است (``tax_setup_confirmed_at``) — نه وجودِ ``TaxRate``، چون
    انتخابِ «مالیات ندارم» عمداً هیچ نرخی نمی‌سازد و هنوز باید کامل حساب
    شود."""
    return bool(shop and shop.tax_setup_confirmed_at)


def _custom_domains(store):
    return list(StoreDomain.objects.filter(
        store=store, domain_type=StoreDomain.DomainType.CUSTOM_DOMAIN, retired_at__isnull=True,
    ))


def _domain_is_active(domain) -> bool:
    """A custom domain is «connected» only when ownership is verified, DNS reaches RastiSi, HTTPS is ready AND it was activated as the
    shop's address. «Verified» alone (or a pending request) never counts — that is only progress."""
    return (
        domain.verification_status == StoreDomain.VerificationStatus.VERIFIED
        and domain.routing_status == StoreDomain.RoutingStatus.CONNECTED
        and domain.tls_status == StoreDomain.TlsStatus.READY
        and bool(domain.is_primary)
    )


def _custom_domain_complete(store, shop):
    return any(_domain_is_active(domain) for domain in _custom_domains(store))


def _custom_domain_state(store, shop):
    """Progress of a domain the seller started but that is not active yet: who has to act next."""
    pending = [domain for domain in _custom_domains(store) if not _domain_is_active(domain)]
    if not pending:
        return None
    states = []
    for domain in pending:
        if domain.verification_status != StoreDomain.VerificationStatus.VERIFIED:
            states.append(STATE_NEEDS_ACTION)                     # the TXT record has to be added / re-checked by the seller
        elif domain.routing_status != StoreDomain.RoutingStatus.CONNECTED:
            states.append(STATE_NEEDS_ACTION)                     # the A / CNAME record
        elif domain.tls_status != StoreDomain.TlsStatus.READY:
            states.append(STATE_PROCESSING)                       # RastiSi is issuing HTTPS
        else:
            states.append(STATE_NEEDS_ACTION)                     # everything is ready: only the activation is left
    return STATE_NEEDS_ACTION if STATE_NEEDS_ACTION in states else STATE_PROCESSING


def _search_visibility_complete(store, shop):
    """The shop can be found: it is public AND its address is a real public host (not localhost / a test address)."""
    from urllib.parse import urlsplit

    from apps.core import seo_policy
    from apps.stores.resolution import resolve_storefront_url_for_store

    if not is_publicly_visible(store):
        return False
    url = resolve_storefront_url_for_store(store, None)
    return bool(url) and not seo_policy.is_non_public_host(urlsplit(url).netloc)


def _sales_prerequisites_complete(store, shop):
    """Everything that must exist before the shop CAN be published: basic information, an installed industry template, one real active
    product, one active shipping method and one way to pay. Tax and a custom domain are optional and never block this."""
    return (
        _store_information_complete(store, shop)
        and _industry_complete(store, shop)
        and _industry_template_complete(store, shop)
        and _product_publish_complete(store, shop)
        and _shipping_complete(store, shop)
        and _payment_gateway_complete(store, shop)
    )


def _publish_complete(store, shop):
    """«انتشار فروشگاه» = the shop is REALLY public (publication authority) — not merely «ready to publish»."""
    return is_publicly_visible(store) and _sales_prerequisites_complete(store, shop)


def _industry_installation(store):
    return (
        StoreIndustryInstallation.objects.select_related("industry_template")
        .filter(store=store)
        .first()
    )


def build_industry_summary(store) -> dict:
    """اطلاعاتِ واقعیِ صنف/قالبِ نصب‌شده برایِ کارتِ کوچکِ «صنفِ فروشگاه» در
    داشبورد — مستقیماً از ``StoreIndustryInstallation`` (تنها منبعِ حقیقتِ
    این داده)؛ اگر نصبی وجود نداشته باشد (چه صنف اصلاً انتخاب نشده باشد، چه
    آگاهانه رد شده باشد)، ``installation`` خالی برمی‌گردد تا تمپلیت پیامِ
    «هنوز قالب صنفی نصب نشده است» را نشان دهد — هیچ متنی این‌جا هاردکد
    نمی‌شود، فقط داده خوانده می‌شود."""
    installation = _industry_installation(store)
    if installation is None:
        return {"has_installation": False}
    return {
        "has_installation": True,
        "industry_name": installation.industry_template.name,
        "template_version": installation.installed_version,
        "status": installation.status,
        "status_label": installation.get_status_display(),
        "installed_at": installation.created_at,
        "categories_created": installation.categories_created,
        "attributes_created": installation.attributes_created,
    }


def _custom_domain_url(store, request):
    """لینکِ صفحه‌ی مدیریتِ دامنه‌ی اختصاصی — با ``reverse`` واقعی روی
    urlconf پلتفرم (``apps.portal.urls``، جایی که این صفحه واقعاً تعریف
    شده)، نه یک مسیرِ دستی‌نوشته. میزبان از همان ``_platform_url`` (که
    خودش از تنظیماتِ ``RASTISI_PLATFORM_PRIMARY_HOST`` می‌خواند) می‌آید —
    پس هیچ میزبانِ پلتفرمِ ثابتی در این ماژول هاردکد نمی‌شود و در توسعه‌ی
    محلی هم یک آدرسِ واقعاً کارآمد می‌سازد."""
    path = reverse("portal:custom-domains", args=[store.public_id], urlconf="shop_core.urls_platform")
    return _platform_url(request, path)


# ---- step states (what the seller sees; never «completed» for something that was not done) ------------------------------------------
STATE_DONE = "done"                    # really done (a real predicate over real data)
STATE_READY = "ready"                  # required, can be done now
STATE_BLOCKED = "blocked"              # required, but a prerequisite of the catalogue chain is still open
STATE_OPTIONAL = "optional"            # not needed to start selling — never counted in the progress, never shown as «done»
STATE_NEEDS_ACTION = "needs_action"    # started, waiting for the seller (e.g. a DNS record)
STATE_PROCESSING = "processing"        # started, RastiSi is working on it automatically
STATE_NEEDS_FIX = "needs_fix"          # something failed and must be corrected

STATE_LABELS = {
    STATE_DONE: "انجام شد",
    STATE_READY: "آماده انجام",
    STATE_BLOCKED: "پس از مرحلهٔ قبل",
    STATE_OPTIONAL: "اختیاری",
    STATE_NEEDS_ACTION: "منتظر اقدام شما",
    STATE_PROCESSING: "در حال انجام خودکار",
    STATE_NEEDS_FIX: "نیازمند اصلاح",
}

GROUPS = (
    ("business", "۱. معرفی کسب‌وکار"),
    ("appearance", "۲. آماده‌سازی ظاهر"),
    ("sales", "۳. آماده‌سازی فروش"),
    ("launch", "۴. بررسی و انتشار"),
    ("growth", "۵. رشد و دیده‌شدن"),
)


@dataclass(frozen=True)
class _ChecklistStep:
    key: str
    label: str
    icon: str
    is_complete: Callable
    url: Callable
    description: str = ""
    group: str = "sales"
    #: needed before the shop can start selling. Everything else is optional/recommended and never blocks nor counts in the progress.
    required: bool = False
    #: progress of a started-but-unfinished step: ``needs_action`` / ``processing`` / ``needs_fix`` (None = not started)
    state_fn: Callable | None = None
    #: True when RastiSi itself produced the result (an installed industry template creates categories, attributes…)
    auto_fn: Callable | None = None


#: کلیدهای زنجیره‌ی اصلیِ کاتالوگ — نگاه کنید به ``build_setup_checklist`` — هر مرحله فقط وقتی «باز» نمایش داده می‌شود که همه‌ی
#: مراحلِ پیش از خودش در همین فهرست تکمیل شده باشند؛ این قفلِ سخت‌گیرانه‌ی ناوبری نیست (هر مرحله همیشه قابل‌کلیک می‌ماند).
CATALOG_CHAIN_KEYS = [
    "industry", "industry_template", "product_groups", "product_categories",
    "brands", "attributes", "first_product", "product_images", "variants",
    "inventory", "shipping", "publish",
]


def _installation_created(attribute: str):
    def _auto(store, shop):
        installation = _active_industry_installation(store)
        return bool(installation and getattr(installation, attribute, 0))
    return _auto


def _industry_template_failed(store, shop):
    installation = _industry_installation(store)
    return STATE_NEEDS_FIX if installation is not None and installation.status == StoreIndustryInstallation.Status.FAILED else None


def _domain_page_url(store, request):
    """Domain work starts INSIDE the seller panel (this store's own admin host) — never a hand-off to another host."""
    return reverse("dashboard:settings") + "?section=domain"


def _steps():
    settings_url = lambda section: (lambda store, request: reverse("dashboard:settings") + f"?section={section}")   # noqa: E731
    return [
        # --- زنجیره‌ی پیش‌نیازیِ واقعیِ ساختِ کالا: صنف → قالب صنف → گروه‌ها → دسته‌بندی‌ها → برندها → ویژگی‌ها → اولین کالا → تصاویر
        # → تنوع‌ها → موجودی → ارسال → انتشار فروشگاه. هرگز نباید بدونِ عبور از پیش‌نیازهایش به «اولین کالا» برسد.
        _ChecklistStep("industry", "انتخاب صنف", "🏭", _industry_complete, settings_url("industry"), group="business", required=True),
        _ChecklistStep("industry_template", "نصب قالب صنف", "🏗️", _industry_template_complete, settings_url("industry"),
                       group="appearance", required=True, state_fn=_industry_template_failed,
                       auto_fn=lambda store, shop: _industry_template_complete(store, shop)),
        _ChecklistStep("product_groups", "ایجاد گروه‌های دسته‌بندی", "🗂️", _product_groups_complete,
                       lambda store, request: reverse("dashboard:category-list"), group="sales", required=True,
                       auto_fn=_installation_created("categories_created")),
        _ChecklistStep("product_categories", "ایجاد دسته‌بندی‌ها", "📁", _product_subcategories_complete,
                       lambda store, request: reverse("dashboard:category-list"), group="sales", required=True,
                       auto_fn=_installation_created("categories_created")),
        _ChecklistStep("brands", "ایجاد برندها", "🔖", _brands_complete, lambda store, request: reverse("dashboard:brand-list"), group="sales"),
        _ChecklistStep("attributes", "ایجاد ویژگی‌های کالا", "🏷️", _attributes_complete,
                       lambda store, request: reverse("dashboard:attribute-list"), group="sales", auto_fn=_installation_created("attributes_created")),
        _ChecklistStep("first_product", "ایجاد اولین کالا", "📦", _first_product_complete,
                       lambda store, request: reverse("dashboard:product-list"), group="sales", required=True),
        _ChecklistStep("product_images", "بارگذاری تصاویر", "🖼️", _product_images_complete,
                       lambda store, request: reverse("dashboard:product-list"), group="sales"),
        _ChecklistStep("variants", "تنظیم تنوع‌ها", "🎛️", _variants_complete, lambda store, request: reverse("dashboard:product-list"), group="sales"),
        _ChecklistStep("inventory", "موجودی", "📊", _inventory_complete, lambda store, request: reverse("dashboard:inventory-list"), group="sales"),
        _ChecklistStep("shipping", "پیکربندی ارسال", "🚚", _shipping_complete, lambda store, request: reverse("dashboard:shipping-setup"),
                       description="حداقل یک روش ارسال یا گزینه دریافت حضوری را فعال کنید.", group="sales", required=True),
        _ChecklistStep("publish", "انتشار فروشگاه", "🚀", _publish_complete,
                       lambda store, request: _platform_url(request, f"/app/stores/{store.public_id}/onboarding/review/"),
                       group="launch", required=True),
        # --- مراحلِ تکمیلی (بخشی از زنجیره‌ی کاتالوگ نیستند)
        _ChecklistStep("product_publish", "انتشار کالا (فعال‌سازی)", "✅", _product_publish_complete,
                       lambda store, request: reverse("dashboard:product-list"), group="sales", required=True),
        _ChecklistStep("store_info", "اطلاعات فروشگاه", "🏬", _store_information_complete, settings_url("general"), group="business", required=True),
        _ChecklistStep("contact", "اطلاعات تماس", "☎️", _contact_complete, settings_url("general"), group="business"),
        _ChecklistStep("logo", "لوگو", "🖼️", _logo_complete, settings_url("general"), group="appearance"),
        _ChecklistStep("theme", "قالب و رنگ‌بندی", "🎨", _theme_complete,
                       lambda store, request: reverse("dashboard:storefront-builder-r4-editor") + "?panel=appearance", group="appearance"),
        _ChecklistStep("payment_gateway", "درگاه پرداخت", "💳", _payment_gateway_complete, settings_url("payment-config"), group="sales", required=True),
        _ChecklistStep("tax", "اطلاعات مالیاتی (اختیاری)", "🧾", _tax_complete, lambda store, request: reverse("dashboard:tax-settings"),
                       description="در صورت نداشتن مالیات، گزینه «مالیات ندارم» را انتخاب کنید.", group="sales"),
        _ChecklistStep("custom_domain", "دامنه اختصاصی (اختیاری)", "🌐", _custom_domain_complete, _domain_page_url,
                       description="فروشگاه بدون دامنه اختصاصی نیز روی زیردامنه راستیسی قابل استفاده است.", group="growth", state_fn=_custom_domain_state),
        _ChecklistStep("search_visibility", "دیده‌شدن در گوگل و بینگ", "🔎", _search_visibility_complete, settings_url("integrations"),
                       description="پس از انتشار روی آدرس عمومی، نقشهٔ سایت و داده‌های فنی به‌صورت خودکار آماده‌اند.", group="growth"),
    ]


def build_setup_checklist(store, request):
    """چک‌لیستِ راه‌اندازی برایِ داشبوردِ خانه — هر بار زنده محاسبه می‌شود، هیچ‌جا ذخیره نمی‌شود.

    * هر مرحله **ضروری** (برایِ شروعِ فروش) یا **اختیاری** است؛ فقط ضروری‌ها در پیشرفت (``required_percent``) و در «آمادهٔ فروش» شمرده
      می‌شوند. یک مرحلهٔ اختیاری هرگز «انجام‌شده» نمایش داده نمی‌شود مگر واقعاً انجام شده باشد.
    * ``state``: done / ready / blocked / optional / needs_action / processing / needs_fix.
    * ``is_unlocked`` یک نشانه‌ی صرفاً بصری است، نه قفلِ ناوبری (دکمه همیشه کلیک‌پذیر می‌ماند).
    * کلیدهای قدیمیِ ``completed_count`` / ``total_count`` / ``percent`` (روی همه‌ی مراحل) برایِ سازگاری می‌مانند؛ رابط از
      ``required_*`` استفاده می‌کند."""
    shop = _shop_settings(store)
    steps = []
    completed_count = 0
    chain_blocked_so_far = False
    blocking_label = None
    for step in _steps():
        is_complete = bool(step.is_complete(store, shop))
        if is_complete:
            completed_count += 1
        in_chain = step.key in CATALOG_CHAIN_KEYS
        is_unlocked = not (in_chain and chain_blocked_so_far)
        locked_reason = f"ابتدا «{blocking_label}» را تکمیل کنید" if in_chain and not is_unlocked else ""
        progress = None if is_complete or step.state_fn is None else step.state_fn(store, shop)
        if is_complete:
            state = STATE_DONE
        elif progress:
            state = progress
        elif not step.required:
            state = STATE_OPTIONAL
        elif not is_unlocked:
            state = STATE_BLOCKED
        else:
            state = STATE_READY
        if in_chain and not is_complete:
            if not chain_blocked_so_far:
                blocking_label = step.label
            chain_blocked_so_far = True
        steps.append({
            "key": step.key, "label": step.label, "icon": step.icon,
            "is_complete": is_complete, "is_unlocked": is_unlocked, "locked_reason": locked_reason,
            "url": step.url(store, request), "description": step.description,
            "group": step.group, "required": step.required, "state": state, "state_label": STATE_LABELS[state],
            "auto_done": bool(is_complete and step.auto_fn is not None and step.auto_fn(store, shop)),
            "is_next": False,
        })

    required = [step for step in steps if step["required"]]
    required_done = sum(1 for step in required if step["is_complete"])
    sell_blockers = [step for step in required if step["key"] != "publish" and not step["is_complete"]]
    publish = next((step for step in steps if step["key"] == "publish"), None)
    is_live = bool(publish and publish["is_complete"])

    # ONE primary action: the first required step still open and open to the seller; then publishing; then the first optional step in progress
    primary = next((step for step in required if not step["is_complete"] and step["state"] in (STATE_READY, STATE_NEEDS_FIX)), None)
    if primary is None:
        primary = next((step for step in steps if not step["is_complete"] and step["state"] in (STATE_NEEDS_ACTION, STATE_NEEDS_FIX)), None)
    if primary is None:
        primary = next((step for step in required if not step["is_complete"]), None)
    if primary is not None:
        primary["is_next"] = True

    groups = []
    for key, label in GROUPS:
        members = [step for step in steps if step["group"] == key]
        required_members = [step for step in members if step["required"]]
        groups.append({
            "key": key, "label": label, "steps": members,
            "required_done": sum(1 for step in required_members if step["is_complete"]), "required_total": len(required_members),
            "is_done": bool(required_members) and all(step["is_complete"] for step in required_members),
        })

    total_count = len(steps)
    return {
        "steps": steps,
        "groups": groups,
        "completed_count": completed_count,
        "total_count": total_count,
        "percent": round(completed_count * 100 / total_count) if total_count else 0,
        "required_done": required_done,
        "required_total": len(required),
        "required_percent": round(required_done * 100 / len(required)) if required else 0,
        "sell_blockers": [step["label"] for step in sell_blockers],
        "ready_to_publish": not sell_blockers,
        "is_live": is_live,
        "primary_action": primary,
        "auto_done_labels": [step["label"] for step in steps if step["auto_done"]],
        # the celebration only when every required step is done AND the shop is really public
        "all_complete": bool(required) and required_done == len(required) and is_live,
    }
