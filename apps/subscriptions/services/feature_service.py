"""مدیریتِ قابلیت‌ها و نسبت‌دادنِ آن‌ها به پلن‌ها — **همه‌ی تغییرها حسابرسی می‌شوند** (کنشگر، زمان، قبل/بعد).

اصول (نگاه کنید به ``capability_registry`` و ``feature_gate``):

* مالکِ پلتفرم می‌تواند قابلیتِ آینده را تعریف و به پلن‌ها نسبت دهد؛ این **هیچ دسترسیِ واقعی نمی‌دهد**.
* «آمادگیِ فنی = آماده» فقط برایِ قابلیتی که کلیدِ Entitlementش در رجیستریِ **کد** ثبت شده؛ «در دسترس» فقط پس از آمادگیِ فنی.
* نسخه‌ی منتشرشده تغییرناپذیر است؛ نسبت‌دادن فقط روی نسخه‌ی پیش‌نویس انجام می‌شود.
* از «در دسترس» نمی‌توان بی‌صدا به «به‌زودی/برنامه‌ریزی» برگشت (دسترسیِ قراردادیِ مشترکان را می‌گرفت)؛ مسیرِ درست «جمع‌شده»
  (دسترسیِ نسخه‌هایِ قبلی حفظ، فروشِ تازه بسته) یا قطعِ اضطراریِ صریح است."""

import re
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from apps.subscriptions import capability_registry
from apps.subscriptions.models import EntitlementDefinition, PlanEntitlement, PlanVersion, PricingFeature
from apps.subscriptions.services import feature_gate
from apps.subscriptions.services.plan_service import PlanServiceError, set_plan_entitlement

_FEATURE_KEY = re.compile(r"^[a-z][a-z0-9_]{1,60}$")
_ENTITLEMENT_KEY = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$")
TS, CS, VT = PricingFeature.TechnicalStatus, PricingFeature.CommercialStatus, PricingFeature.ValueType
_DEF_TYPE = {
    VT.BOOLEAN: EntitlementDefinition.EntitlementType.BOOLEAN,
    VT.INTEGER_LIMIT: EntitlementDefinition.EntitlementType.INTEGER_LIMIT,
    VT.DECIMAL_LIMIT: EntitlementDefinition.EntitlementType.DECIMAL_LIMIT,
    VT.TEXT: EntitlementDefinition.EntitlementType.TEXT_VALUE,
}


class FeatureError(PlanServiceError):
    """خطای قابلِ‌نمایشِ مدیریتِ قابلیت."""


def snapshot(feature) -> dict:
    return {
        "key": feature.key, "title": feature.title, "category": feature.category, "icon": feature.icon,
        "value_type": feature.value_type, "unit": feature.unit_label, "technical": feature.technical_status,
        "commercial": feature.commercial_status, "visible": feature.is_visible, "kill_switch": feature.kill_switch,
        "planned_release_on": str(feature.planned_release_on or ""), "entitlement": feature.entitlement.key if feature.entitlement_id else "",
        "schema": dict(feature.config_schema or {}),
    }


def _audit(actor, action, feature, before=None, after=None, **meta):
    from apps.portal.services.platform_config_service import record_platform_audit_event

    record_platform_audit_event(
        actor=actor, action_code=f"platform_admin.feature_{action}", object_type="PricingFeature",
        object_id=feature.pk, object_label=feature.key, before=before, after=after, metadata=meta,
    )


def _validate_schema(schema):
    if not isinstance(schema, dict):
        raise FeatureError("طرحِ سهمیه باید یک شیءِ JSON باشد.")
    for name in ("min", "max", "step"):
        if name in schema and schema[name] not in (None, ""):
            try:
                value = Decimal(str(schema[name]))
            except InvalidOperation:
                raise FeatureError(f"«{name}» در طرحِ سهمیه عدد نیست.")
            if value < 0:
                raise FeatureError(f"«{name}» در طرحِ سهمیه منفی است.")
    if "min" in schema and "max" in schema and schema["min"] is not None and schema["max"] is not None:
        if Decimal(str(schema["min"])) > Decimal(str(schema["max"])):
            raise FeatureError("حداقلِ سهمیه از حداکثر بزرگ‌تر است.")
    return {k: v for k, v in schema.items() if k in ("min", "max", "step", "options", "note")}


@transaction.atomic
def create_feature(*, actor, key, title, category, entitlement_key="", description="", help_text="", icon="", value_type=VT.BOOLEAN,
                   unit_label="", config_schema=None, commercial_status=CS.COMING_SOON, planned_release_on=None, is_visible=True):
    """قابلیتِ تازه (حتی پیش از پیاده‌سازی). فقط تعریف می‌سازد: آمادگیِ فنی «برنامه‌ریزی‌شده»، **بدونِ هیچ دسترسی**."""
    key = (key or "").strip()
    if not _FEATURE_KEY.match(key):
        raise FeatureError("کلیدِ قابلیت باید انگلیسیِ کوچک، با حرف شروع شود و فقط شاملِ حرف/رقم/زیرخط باشد (۲ تا ۶۱ نویسه).")
    if PricingFeature.objects.filter(key=key).exists():
        raise FeatureError("قابلیتی با این کلید از قبل وجود دارد؛ کلیدِ قابلیت پایدار و یکتاست.")
    if category not in PricingFeature.Category.values:
        raise FeatureError("دسته‌ی نامعتبر.")
    if value_type not in VT.values:
        raise FeatureError("نوعِ مقدارِ نامعتبر.")
    if not (title or "").strip():
        raise FeatureError("نامِ فارسیِ قابلیت الزامی است.")
    if commercial_status not in (CS.PLANNED, CS.COMING_SOON):
        raise FeatureError("قابلیتِ تازه فقط با وضعیتِ «در برنامه» یا «به‌زودی» ساخته می‌شود؛ «در دسترس» پس از آمادگیِ فنی ممکن است.")
    ent_key = (entitlement_key or f"custom.{key}").strip()
    if not _ENTITLEMENT_KEY.match(ent_key):
        raise FeatureError("کلیدِ حق‌دسترسی باید مانندِ «ai.assistant» باشد (حروفِ کوچک، با نقطه).")
    if PricingFeature.objects.filter(entitlement__key=ent_key).exists():
        raise FeatureError("این کلیدِ حق‌دسترسی به قابلیتِ دیگری وصل است.")
    schema = _validate_schema(config_schema or {})
    definition, created = EntitlementDefinition.objects.get_or_create(
        key=ent_key, defaults={"name": title.strip()[:120], "entitlement_type": _DEF_TYPE[value_type], "default_enabled": False, "is_active": True},
    )
    if not created and definition.entitlement_type != _DEF_TYPE[value_type]:
        raise FeatureError("این کلیدِ حق‌دسترسی از قبل با نوعِ مقدارِ دیگری تعریف شده است.")
    order = (PricingFeature.objects.filter(category=category).order_by("-display_order").values_list("display_order", flat=True).first() or 0) + 10
    feature = PricingFeature.objects.create(
        key=key, category=category, title=title.strip()[:140], description=(description or "").strip(), help_text=(help_text or "").strip(),
        icon=(icon or "").strip()[:24], value_type=value_type, unit_label=(unit_label or "").strip()[:30], config_schema=schema,
        is_custom=True, technical_status=TS.PLANNED, commercial_status=commercial_status, planned_release_on=planned_release_on or None,
        is_visible=bool(is_visible), entitlement=definition, availability=PricingFeature.Availability.PLANNED, display_order=order,
    )
    feature_gate.invalidate()
    _audit(actor, "created", feature, after=snapshot(feature))
    return feature


@transaction.atomic
def update_feature(*, actor, feature, **fields):
    """متنِ نمایشی/آیکون/دسته/واحد/طرحِ سهمیه/تاریخ/نمایش. کلید و اتصالِ حق‌دسترسی پایدارند و تغییر نمی‌کنند."""
    feature = PricingFeature.objects.select_for_update().get(pk=feature.pk)
    before = snapshot(feature)
    editable = {"title", "description", "help_text", "icon", "unit_label", "planned_release_on", "is_visible", "display_order"}
    if feature.is_custom:
        editable |= {"category", "config_schema"}
    for name, value in fields.items():
        if name not in editable:
            raise FeatureError(f"فیلدِ «{name}» قابلِ ویرایش نیست.")
        if name == "category" and value not in PricingFeature.Category.values:
            raise FeatureError("دسته‌ی نامعتبر.")
        if name == "config_schema":
            value = _validate_schema(value or {})
        if name == "title" and not (value or "").strip():
            raise FeatureError("نامِ فارسیِ قابلیت الزامی است.")
        setattr(feature, name, value)
    feature.save()
    _audit(actor, "updated", feature, before=before, after=snapshot(feature))
    return feature


@transaction.atomic
def set_technical_status(*, actor, feature, status):
    feature = PricingFeature.objects.select_related("entitlement").select_for_update(of=("self",)).get(pk=feature.pk)
    if status not in TS.values:
        raise FeatureError("وضعیتِ فنیِ نامعتبر.")
    if not feature.is_custom:
        raise FeatureError("آمادگیِ فنیِ قابلیت‌هایِ کد-مالک از کاتالوگِ کد می‌آید، نه از پنل.")
    before = snapshot(feature)
    if status == TS.READY:
        if not feature.entitlement_id:
            raise FeatureError("برایِ «آماده» قابلیت باید به یک حق‌دسترسی وصل باشد.")
        if not capability_registry.is_registered(feature.entitlement.key):
            raise FeatureError(
                f"کلیدِ «{feature.entitlement.key}» هنوز در رجیستریِ کد (capability_registry) ثبت نشده؛ تا گیتِ Backend و تستِ آن نوشته و ثبت نشود "
                "نمی‌توان آن را «آماده» کرد."
            )
    elif feature.commercial_status == CS.AVAILABLE:
        raise FeatureError("قابلیتِ «در دسترس» را نمی‌توان فنیاً به عقب برد؛ ابتدا «جمع‌شده» یا قطعِ اضطراری را انتخاب کنید.")
    feature.technical_status = status
    feature.save(update_fields=["technical_status", "updated_at"])
    _audit(actor, "technical_status", feature, before=before, after=snapshot(feature))
    return feature


@transaction.atomic
def set_commercial_status(*, actor, feature, status, planned_release_on=None):
    feature = PricingFeature.objects.select_related("entitlement").select_for_update(of=("self",)).get(pk=feature.pk)
    if status not in CS.values:
        raise FeatureError("وضعیتِ تجاریِ نامعتبر.")
    before = snapshot(feature)
    current = feature.commercial_status
    if status == CS.AVAILABLE:
        if not feature.is_technically_ready:
            raise FeatureError("تا آمادگیِ فنیِ واقعی (ثبت در رجیستریِ کد + وضعیتِ «آماده») قابلیت «در دسترس» نمی‌شود.")
        if feature.kill_switch:
            raise FeatureError("قطعِ اضطراری فعال است.")
        if current != CS.AVAILABLE:
            feature.activated_at = timezone.now()
    elif current == CS.AVAILABLE and status in (CS.PLANNED, CS.COMING_SOON):
        raise FeatureError("از «در دسترس» به «به‌زودی/در برنامه» برگشت دسترسیِ قراردادیِ مشترکان را می‌گیرد؛ «جمع‌شده» (حفظِ دسترسیِ نسخه‌هایِ قبلی) یا قطعِ اضطراری را استفاده کنید.")
    feature.commercial_status = status
    if planned_release_on is not None:
        feature.planned_release_on = planned_release_on or None
    feature.save()
    _audit(actor, "commercial_status", feature, before=before, after=snapshot(feature))
    return feature


@transaction.atomic
def set_kill_switch(*, actor, feature, on, reason=""):
    feature = PricingFeature.objects.select_for_update().get(pk=feature.pk)
    if on and not (reason or "").strip():
        raise FeatureError("برایِ قطعِ اضطراری دلیل الزامی است.")
    before = snapshot(feature)
    feature.kill_switch = bool(on)
    feature.save(update_fields=["kill_switch", "updated_at"])
    _audit(actor, "kill_switch", feature, before=before, after=snapshot(feature), reason=(reason or "")[:200])
    return feature


# ---------------------------------------------------------------------------------------------------- نسبت‌دادن به پلن

def validate_assignment(feature, *, enabled, limit=None, unlimited=False):
    """مقدارِ نسبت‌داده‌شده با نوعِ قابلیت و طرحِ سهمیه اعتبارسنجی می‌شود (مثلاً min/max)."""
    if not feature.entitlement_id:
        raise FeatureError("این قابلیت به حق‌دسترسی وصل نیست؛ نسبت‌دادن به پلن ممکن نیست.")
    if feature.value_type == VT.BOOLEAN:
        return {"is_enabled": bool(enabled), "is_unlimited": False, "integer_limit": None, "decimal_limit": None}
    if not enabled:          # خاموش‌کردنِ قابلیتِ سقف‌دار: ردیفِ معتبر با سقفِ صفر (has_entitlement=False)
        zero = {VT.INTEGER_LIMIT: {"integer_limit": 0, "decimal_limit": None}, VT.DECIMAL_LIMIT: {"integer_limit": None, "decimal_limit": Decimal(0)}}.get(
            feature.value_type, {"integer_limit": None, "decimal_limit": None})
        return {"is_enabled": False, "is_unlimited": False, **zero}
    if unlimited:
        return {"is_enabled": True, "is_unlimited": True, "integer_limit": None, "decimal_limit": None}
    schema = feature.config_schema or {}
    if feature.value_type == VT.INTEGER_LIMIT:
        try:
            number = Decimal(str(limit))
        except (InvalidOperation, ValueError):
            raise FeatureError("سقفِ عددی معتبر نیست.")
        if number < 0 or number != number.to_integral_value():
            raise FeatureError("سقفِ عددی باید عددِ صحیحِ غیرمنفی باشد.")
        out = {"is_enabled": True, "is_unlimited": False, "integer_limit": int(number), "decimal_limit": None}
    elif feature.value_type == VT.DECIMAL_LIMIT:
        try:
            number = Decimal(str(limit))
        except (InvalidOperation, ValueError):
            raise FeatureError("سقفِ اعشاری معتبر نیست.")
        if number < 0:
            raise FeatureError("سقف نمی‌تواند منفی باشد.")
        out = {"is_enabled": True, "is_unlimited": False, "integer_limit": None, "decimal_limit": number}
    else:
        return {"is_enabled": True, "is_unlimited": False, "integer_limit": None, "decimal_limit": None}
    if schema.get("min") not in (None, "") and number < Decimal(str(schema["min"])):
        raise FeatureError(f"مقدار از حداقلِ مجاز ({schema['min']}) کمتر است.")
    if schema.get("max") not in (None, "") and number > Decimal(str(schema["max"])):
        raise FeatureError(f"مقدار از حداکثرِ مجاز ({schema['max']}) بیشتر است.")
    return out


@transaction.atomic
def assign_to_plan_version(*, actor, plan_version, feature, enabled, limit=None, unlimited=False):
    """نسبت‌دادن/برداشتنِ قابلیت روی نسخه‌ی **پیش‌نویس**. برایِ قابلیتِ برنامه‌ریزی‌شده «برنامه‌ی پلن» است و دسترسی نمی‌دهد."""
    status = PlanVersion.objects.filter(pk=plan_version.pk).values_list("status", flat=True).first()
    if status != PlanVersion.Status.DRAFT:
        raise FeatureError("نسبت‌دادنِ قابلیت فقط روی نسخه‌ی «پیش‌نویس» ممکن است؛ نسخه‌ی منتشرشده تغییرناپذیر است.")
    feature = PricingFeature.objects.select_related("entitlement").get(pk=feature.pk)
    values = validate_assignment(feature, enabled=enabled, limit=limit, unlimited=unlimited)
    existing = PlanEntitlement.objects.filter(plan_version=plan_version, entitlement=feature.entitlement).first()
    before = ({"enabled": existing.is_enabled, "unlimited": existing.is_unlimited, "limit": existing.integer_limit if existing.integer_limit is not None else (str(existing.decimal_limit) if existing.decimal_limit is not None else None)}
              if existing else None)
    set_plan_entitlement(plan_version, feature.entitlement.key, **values)
    after = {"enabled": values["is_enabled"], "unlimited": values["is_unlimited"],
             "limit": values["integer_limit"] if values["integer_limit"] is not None else (str(values["decimal_limit"]) if values["decimal_limit"] is not None else None)}
    from apps.portal.services.platform_config_service import record_platform_audit_event

    record_platform_audit_event(
        actor=actor, action_code="platform_admin.feature_assigned", object_type="PlanVersion", object_id=plan_version.pk,
        object_label=f"{plan_version.plan.code} v{plan_version.version_number} · {feature.key}", before=before, after=after,
        metadata={"grants_access_now": feature.grants_access},
    )
    return after


def access_status(feature, plan_version) -> dict:
    """وضعیتِ یک سلولِ ماتریسِ تخصیص برایِ یک نسخه: ``state`` ∈ none | planned | active و دلیلِ فارسی.

    ``planned`` = نسخه قابلیت را فعال (برنامه‌ریزی) کرده امّا *همین الان دسترسیِ واقعی نمی‌دهد*؛ ``active`` = گیتِ Backend اجازه می‌دهد.
    همان ``feature_gate.allows`` که محصول اعمال می‌کند، بدونِ کپیِ منطق."""
    if not feature.entitlement_id:
        return {"state": "none", "reason": "بدونِ حق‌دسترسی"}
    row = PlanEntitlement.objects.filter(plan_version=plan_version, entitlement=feature.entitlement).first()
    if row is None or not row.is_enabled:
        return {"state": "none", "reason": ""}
    if feature.kill_switch:
        return {"state": "planned", "reason": "قطعِ اضطراری فعال است"}
    if not capability_registry.is_registered(feature.entitlement.key):
        return {"state": "planned", "reason": "گیتِ Backend هنوز در کد ثبت نشده"}
    if not feature.is_technically_ready:
        return {"state": "planned", "reason": "آمادگیِ فنی تأیید نشده"}
    if feature.commercial_status not in (CS.AVAILABLE, CS.WITHDRAWN):
        return {"state": "planned", "reason": "هنوز «در دسترس» اعلام نشده"}
    if not feature_gate.allows(feature.entitlement.key, plan_version):
        return {"state": "planned", "reason": "این نسخه پیش از فعال‌شدنِ قابلیت منتشر شده؛ نسخه‌ی تازه منتشر کنید"}
    return {"state": "active", "reason": ""}


def assignable_features():
    """قابلیت‌هایی که نسبت‌دادنِ آن‌ها به پلن معنا دارد: دارایِ حق‌دسترسی و (ساخته‌ی مالک یا ثبت‌شده در رجیستریِ کد)."""
    rows = PricingFeature.objects.filter(entitlement__isnull=False).select_related("entitlement").order_by("category", "display_order", "key")
    return [f for f in rows if f.is_custom or capability_registry.is_registered(f.entitlement.key)]
