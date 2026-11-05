"""گیتِ انتشارِ قابلیت‌ها — تضمین می‌کند **قابلیتِ برنامه‌ریزی‌شده هرگز دسترسیِ واقعی نمی‌دهد**.

برایِ هر کلیدِ Entitlement که به یک ``PricingFeature`` وصل است، دسترسی فقط وقتی ممکن است که *همه‌ی* شرط‌هایِ زیر برقرار باشد:

1. قطعِ اضطراریِ (kill switch) خاموش باشد،
2. کلید در رجیستریِ **کد** ثبت شده باشد (``capability_registry``) — یک رکوردِ DB نمی‌تواند خودش را «اعمال‌شده» اعلام کند،
3. آمادگیِ فنی «آماده» باشد،
4. وضعیتِ تجاری «در دسترس» (یا «جمع‌شده» که دسترسیِ نسخه‌هایِ قبلی را حفظ می‌کند) باشد، و
5. برایِ قابلیتِ ساخته‌شده توسطِ مالک: نسخه‌ی پلن **پس از** زمانِ در‌دسترس‌شدن منتشر شده باشد (انتشارِ نسخه‌ی تازه = قراردادِ صریح؛
   نسخه‌هایِ قدیمی بی‌صدا دسترسیِ تازه نمی‌گیرند) و فروشگاهِ بدونِ اشتراک fail-closed باشد.

کلیدی که به هیچ ``PricingFeature``ای وصل نیست رفتارِ قبلی را دارد (ADR-64). نتیجه‌ی گیت‌ها ۳۰ ثانیه کش می‌شود و با هر تغییرِ ردیف
(همان پردازش) فوراً باطل می‌شود؛ در چندپردازشی حداکثر ۳۰ ثانیه تأخیر دارد (قطعِ اضطراری در ``invalidate`` همه‌جا ۳۰ ثانیه)."""

from django.core.cache import cache
from django.db.models.signals import post_delete, post_save

from apps.subscriptions import capability_registry

_CACHE_KEY = "subscriptions:feature_gates:v1"
_TTL = 30


def _load() -> dict:
    from apps.subscriptions.models import PricingFeature

    rows = {}
    for f in PricingFeature.objects.filter(entitlement__isnull=False).select_related("entitlement"):
        rows[f.entitlement.key] = {
            "technical": f.technical_status, "commercial": f.commercial_status, "kill": f.kill_switch,
            "custom": f.is_custom, "activated_at": f.activated_at,
        }
    return rows


def gates() -> dict:
    data = cache.get(_CACHE_KEY)
    if data is None:
        data = _load()
        cache.set(_CACHE_KEY, data, _TTL)
    return data


def invalidate(*args, **kwargs):
    cache.delete(_CACHE_KEY)


def allows(key: str, plan_version) -> bool:
    gate = gates().get(key)
    if gate is None:
        return True                                   # کلیدِ مدیریت‌نشده توسطِ کاتالوگ: رفتارِ قبلی
    if gate["kill"] or not capability_registry.is_registered(key):
        return False
    if gate["technical"] != "ready":
        return False
    if gate["commercial"] not in ("available", "withdrawn"):
        return False
    if gate["custom"]:
        if plan_version is None:
            return False                              # قابلیتِ تازه به فروشگاهِ بدونِ اشتراک نشت نمی‌کند
        activated = gate["activated_at"]
        if activated is not None and (plan_version.published_at is None or plan_version.published_at < activated):
            return False
    return True


def _connect():
    from apps.subscriptions.models import EntitlementDefinition, PricingFeature

    for model in (PricingFeature, EntitlementDefinition):
        post_save.connect(invalidate, sender=model, dispatch_uid=f"fg-save-{model.__name__}")
        post_delete.connect(invalidate, sender=model, dispatch_uid=f"fg-del-{model.__name__}")
