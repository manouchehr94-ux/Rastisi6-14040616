"""موتورِ قاعده‌یِ سگمنتِ مشتری — checkpoint 4 §18-20، نگاه کنید به ADR-53 در
``SAAS_DOMAIN_DECISIONS.md``.

فقط فیلدها/عملگرهایِ صراحتاً allowlistشده در ``ALLOWED_FIELDS``/``OPERATORS``
این‌جا قابل‌استفاده‌اند — هرگز یک زبانِ عبارتِ آزاد/eval. هر قاعده به‌صورتِ
مستقل به یک کوئریِ Store-scoped (نه پیمایشِ ردیف‌به‌ردیفِ پایتونی) ترجمه
می‌شود که مجموعه‌ای از شناسه‌هایِ Customer برمی‌گرداند؛ ترکیبِ چند قاعده
(match_mode: all/any) با عملیاتِ مجموعه‌ای (اشتراک/اجتماع) رویِ همین
شناسه‌ها انجام می‌شود — نه جوینِ چندگانه‌یِ annotate که می‌تواند fan-out
نادرست تولید کند."""

import time
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db.models import Count, Max, Min, Q, Sum
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from apps.core.services.audit_service import record_audit_event
from apps.customers.models import Customer, CustomerSegment, CustomerSegmentMembership, CustomerSegmentRule
from apps.orders.models import Refund
from apps.orders.services import order_definitions


class SegmentError(Exception):
    """خطای قابل‌نمایشِ مستقیم به کاربر — قاعده/فیلد/عملگرِ نامعتبر."""


NUMERIC_OPERATORS = ["equals", "not_equals", "greater_than", "greater_than_or_equal", "less_than", "less_than_or_equal"]
DATE_OPERATORS = ["before", "after", "between"]

ALLOWED_FIELDS = {
    "order_count": {"label": "تعداد سفارش", "value_type": "int", "operators": NUMERIC_OPERATORS},
    "total_spent": {"label": "مجموع خرید (پرداخت‌شده)", "value_type": "decimal", "operators": NUMERIC_OPERATORS},
    "last_order_at": {"label": "تاریخ آخرین سفارش", "value_type": "date", "operators": DATE_OPERATORS},
    "first_order_at": {"label": "تاریخ اولین سفارش", "value_type": "date", "operators": DATE_OPERATORS},
    "no_purchase_for_days": {
        "label": "بدونِ خرید به مدتِ حداقل (روز)", "value_type": "int",
        "operators": ["greater_than", "greater_than_or_equal"],
    },
    "has_purchased_product": {"label": "خریدِ کالایِ مشخص (شناسه)", "value_type": "id", "operators": ["contains"]},
    "has_purchased_category": {"label": "خریدِ دسته‌یِ مشخص (شناسه)", "value_type": "id", "operators": ["contains"]},
    "has_used_coupon": {"label": "استفاده از کدِ تخفیفِ مشخص (شناسه)", "value_type": "id", "operators": ["contains"]},
    "customer_tag": {"label": "دارایِ برچسبِ مشخص (شناسه)", "value_type": "id", "operators": ["in"]},
    "refund_count": {"label": "تعدادِ استردادِ موفق", "value_type": "int", "operators": NUMERIC_OPERATORS},
}

OPERATOR_LABELS = {
    "equals": "برابر با", "not_equals": "نابرابر با",
    "greater_than": "بیشتر از", "greater_than_or_equal": "بیشتر یا مساویِ",
    "less_than": "کمتر از", "less_than_or_equal": "کمتر یا مساویِ",
    "before": "پیش از", "after": "پس از", "between": "بینِ",
    "contains": "شاملِ", "in": "در میانِ",
}


def field_choices():
    return [(key, meta["label"]) for key, meta in ALLOWED_FIELDS.items()]


def operators_for_field(field: str):
    meta = ALLOWED_FIELDS.get(field)
    if meta is None:
        return []
    return [(op, OPERATOR_LABELS[op]) for op in meta["operators"]]


def validate_rule(field: str, operator: str) -> None:
    """اعتبارسنجیِ عمومیِ یک جفتِ فیلد/عملگر در برابرِ ``ALLOWED_FIELDS`` —
    هم موتورِ ارزیابی و هم ویوِ ذخیره‌ی فرم از همین تابع استفاده می‌کنند تا
    هرگز دو قاعده‌ی اعتبارسنجیِ متفاوت پیدا نشود."""
    meta = ALLOWED_FIELDS.get(field)
    if meta is None:
        raise SegmentError(f"فیلدِ «{field}» مجاز نیست.")
    if operator not in meta["operators"]:
        raise SegmentError(f"عملگرِ «{operator}» برایِ فیلدِ «{field}» مجاز نیست.")


def _to_number(raw: str, value_type: str):
    try:
        return int(raw) if value_type == "int" else Decimal(raw)
    except (TypeError, ValueError, InvalidOperation):
        raise SegmentError(f"مقدارِ «{raw}» یک عددِ معتبر نیست.")


def _to_datetime(raw: str):
    parsed = parse_datetime(raw)
    if parsed is None:
        parsed_date = parse_date(raw)
        if parsed_date is not None:
            parsed = timezone.datetime.combine(parsed_date, timezone.datetime.min.time())
    if parsed is None:
        raise SegmentError(f"مقدارِ «{raw}» یک تاریخِ معتبر نیست.")
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed)
    return parsed


def _numeric_q(annotation_field: str, operator: str, value) -> Q:
    lookup = {
        "equals": f"{annotation_field}__exact", "not_equals": f"{annotation_field}__exact",
        "greater_than": f"{annotation_field}__gt", "greater_than_or_equal": f"{annotation_field}__gte",
        "less_than": f"{annotation_field}__lt", "less_than_or_equal": f"{annotation_field}__lte",
    }[operator]
    q = Q(**{lookup: value})
    return ~q if operator == "not_equals" else q


def current_definition() -> order_definitions.CustomerOrderDefinition:
    """تعریفِ سفارشِ آمارِ مشتری که سگمنت‌ها با آن ارزیابی می‌شوند. پیش‌فرض ``legacy``
    (رفتارِ تاریخی)؛ تغییرِ آن (``settings.SEGMENT_ORDER_DEFINITION = "valid"``) عضویتِ
    سگمنت‌ها را عوض می‌کند و فقط پس از تأییدِ مالک (و گزارشِ ``analyze_segment_definitions``) مجاز است.
    مقدارِ ناشناخته ⇒ ``legacy`` (fail-safe)."""
    return order_definitions.DEFINITIONS.get(
        getattr(settings, "SEGMENT_ORDER_DEFINITION", "legacy"), order_definitions.LEGACY,
    )


def _matching_customer_ids(store, rule: CustomerSegmentRule, definition=None) -> set:
    """شناسه‌هایِ Customerِ منطبق با یک قاعده‌ی تکی را برمی‌گرداند — همیشه
    Store-scoped، همیشه یک کوئریِ مستقل (نه annotateهایِ ترکیبی که می‌توانند
    فان‌اوت غلط بدهند). ``definition``: کدام سفارش‌ها شمرده شوند (نگاه کنید به
    ``order_definitions``)؛ پیش‌فرض ``current_definition()``."""
    validate_rule(rule.field, rule.operator)
    meta = ALLOWED_FIELDS[rule.field]
    d = definition or current_definition()
    in_store = Q(orders__store=store)

    base = Customer.objects.filter(orders__store=store)

    # نامِ annotationها عمداً پیشوندِ ``_seg_`` دارند — ``Customer`` خودش
    # فیلدهایِ واقعیِ ``total_spent``/... دارد (سراسری، نه Store-scoped؛
    # نگاه کنید به ADR-50)؛ نامِ annotation نباید با آن‌ها یکسان باشد وگرنه
    # Django's ``annotate`` خطای تداخل می‌دهد.
    if rule.field in ("order_count", "total_spent", "first_order_at", "last_order_at"):
        annotation_field = f"_seg_{rule.field}"
        annotated = base.annotate(**{
            "_seg_order_count": Count("orders", filter=in_store & d.count_q, distinct=True),
            "_seg_total_spent": Sum("orders__grand_total", filter=in_store & d.spent_q),
            "_seg_first_order_at": Min("orders__created_at", filter=in_store & d.activity_q),
            "_seg_last_order_at": Max("orders__created_at", filter=in_store & d.activity_q),
        })
        if meta["value_type"] in ("int", "decimal"):
            value = _to_number(rule.value, meta["value_type"])
            qs = annotated.filter(_numeric_q(annotation_field, rule.operator, value))
        else:
            if rule.operator == "between":
                start, end = _to_datetime(rule.value), _to_datetime(rule.value2)
                qs = annotated.filter(**{f"{annotation_field}__gte": start, f"{annotation_field}__lte": end})
            elif rule.operator == "before":
                qs = annotated.filter(**{f"{annotation_field}__lt": _to_datetime(rule.value)})
            else:
                qs = annotated.filter(**{f"{annotation_field}__gt": _to_datetime(rule.value)})
        return set(qs.values_list("pk", flat=True))

    if rule.field == "no_purchase_for_days":
        days = _to_number(rule.value, "int")
        cutoff = timezone.now() - timezone.timedelta(days=days)
        qs = base.annotate(
            _seg_last_order_at=Max("orders__created_at", filter=in_store & d.activity_q),
        ).filter(_seg_last_order_at__lte=cutoff)
        return set(qs.values_list("pk", flat=True))

    # شرطِ «سفارش + کالا/دسته/کد» باید روی *همان* سفارش باشد (یک ``filter`` واحد ⇒ یک join)،
    # هم در این Store و هم مطابقِ تعریفِ سفارشِ معتبر.
    if rule.field == "has_purchased_product":
        product_id = _to_number(rule.value, "int")
        qs = Customer.objects.filter(in_store & d.activity_q & Q(orders__items__product_id=product_id)).distinct()
        return set(qs.values_list("pk", flat=True))

    if rule.field == "has_purchased_category":
        category_id = _to_number(rule.value, "int")
        qs = Customer.objects.filter(in_store & d.activity_q & Q(orders__items__product__category_id=category_id)).distinct()
        return set(qs.values_list("pk", flat=True))

    if rule.field == "has_used_coupon":
        coupon_id = _to_number(rule.value, "int")
        qs = Customer.objects.filter(in_store & d.activity_q & Q(orders__coupon_id=coupon_id)).distinct()
        return set(qs.values_list("pk", flat=True))

    if rule.field == "customer_tag":
        tag_id = _to_number(rule.value, "int")
        qs = base.filter(store_profiles__store=store, store_profiles__tags__id=tag_id).distinct()
        return set(qs.values_list("pk", flat=True))

    if rule.field == "refund_count":
        # «تعدادِ استردادِ *موفق*» عمداً فقط SUCCEEDED (برچسبِ UI) — با «استردادِ فعال» (مبلغ) متفاوت و مشروع است.
        value = _to_number(rule.value, "int")
        qs = base.annotate(
            _seg_refund_count=Count(
                "orders__refunds",
                filter=Q(orders__refunds__store=store, orders__refunds__status=Refund.Status.SUCCEEDED),
                distinct=True,
            ),
        ).filter(_numeric_q("_seg_refund_count", rule.operator, value))
        return set(qs.values_list("pk", flat=True))

    raise SegmentError(f"فیلدِ «{rule.field}» پیاده‌سازی نشده است.")


def evaluate_segment(segment: CustomerSegment, definition=None) -> set:
    """مجموعه‌یِ شناسه‌هایِ Customerِ منطبق با قاعده‌هایِ یک سگمنتِ dynamic را
    برمی‌گرداند — بدونِ نوشتنِ چیزی در دیتابیس (preview-safe). سگمنتِ
    ``static`` را نباید با این تابع صدا زد — عضویتِ آن فقط دستی است."""
    rules = list(segment.rules.all())
    if not rules:
        return set()

    rule_sets = [_matching_customer_ids(segment.store, rule, definition) for rule in rules]
    if segment.match_mode == CustomerSegment.MatchMode.ANY:
        result = set()
        for s in rule_sets:
            result |= s
        return result
    result = rule_sets[0]
    for s in rule_sets[1:]:
        result &= s
    return result


def preview_segment(segment: CustomerSegment):
    """پیش‌نمایشِ زنده — بدونِ تغییرِ عضویتِ ذخیره‌شده. برایِ ``static`` همان
    عضویتِ فعلی را برمی‌گرداند."""
    if segment.segment_type == CustomerSegment.SegmentType.STATIC:
        return Customer.objects.filter(segment_memberships__segment=segment)
    ids = evaluate_segment(segment)
    return Customer.objects.filter(pk__in=ids)


def refresh_segment_membership(segment: CustomerSegment, *, actor=None) -> int:
    """عضویتِ محقق‌شده‌یِ یک سگمنتِ dynamic را با نتیجه‌یِ تازه‌یِ ارزیابی
    جایگزین می‌کند — برایِ ``static`` هیچ کاری نمی‌کند (عضویتِ آن فقط با
    اکشنِ دستیِ افزودن/حذف تغییر می‌کند، نه با این تابع)."""
    if segment.segment_type == CustomerSegment.SegmentType.STATIC:
        return segment.memberships.count()

    started = time.monotonic()
    try:
        matched_ids = evaluate_segment(segment)
    except SegmentError as exc:
        segment.last_evaluation_error = str(exc)
        segment.last_evaluated_at = timezone.now()
        segment.save(update_fields=["last_evaluation_error", "last_evaluated_at"])
        raise

    existing_ids = set(segment.memberships.values_list("customer_id", flat=True))
    to_add = matched_ids - existing_ids
    to_remove = existing_ids - matched_ids

    if to_remove:
        segment.memberships.filter(customer_id__in=to_remove).delete()
    if to_add:
        CustomerSegmentMembership.objects.bulk_create(
            [CustomerSegmentMembership(segment=segment, customer_id=cid) for cid in to_add],
            ignore_conflicts=True,
        )

    duration_ms = int((time.monotonic() - started) * 1000)
    segment.last_evaluated_at = timezone.now()
    segment.last_evaluation_duration_ms = duration_ms
    segment.last_evaluation_error = ""
    segment.save(update_fields=["last_evaluated_at", "last_evaluation_duration_ms", "last_evaluation_error"])

    record_audit_event(
        store=segment.store, actor=actor, action_code="customer_segment.refreshed",
        object_type="CustomerSegment", object_id=str(segment.pk), object_label=segment.name,
        after={"member_count": len(matched_ids), "duration_ms": duration_ms},
    )
    return len(matched_ids)


def add_static_member(segment: CustomerSegment, customer_id, *, actor=None) -> bool:
    if segment.segment_type != CustomerSegment.SegmentType.STATIC:
        raise SegmentError("فقط سگمنتِ دستی (static) عضوگیریِ دستی می‌پذیرد.")
    customer = Customer.objects.filter(pk=customer_id, orders__store=segment.store).distinct().first()
    if customer is None:
        return False
    _, created = CustomerSegmentMembership.objects.get_or_create(segment=segment, customer=customer)
    if created:
        record_audit_event(
            store=segment.store, actor=actor, action_code="customer_segment.member_added",
            object_type="CustomerSegment", object_id=str(segment.pk),
            object_label=f"{segment.name} — {customer.full_name}",
        )
    return created


def remove_static_member(segment: CustomerSegment, customer_id, *, actor=None) -> bool:
    if segment.segment_type != CustomerSegment.SegmentType.STATIC:
        raise SegmentError("فقط سگمنتِ دستی (static) حذفِ دستی می‌پذیرد.")
    deleted, _ = CustomerSegmentMembership.objects.filter(segment=segment, customer_id=customer_id).delete()
    if deleted:
        record_audit_event(
            store=segment.store, actor=actor, action_code="customer_segment.member_removed",
            object_type="CustomerSegment", object_id=str(segment.pk), object_label=segment.name,
        )
    return bool(deleted)
