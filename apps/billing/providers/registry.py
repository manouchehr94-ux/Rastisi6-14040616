"""رجیستریِ Providerهایِ پرداختِ اشتراک (ADR-75).

Providerِ فعال از ``settings.RASTISI_BILLING_PROVIDER`` تعیین می‌شود (پیش‌فرض
«manual»). رازِ Webhook فقط از تنظیمات/محیط خوانده می‌شود، هرگز از پایگاه‌داده
یا کد."""

from django.conf import settings

from apps.billing.providers.adapter_backed import AdapterBackedBillingProvider
from apps.billing.providers.base import BillingProviderError
from apps.billing.providers.manual import ManualProvider
from apps.billing.providers.zibal import ZibalBillingProvider

_PROVIDERS = {
    ManualProvider.code: ManualProvider(),
    ZibalBillingProvider.code: ZibalBillingProvider(),
    "zarinpal": AdapterBackedBillingProvider("zarinpal"),
    "pasargad": AdapterBackedBillingProvider("pasargad"),
}


def get_provider(code: str | None = None):
    """نمونه‌ی Providerِ خواسته‌شده (یا Providerِ فعالِ پیش‌فرض)."""
    code = code or active_provider_code()
    provider = _PROVIDERS.get(code)
    if provider is None:
        raise BillingProviderError(f"Providerِ «{code}» ثبت نشده است.", code="unknown_provider")
    return provider


def active_provider_code() -> str:
    """کدِ Providerِ فعال — از Platform Admin (``PlatformConfiguration``)
    قابلِ‌تغییر بدونِ ویرایشِ کد. اگر ردیفِ پیکربندی هنوز موجود نیست (مثلاً
    حینِ migrate اولیه)، به تنظیماتِ محیط برمی‌گردد (fail-safe به «manual»)."""
    try:
        from apps.portal.services.platform_config_service import get_platform_configuration

        code = get_platform_configuration().default_payment_provider
    except Exception:  # noqa: BLE001 — پایگاه‌داده هنوز آماده نیست/جدول نیست
        code = None
    if not code:
        code = getattr(settings, "RASTISI_BILLING_PROVIDER", "manual")
    return code or "manual"


def webhook_secret() -> str:
    """رازِ تأییدِ Webhookِ Providerِ فعال — فقط از تنظیمات/محیط."""
    return getattr(settings, "RASTISI_BILLING_WEBHOOK_SECRET", "") or ""
