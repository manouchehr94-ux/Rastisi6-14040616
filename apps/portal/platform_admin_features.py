"""مدیریتِ کاتالوگِ قابلیت‌ها، ماتریسِ تخصیصِ قابلیت↔پلن و مهاجرتِ مشترکان در Platform Admin.

همه‌ی تغییرها از ``feature_service`` / ``plan_service`` می‌گذرند (اعتبارسنجی + ممیزی)؛ این‌جا فقط HTTP است."""

from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.subscriptions import capability_registry
from apps.subscriptions.models import Plan, PlanVersion, PricingFeature
from apps.subscriptions.services import feature_service as fs
from apps.subscriptions.services import plan_service

from .platform_admin_views import _is_platform_staff

_LOGIN = "portal_platform_admin:login"


def _parse_date(raw):
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise fs.FeatureError("تاریخ باید به صورت YYYY-MM-DD (میلادی) باشد.")


def _schema_from_post(post):
    schema = {}
    for name in ("min", "max", "step"):
        raw = (post.get(f"schema_{name}") or "").strip()
        if raw:
            schema[name] = raw
    return schema


@user_passes_test(_is_platform_staff, login_url=_LOGIN)
def features(request):
    rows = []
    for f in PricingFeature.objects.select_related("entitlement").order_by("category", "display_order", "key"):
        rows.append({"f": f, "registered": f.is_registered, "state": f.public_state, "grants": f.grants_access})
    return render(request, "portal/platform_admin/features.html", {
        "rows": rows, "registered_keys": sorted(capability_registry.registered_keys()), "active_nav": "features",
    })


@user_passes_test(_is_platform_staff, login_url=_LOGIN)
def feature_form(request, feature_id=None):
    feature = get_object_or_404(PricingFeature.objects.select_related("entitlement"), pk=feature_id) if feature_id else None
    if request.method == "POST":
        action = request.POST.get("action", "save")
        try:
            if feature is None:
                feature = fs.create_feature(
                    actor=request.user, key=request.POST.get("key"), title=request.POST.get("title"), category=request.POST.get("category"),
                    entitlement_key=request.POST.get("entitlement_key", ""), description=request.POST.get("description", ""),
                    help_text=request.POST.get("help_text", ""), icon=request.POST.get("icon", ""),
                    value_type=request.POST.get("value_type") or "boolean", unit_label=request.POST.get("unit_label", ""),
                    config_schema=_schema_from_post(request.POST), commercial_status=request.POST.get("commercial_status") or "coming_soon",
                    planned_release_on=_parse_date(request.POST.get("planned_release_on")), is_visible=request.POST.get("is_visible") == "on",
                )
                messages.success(request, f"قابلیتِ «{feature.title}» ساخته شد؛ هنوز هیچ دسترسیِ واقعی نمی‌دهد (آمادگیِ فنی: برنامه‌ریزی‌شده).")
            elif action == "technical":
                fs.set_technical_status(actor=request.user, feature=feature, status=request.POST.get("technical_status"))
                messages.success(request, "آمادگیِ فنی به‌روز شد.")
            elif action == "commercial":
                fs.set_commercial_status(actor=request.user, feature=feature, status=request.POST.get("commercial_status"),
                                         planned_release_on=_parse_date(request.POST.get("planned_release_on")))
                messages.success(request, "وضعیتِ تجاری به‌روز شد.")
            elif action == "kill":
                fs.set_kill_switch(actor=request.user, feature=feature, on=request.POST.get("on") == "1", reason=request.POST.get("reason", ""))
                messages.success(request, "قطعِ اضطراری به‌روز شد.")
            else:
                fields = dict(
                    title=request.POST.get("title", ""), description=request.POST.get("description", ""), help_text=request.POST.get("help_text", ""),
                    icon=request.POST.get("icon", "")[:24], unit_label=request.POST.get("unit_label", ""), is_visible=request.POST.get("is_visible") == "on",
                    planned_release_on=_parse_date(request.POST.get("planned_release_on")),
                )
                if feature.is_custom:
                    fields.update(category=request.POST.get("category", feature.category), config_schema=_schema_from_post(request.POST))
                order = (request.POST.get("display_order") or "").strip()
                if order.isdigit():
                    fields["display_order"] = int(order)
                fs.update_feature(actor=request.user, feature=feature, **fields)
                messages.success(request, "ذخیره شد.")
            return redirect("portal_platform_admin:feature-edit", feature.pk)
        except (fs.FeatureError, plan_service.PlanServiceError) as exc:
            messages.error(request, str(exc))
    if feature is not None:
        feature.refresh_from_db()
    return render(request, "portal/platform_admin/feature_form.html", {
        "feature": feature, "categories": PricingFeature.Category.choices, "value_types": PricingFeature.ValueType.choices,
        "technical_choices": PricingFeature.TechnicalStatus.choices, "commercial_choices": PricingFeature.CommercialStatus.choices,
        "registered": feature.is_registered if feature else False, "schema": (feature.config_schema if feature else {}) or {},
        "post": request.POST if request.method == "POST" else {}, "active_nav": "features",
    })


@user_passes_test(_is_platform_staff, login_url=_LOGIN)
def assignment_matrix(request):
    """ماتریسِ «قابلیت × پلن»: ستون = نسخه‌ی پیش‌نویسِ هر پلن؛ هر خانه فعال/غیرفعال + سقف، با وضعیتِ دسترسیِ واقعی."""
    plans = list(Plan.objects.order_by("display_order", "code"))
    drafts = {p.pk: p.versions.filter(status=PlanVersion.Status.DRAFT).order_by("-version_number").first() for p in plans}
    published = {p.pk: p.versions.filter(status=PlanVersion.Status.PUBLISHED).order_by("-version_number").first() for p in plans}
    feats = fs.assignable_features()
    if request.method == "POST":
        action = request.POST.get("action")
        try:
            if action == "create_draft":
                plan = get_object_or_404(Plan, pk=request.POST.get("plan_id"))
                draft = plan_service.get_or_create_draft(plan, actor=request.user)
                messages.success(request, f"پیش‌نویسِ v{draft.version_number} پلنِ «{plan.name}» آماده‌ی ویرایش است.")
            else:
                changed = errors = 0
                for plan in plans:
                    draft = drafts[plan.pk]
                    if draft is None or f"present_{draft.pk}" not in request.POST:
                        continue
                    current = {pe.entitlement_id: pe for pe in draft.plan_entitlements.all()}
                    for f in feats:
                        if f"cell_{draft.pk}_{f.pk}" not in request.POST:
                            continue          # فقط خانه‌هایِ صراحتاً ارسال‌شده؛ نبودنِ علامت = «تغییرِ ناخواسته» نیست
                        enabled = request.POST.get(f"en_{draft.pk}_{f.pk}") == "on"
                        unlimited = request.POST.get(f"un_{draft.pk}_{f.pk}") == "on"
                        limit = (request.POST.get(f"lim_{draft.pk}_{f.pk}") or "").strip()
                        existing = current.get(f.entitlement_id)
                        if existing is None and not enabled:
                            continue          # بدونِ ردیف و خاموش = بدونِ تغییر
                        if existing is not None and existing.is_enabled == enabled and not enabled:
                            continue
                        try:
                            if enabled and f.value_type in ("integer_limit", "decimal_limit") and not unlimited and limit == "":
                                if existing is not None and existing.is_enabled:
                                    continue          # مقدارِ قبلی حفظ می‌شود
                                raise fs.FeatureError("برایِ قابلیتِ عددی سقف یا «نامحدود» را مشخص کنید.")
                            fs.assign_to_plan_version(actor=request.user, plan_version=draft, feature=f, enabled=enabled, limit=limit, unlimited=unlimited)
                            changed += 1
                        except fs.FeatureError as exc:
                            errors += 1
                            messages.error(request, f"{plan.name} · {f.title}: {exc}")
                if changed:
                    messages.success(request, f"{changed} تغییر روی پیش‌نویس‌ها ذخیره شد (نسخه‌ی منتشرشده تغییر نکرده است).")
                elif not errors:
                    messages.info(request, "تغییری برایِ ذخیره نبود.")
        except (fs.FeatureError, plan_service.PlanServiceError) as exc:
            messages.error(request, str(exc))
        return redirect("portal_platform_admin:assignment-matrix")
    columns = [{"plan": p, "draft": drafts[p.pk], "published": published[p.pk]} for p in plans]
    labels = dict(PricingFeature.Category.choices)
    rows = []
    for f in feats:
        cells = []
        for col in columns:
            draft, pub = col["draft"], col["published"]
            entry = {"draft": None, "published": None}
            if draft is not None:
                pe = draft.plan_entitlements.filter(entitlement=f.entitlement).first()
                entry["draft"] = {"pk": draft.pk, "pe": pe, "enabled": bool(pe and pe.is_enabled), "unlimited": bool(pe and pe.is_unlimited),
                                  "limit": (pe.integer_limit if pe and pe.integer_limit is not None else (pe.decimal_limit if pe and pe.decimal_limit is not None else ""))}
            if pub is not None:
                entry["published"] = fs.access_status(f, pub)
            cells.append(entry)
        rows.append({"f": f, "category": labels.get(f.category, f.category), "cells": cells, "limited": f.value_type in ("integer_limit", "decimal_limit")})
    not_assignable = [f for f in PricingFeature.objects.filter(is_visible=True).select_related("entitlement") if f not in feats][:200]
    return render(request, "portal/platform_admin/assignment_matrix.html", {
        "columns": columns, "rows": rows, "not_assignable_count": len(not_assignable), "active_nav": "assignments",
    })


@user_passes_test(_is_platform_staff, login_url=_LOGIN)
def plan_migration(request, plan_id):
    """مهاجرتِ صریحِ مشترکان بینِ دو نسخه‌ی یک پلن؛ پیش‌فرضِ محصول grandfathering است (بدونِ مهاجرت)."""
    plan = get_object_or_404(Plan, pk=plan_id)
    versions = list(plan.versions.exclude(status=PlanVersion.Status.DRAFT).order_by("-version_number"))
    preview = None
    src = dst = None
    data = request.POST if request.method == "POST" else request.GET
    if data.get("from") and data.get("to"):
        src = next((v for v in versions if str(v.pk) == data.get("from")), None)
        dst = next((v for v in versions if str(v.pk) == data.get("to")), None)
        if src and dst and src.pk != dst.pk:
            try:
                preview = plan_service.plan_migration_preview(src, dst)
            except plan_service.PlanServiceError as exc:
                messages.error(request, str(exc))
    if request.method == "POST" and request.POST.get("action") == "execute" and preview is not None:
        try:
            moved = plan_service.migrate_subscribers(src, dst, actor=request.user, reason=request.POST.get("reason", ""),
                                                     accept_losses=request.POST.get("accept_losses") == "on")
            messages.success(request, f"{moved} مشترک به v{dst.version_number} منتقل شد.")
            return redirect("portal_platform_admin:plan-migration", plan.pk)
        except plan_service.PlanServiceError as exc:
            messages.error(request, str(exc))
    return render(request, "portal/platform_admin/plan_migration.html", {
        "plan": plan, "versions": versions, "src": src, "dst": dst, "preview": preview, "active_nav": "plans",
    })
