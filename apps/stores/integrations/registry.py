"""فهرستِ یکپارچه‌سازی‌های سطحِ Store (eNamad، Torob، Google Analytics،
Google Tag Manager، پیکسل‌های تبلیغاتی، موتورهایِ مقایسه‌ی قیمت).

دقیقاً همان الگویِ ``apps.orders.gateways.registry`` — یک نقطه‌ی واحدِ
dispatch؛ افزودنِ یکپارچه‌سازیِ جدید یعنی افزودنِ یک ``IntegrationProvider``
اینجا، نه ساختِ کدِ تکراری در هر جای دیگر. هیچ‌کدام اینجا یک درگاهِ پرداختِ
واقعی نیستند (آن‌ها همچنان از طریقِ ``apps.orders.gateways`` مدیریت
می‌شوند، طبقِ همان الگویِ اثبات‌شده‌ی Zibal/COD) — این فهرست فقط برایِ
یکپارچه‌سازی‌هایی است که صرفاً یک شناسه/کد نیاز دارند، نه یک تراکنشِ مالی.

هر Provider یک ``validate(values)`` دارد که فرمتِ مقادیر را واقعاً بررسی
می‌کند (نه صرفاً «غیرخالی») — این همان «تستِ اتصال»ی است که این کدبیس
می‌تواند بدونِ حدس‌زدنِ APIهای مستندنشده‌ی بیرونی، صادقانه و به‌درستی انجام
دهد؛ یک HTTP واقعی به سرویسِ eNamad/Torob بدونِ مستنداتِ رسمیِ تأییدشده
می‌توانست کدی بسازد که به‌نظر کار می‌کند اما در تولید شکست بخورد یا داده‌ی
نادرست بفرستد — ریسکی که برایِ یکپارچه‌سازیِ مالی/اعتمادی قابلِ قبول نیست."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

from apps.stores.services.enamad_verification_service import (
    validate_enamad_integration_values,
)


class IntegrationCategory:
    TRUST = "trust"
    ANALYTICS = "analytics"
    MARKETING = "marketing"
    COMPARISON = "comparison"

    CHOICES = [
        (TRUST, "نشان اعتماد"),
        (ANALYTICS, "تحلیل و آمار"),
        (MARKETING, "بازاریابی و تبلیغات"),
        (COMPARISON, "مقایسه‌گرهای قیمت"),
    ]


@dataclass(frozen=True)
class IntegrationField:
    key: str
    label: str
    is_secret: bool = False
    placeholder: str = ""
    kind: str = "text"            # "text" | "checkbox" (a checkbox is a setting, not an identifier: it never counts as «saved data»)


@dataclass(frozen=True)
class IntegrationProvider:
    code: str
    display_name: str
    category: str
    description: str
    setup_guide: str
    fields: tuple[IntegrationField, ...]
    validate: Callable[[dict], str | None] = field(repr=False)


def _require_non_empty(field_key: str, label: str):
    def _validate(values: dict) -> str | None:
        if not (values.get(field_key) or "").strip():
            return f"{label} نمی‌تواند خالی باشد."
        return None
    return _validate


def _require_pattern(field_key: str, label: str, pattern: str, example: str):
    compiled = re.compile(pattern)

    def _validate(values: dict) -> str | None:
        value = (values.get(field_key) or "").strip()
        if not value:
            return f"{label} نمی‌تواند خالی باشد."
        if not compiled.match(value):
            return f"{label} با الگویِ موردِ انتظار (مثل «{example}») مطابقت ندارد."
        return None
    return _validate


PROVIDERS: dict[str, IntegrationProvider] = {
    "enamad": IntegrationProvider(
        code="enamad",
        display_name="اینماد (eNamad)",
        category=IntegrationCategory.TRUST,
        description=(
            "دو مرحله‌ی جدا: ۱) احراز دسترسی فنی با متاتگِ اینماد؛ ۲) پس از صدورِ نماد، شناسه و کدِ تأییدِ آن. "
            "HTML/اسکریپتِ دلخواه هرگز پذیرفته نمی‌شود؛ راستی‌سی خودش تصویر و پیوندِ امن را می‌سازد."
        ),
        setup_guide="https://enamad.ir",
        fields=(
            IntegrationField(
                key="verification_meta_tag",
                label="متاتگ احراز فنی اینماد",
                placeholder='<meta name="..." content="...">',
            ),
            IntegrationField(key="enamad_id", label="شناسه‌ی نمادِ نهایی (پس از صدور)", placeholder="221617"),
            IntegrationField(key="enamad_auth_code", label="کدِ تأییدِ نمادِ نهایی (پس از صدور)", placeholder="94MqMPJEnuahlSHjb9kP"),
            IntegrationField(key="enamad_show_badge", label="نمایش نماد در فوتر فروشگاه (فقط روی دامنهٔ اختصاصیِ تأییدشده)", kind="checkbox"),
        ),
        validate=validate_enamad_integration_values,
    ),
    "torob": IntegrationProvider(
        code="torob",
        display_name="ترب (Torob)",
        category=IntegrationCategory.COMPARISON,
        description=(
            "فقط شناسه‌ی فروشنده‌ی شما در ترب ذخیره می‌شود. راستی‌سی فعلاً فیدی برای ترب نمی‌سازد و داده‌ای به ترب نمی‌فرستد؛ "
            "صفحه‌های عمومیِ محصولات (با قیمت و موجودیِ واقعی در داده‌ی ساختاریافته) پس از انتشار روی آدرس عمومی قابل‌خواندن‌اند."
        ),
        setup_guide="https://torob.com/sell/",
        fields=(IntegrationField(key="merchant_id", label="شناسه‌ی فروشنده در ترب"),),
        validate=_require_pattern("merchant_id", "شناسه‌ی فروشنده", r"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,63}$", "SHOP-77"),
    ),
    "google_analytics": IntegrationProvider(
        code="google_analytics",
        display_name="گوگل آنالیتیکس (GA4)",
        category=IntegrationCategory.ANALYTICS,
        description="شناسه‌ی اندازه‌گیریِ GA4 را ذخیره می‌کنید؛ ردیابی فقط وقتی روشن می‌شود که پلتفرم آن را فعال کرده باشد و فروشگاه روی آدرس عمومی منتشر شده باشد.",
        setup_guide="https://analytics.google.com",
        fields=(IntegrationField(key="measurement_id", label="شناسه‌ی اندازه‌گیری", placeholder="G-XXXXXXXXXX"),),
        validate=_require_pattern("measurement_id", "شناسه‌ی اندازه‌گیری", r"^G-[A-Z0-9]{6,10}$", "G-ABC1234DEF"),
    ),
    "google_tag_manager": IntegrationProvider(
        code="google_tag_manager",
        display_name="گوگل تگ منیجر (GTM)",
        category=IntegrationCategory.ANALYTICS,
        description="شناسه‌ی کانتینر GTM را ذخیره می‌کنید؛ ردیابی فقط با فعال‌بودنِ پلتفرم و انتشار روی آدرس عمومی بارگذاری می‌شود. اگر داخل GTM تگ GA4 دارید، GA4 را جداگانه فعال نکنید.",
        setup_guide="https://tagmanager.google.com",
        fields=(IntegrationField(key="container_id", label="شناسه‌ی کانتینر", placeholder="GTM-XXXXXXX"),),
        validate=_require_pattern("container_id", "شناسه‌ی کانتینر", r"^GTM-[A-Z0-9]{4,8}$", "GTM-ABC1234"),
    ),
    "ad_pixel": IntegrationProvider(
        code="ad_pixel",
        display_name="پیکسلِ تبلیغاتی (متا/اینستاگرام)",
        category=IntegrationCategory.MARKETING,
        description="شناسه‌ی پیکسل متا را ذخیره می‌کنید؛ ردیابی فقط با فعال‌بودنِ پلتفرم و انتشار روی آدرس عمومی بارگذاری می‌شود.",
        setup_guide="https://business.facebook.com/events_manager",
        fields=(IntegrationField(key="pixel_id", label="شناسه‌ی پیکسل", placeholder="1234567890123456"),),
        validate=_require_pattern("pixel_id", "شناسه‌ی پیکسل", r"^\d{10,20}$", "1234567890123456"),
    ),
}


def get_provider(code: str) -> IntegrationProvider | None:
    return PROVIDERS.get(code)


def all_providers() -> list[IntegrationProvider]:
    return list(PROVIDERS.values())


PROVIDER_CHOICES = [(code, provider.display_name) for code, provider in PROVIDERS.items()]
