"""راه‌اندازیِ اتمیکِ فروشگاهِ آزمایشی (Section C) — از ثبت‌نامِ مالک تا یک
Store کاملاً قابل‌استفاده، در یک تراکنشِ واحد.

هیچ نیمه‌کاره‌ای وجود ندارد: یا همه‌ی مراحل زیر با موفقیت انجام می‌شود، یا
هیچ‌کدام (``transaction.atomic``). خطای هر مرحله کل عملیات را rollback
می‌کند — از جمله اگر تولید ``platform_code`` به دلیلِ برخوردِ نادرِ یکتایی
شکست بخورد (با retry محدود دوباره تلاش می‌شود، نه اینکه یک Store نیمه‌ساز
باقی بماند).

ایدمپوتنسی: این تابع خودش قفلِ «دوبار-کلیک» ندارد — آن مسئولیتِ لایه‌ی view
(Section G) است (توکنِ یکبارمصرفِ session-based، مطابق الگوی موجودِ
Cart.checkout_token/Order.idempotency_key). دو فراخوانیِ واقعاً مستقل، هر
دو Store جداگانه می‌سازند — این محدودیتِ عمدی و مستندشده است، نه باگ."""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.text import slugify

from apps.catalog.models import IndustryTemplate, Warehouse
from apps.catalog.services import industry_catalog_service
from apps.catalog.services.industry_template_service import install_industry_template
from apps.core.models import ShopSettings
from apps.core.services.audit_service import record_audit_event
from apps.stores.models import Store, StoreDomain, StoreMembership
from apps.stores.services.platform_code_service import generate_unique_platform_code
from apps.subscriptions.services.subscription_service import provision_default_subscription

from apps.stores.services.domain_namespace_service import (
    DomainNamespaceCollisionError,
    assert_admin_subdomain_namespace_available,
)

User = get_user_model()

_MAX_SLUG_ATTEMPTS = 20
_MAX_PLATFORM_CODE_ATTEMPTS = 10


class ProvisioningError(Exception):
    """خطای قابل‌نمایش هنگام راه‌اندازیِ فروشگاهِ آزمایشی."""


class RegistrationClosedError(ProvisioningError):
    """``PlatformConfiguration.new_store_registration_enabled`` خاموش است."""


REGISTRATION_CLOSED_MESSAGE = "ساخت فروشگاه تازه موقتاً در دسترس نیست؛ لطفاً بعداً دوباره تلاش کنید."


def enforce_new_store_registration_open() -> None:
    """سیاستِ پلتفرم در لایه‌ی سرویس: هیچ Storeی (چه ثبت‌نامِ اول، چه فروشگاهِ
    اضافه‌ی مالکِ موجود، چه فراخوانیِ داخلی) وقتی ثبت‌نامِ فروشگاهِ تازه خاموش
    است ساخته نمی‌شود. Storeهایِ موجود و ورودِ مالکان تأثیری نمی‌پذیرند."""
    from .platform_config_service import is_new_store_registration_enabled

    if not is_new_store_registration_enabled():
        raise RegistrationClosedError(REGISTRATION_CLOSED_MESSAGE)


def _owned_active_store_count(owner) -> int:
    return StoreMembership.objects.filter(
        user=owner, role=StoreMembership.Role.OWNER, status=StoreMembership.MembershipStatus.ACTIVE,
    ).count()


def enforce_can_provision_store(owner) -> None:
    limit = settings.RASTISI_MAX_STORES_PER_OWNER
    if _owned_active_store_count(owner) >= limit:
        raise ProvisioningError(
            f"شما به سقفِ مجازِ {limit} فروشگاه رسیده‌اید؛ برای فروشگاه‌های بیشتر با پشتیبانی تماس بگیرید."
        )


def _unique_slug(name: str) -> str:
    base = slugify(name, allow_unicode=True) or "store"
    base = base[:190]
    candidate = base
    for attempt in range(1, _MAX_SLUG_ATTEMPTS + 1):
        if not Store.objects.filter(slug=candidate).exists():
            return candidate
        candidate = f"{base}-{attempt + 1}"
    raise ProvisioningError("امکانِ ساختِ اسلاگِ یکتا برای این نام وجود ندارد؛ نامِ دیگری امتحان کنید.")


def _create_store_with_unique_platform_code(*, name: str, slug: str) -> Store:
    last_error = None
    for _attempt in range(_MAX_PLATFORM_CODE_ATTEMPTS):
        code = generate_unique_platform_code()
        try:
            with transaction.atomic():
                return Store.objects.create(
                    name=name, slug=slug, status=Store.Status.ACTIVE, platform_code=code,
                    # Durable "modern portal Store" signal: private until the final
                    # onboarding Publish, whatever the subscription/billing config is.
                    onboarding_required_at=timezone.now(),
                )
        except IntegrityError as exc:
            last_error = exc
            continue
    raise ProvisioningError("امکانِ تولیدِ شناسه‌ی یکتای پلتفرم وجود ندارد؛ دوباره تلاش کنید.") from last_error


def latest_offerable_industry_templates():
    """آخرین نسخه‌ی production_ready هر صنف — یک ردیف به‌ازای هر ``slug``،
    برای نمایش در ویزارد آنبوردینگ (Section D).

    نازک‌پوششی روی تکِ منبعِ حقیقتِ کاتالوگِ صنف
    (``industry_catalog_service.offerable_industry_templates``) — نگاه کنید
    به بخشِ ۲ («یک منبعِ واحد برایِ همه‌ی نقاطِ ورودی»)."""
    return industry_catalog_service.offerable_industry_templates()


@transaction.atomic
def provision_trial_store(*, owner, name: str, industry_template: IndustryTemplate | None = None) -> Store:
    """فروشگاهِ آزمایشیِ ``owner`` را می‌سازد و بلافاصله فعال و قابل‌استفاده
    برمی‌گرداند. مراحل: سقفِ تعدادِ فروشگاه → Store (با platform_code و
    admin_subdomain خودکار) → عضویتِ OWNER فعال → دامنه‌ی آزمایشیِ
    ``{platform_code}.{RASTISI_ADMIN_DOMAIN_SUFFIX}`` (از پیش verified، چون
    خودِ راستیسی مالکِ DNS این پسوند است — ADR-95) → ShopSettings →
    انبارِ پیش‌فرض → (اختیاری) نصبِ قالبِ صنف → اشتراکِ پیش‌فرض (fail-open
    اگر پلن پیش‌فرض تنظیم نشده باشد، ADR-65) → رخدادِ حسابرسی."""
    name = (name or "").strip()
    if not name:
        raise ProvisioningError("نامِ فروشگاه الزامی است")

    enforce_new_store_registration_open()
    enforce_can_provision_store(owner)

    slug = _unique_slug(name)
    store = _create_store_with_unique_platform_code(name=name, slug=slug)
    try:
        assert_admin_subdomain_namespace_available(
            store=store, label=store.admin_subdomain,
        )
    except DomainNamespaceCollisionError as exc:
        raise ProvisioningError(str(exc)) from exc


    StoreMembership.objects.create(
        store=store, user=owner, role=StoreMembership.Role.OWNER,
        status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
    )

    trial_hostname = f"{store.platform_code}.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"
    StoreDomain.objects.create(
        store=store, hostname=trial_hostname, is_primary=True,
        domain_type=StoreDomain.DomainType.GENERATED_TRIAL,
        verification_status=StoreDomain.VerificationStatus.VERIFIED,
        verified_at=timezone.now(),
    )

    ShopSettings.provision_for(store)
    Warehouse.objects.get_or_create(
        store=store, code="main", defaults={"name": "انبار اصلی", "is_default": True, "is_active": True},
    )

    if industry_template is not None:
        install_industry_template(store, industry_template)

    provision_default_subscription(store, actor=owner)

    record_audit_event(
        store=store, actor=owner, action_code="store.trial_provisioned",
        object_type="Store", object_id=store.pk, object_label=store.name,
        after={"platform_code": store.platform_code, "trial_hostname": trial_hostname},
    )
    return store


def provision_initial_trial_store(*, owner, name: str) -> tuple[Store, bool]:
    """فروشگاهِ آزمایشیِ **اولِ** یک مالکِ تازه — idempotent و ایمن در برابرِ
    مسابقه. ردیفِ ``User`` مالک در تراکنش قفل می‌شود (PostgreSQL:
    ``SELECT ... FOR UPDATE``)؛ اگر مالک از قبل عضوِ فعالِ OWNER یک Store باشد،
    همان Store برمی‌گردد و Storeِ دومی ساخته نمی‌شود. خروجی: ``(store, created)``.

    این لایه‌ی دفاعیِ دوم است؛ لایه‌ی اول این است که فقط درخواستی که
    ``OwnerProfile`` را واقعاً ساخته (``owner_created``) این تابع را صدا می‌زند."""
    with transaction.atomic():
        User.objects.select_for_update().get(pk=owner.pk)
        existing = (
            Store.objects.filter(
                memberships__user=owner, memberships__role=StoreMembership.Role.OWNER,
                memberships__status=StoreMembership.MembershipStatus.ACTIVE,
            ).order_by("created_at", "pk").first()
        )
        if existing is not None:
            return existing, False
        return provision_trial_store(owner=owner, name=name), True
