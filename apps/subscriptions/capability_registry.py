"""رجیستریِ **کد-مالکِ** قابلیت‌هایِ اعمال‌شده — تنها مرجعِ «این کلید واقعاً در Backend اعمال می‌شود».

اصل: مالکِ پلتفرم می‌تواند در Platform Admin هر تعدادِ «تعریفِ قابلیت» (حتی برایِ آینده) بسازد و به پلن‌ها نسبت دهد، امّا **هیچ تعریفی
به‌تنهایی دسترسی نمی‌دهد**. دسترسیِ واقعی فقط وقتی ممکن است که:

1. کلیدِ Entitlementِ آن در همین رجیستری ثبت شده باشد (یعنی توسعه‌دهنده گیتِ سرویس را نوشته و تستِ رفتاری دارد)،
2. وضعیتِ فنی «آماده» و وضعیتِ تجاری «در دسترس» باشد، و
3. نسخه‌ی منتشرشده‌ی پلن آن را صراحتاً فعال کرده باشد (و پس از زمانِ فعال‌سازیِ قابلیت منتشر شده باشد).

افزودنِ یک قابلیتِ تازه به محصول = (الف) نوشتنِ گیت در سرویس (``enforcement.enforce_feature(store, key)`` یا ``check_entitlement``)،
(ب) افزودنِ یک ``Capability`` به ``CAPABILITIES`` با ``enforced_by`` و ``tests``، (ج) تست. رجیستری کد است، نه داده؛ پس یک رکوردِ
دیتابیس هرگز نمی‌تواند یک کلیدِ دلخواه را «اعمال‌شده» اعلام کند."""

from contextlib import contextmanager
from dataclasses import dataclass

from apps.subscriptions import entitlements as ekeys

DOMAINS_CUSTOM = "domains.custom"


@dataclass(frozen=True)
class Capability:
    key: str
    enforced_by: str          # مسیرِ نقطه‌ی اعمال (برایِ ممیزی)
    tests: tuple = ()         # تست‌هایِ رفتاریِ دسترسی/سقف
    note: str = ""


CAPABILITIES: dict[str, Capability] = {c.key: c for c in (
    Capability(ekeys.CATALOG_PRODUCTS, "apps/subscriptions/services/enforcement.py::enforce_can_create_product", ("apps/subscriptions/tests/test_creation_limits.py",)),
    Capability(ekeys.CATALOG_VARIANTS, "apps/catalog/services/variant_engine_service.py", ("apps/subscriptions/tests/test_creation_limits.py",)),
    Capability(ekeys.CATALOG_IMPORT, "apps/subscriptions/services/enforcement.py::enforce_import_allowed", ("apps/subscriptions/tests/test_import_export_limits.py",)),
    Capability(ekeys.CATALOG_EXPORT, "apps/subscriptions/services/enforcement.py::enforce_export_allowed", ("apps/subscriptions/tests/test_import_export_limits.py",)),
    Capability(ekeys.CATALOG_IMPORT_ROWS_MONTHLY, "apps/subscriptions/services/enforcement.py::check_import_row_budget", ("apps/subscriptions/tests/test_import_export_limits.py",)),
    Capability(ekeys.CATALOG_EXPORTS_MONTHLY, "apps/subscriptions/services/enforcement.py::check_export_budget", ("apps/subscriptions/tests/test_import_export_limits.py",)),
    Capability(ekeys.INVENTORY_WAREHOUSES, "apps/catalog/services/warehouse_service.py", ("apps/subscriptions/tests/test_creation_limits.py",)),
    Capability(ekeys.CUSTOMERS_SEGMENTS, "apps/subscriptions/services/enforcement.py::enforce_can_create_segment", ("apps/subscriptions/tests/test_creation_limits.py",)),
    Capability(ekeys.STAFF_MEMBERS, "apps/stores/services/membership_service.py", ("apps/subscriptions/tests/test_creation_limits.py",)),
    Capability(DOMAINS_CUSTOM, "apps/stores/services/domain_verification_service.py::request_custom_domain",
               ("apps/subscriptions/tests/test_pricing_dynamic.py",), note="با grandfathering (EntitlementDefinition.enforced_from)"),
)}


def is_registered(key: str) -> bool:
    return key in CAPABILITIES


def registered_keys() -> frozenset:
    return frozenset(CAPABILITIES)


@contextmanager
def registered_for_test(*capabilities: Capability):
    """فقط برایِ تست: ثبتِ موقتِ یک قابلیت (شبیه‌سازیِ «توسعه‌دهنده گیت را نوشت و ثبت کرد») بدونِ آلوده‌کردنِ رجیستری."""
    added = []
    try:
        for cap in capabilities:
            if cap.key not in CAPABILITIES:
                CAPABILITIES[cap.key] = cap
                added.append(cap.key)
        yield
    finally:
        for key in added:
            CAPABILITIES.pop(key, None)
