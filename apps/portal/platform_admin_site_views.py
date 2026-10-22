"""Platform Admin: edit the public marketing website (texts, colours, fonts) and switch
between the new and the previous design. Platform owner (superuser) only; host-isolated like
the rest of Platform Admin. Never touches storefront/tenant data."""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.db import transaction
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from apps.stores.hostnames import build_cross_host_url

from .models import PublicSiteSetting
from .public_site import registry, services
from .services.platform_config_service import record_platform_audit_event

LOGIN = "portal_platform_admin:login"
_GROUPS = {g.slug: g for g in registry.GROUPS}
_RESET_PREFIX = "__reset__"


def _is_platform_staff(user):
    return user.is_authenticated and user.is_staff and user.is_superuser


def _group_keys(group):
    return [f.key for section in registry.group_sections(group) for f in section.fields]


def _preview_url(request, path):
    host = getattr(settings, "RASTISI_PLATFORM_PRIMARY_HOST", "") or request.get_host()
    return build_cross_host_url(request, hostname=host, path=path)


def _short(text, limit=120):
    text = (text or "").replace("\n", " ")
    return text if len(text) <= limit else text[:limit] + "…"


@user_passes_test(_is_platform_staff, login_url=LOGIN)
def public_site_home(request):
    overrides = {row.key: row.value for row in PublicSiteSetting.objects.all()}
    forced = getattr(settings, "PUBLIC_SITE_FORCE_DESIGN", "")
    rows = []
    for group in registry.GROUPS:
        keys = set(_group_keys(group))
        rows.append({
            "group": group,
            "changed": sum(1 for k in overrides if k in keys),
            "fields": len(keys),
        })
    return render(request, "portal/platform_admin/public_site.html", {
        "rows": rows,
        "design": services.active_design(),
        "forced": forced if forced in (registry.DESIGN_V2, registry.DESIGN_LEGACY) else "",
        "stored_design": overrides.get(registry.SWITCH_KEY, ""),
        "total_changed": sum(1 for k in overrides if k in registry.FIELDS),
        "preview_home": _preview_url(request, "/"),
        "active_nav": "public-site",
    })


@require_POST
@user_passes_test(_is_platform_staff, login_url=LOGIN)
def public_site_switch(request):
    choice = request.POST.get("design")
    if choice not in (registry.DESIGN_V2, registry.DESIGN_LEGACY):
        raise Http404("Unknown design")
    previous = PublicSiteSetting.objects.filter(pk=registry.SWITCH_KEY).values_list("value", flat=True).first() or ""
    PublicSiteSetting.objects.update_or_create(
        key=registry.SWITCH_KEY, defaults={"value": choice, "updated_by": request.user},
    )
    record_platform_audit_event(
        actor=request.user, action_code="platform_admin.public_site_design_switched",
        object_type="PublicSiteSetting", object_id=registry.SWITCH_KEY, object_label="طراحی سایت عمومی",
        before={"design": previous or "default"}, after={"design": choice},
    )
    if choice == registry.DESIGN_LEGACY:
        messages.success(request, "سایت عمومی به طراحی قبلی برگشت. هر زمان بخواهید می‌توانید دوباره طراحی جدید را فعال کنید؛ متن‌ها و رنگ‌های ویرایش‌شده حفظ می‌شوند.")
    else:
        messages.success(request, "طراحی جدید سایت عمومی فعال شد.")
    return redirect("portal_platform_admin:public-site")


def _field_rows(group, overrides, posted=None, errors=None):
    """Template-friendly sections with the value to show in each input."""
    sections = []
    for section in registry.group_sections(group):
        fields = []
        for f in section.fields:
            override = overrides.get(f.key)
            if posted is not None:
                if f.kind == registry.KIND_BOOL:
                    shown = "1" if posted.get(f.key) else "0"
                else:
                    shown = posted.get(f.key, "")
            elif override not in (None, ""):
                shown = override
            else:
                shown = f.default
            fields.append({
                "key": f.key, "label": f.label, "kind": f.kind, "help": f.help,
                "value": shown, "default": f.default,
                "checked": shown == "1" or (f.kind == registry.KIND_BOOL and shown == "" and f.default == "1"),
                "overridden": override not in (None, ""),
                "error": (errors or {}).get(f.key, ""),
                "choices": [(v, label, v == shown) for v, label in f.choices],
                "multiline": f.kind == registry.KIND_TEXTAREA,
                "short_default": _short(f.default, 90),
            })
        sections.append({"title": section.title, "note": section.note, "fields": fields})
    return sections


@user_passes_test(_is_platform_staff, login_url=LOGIN)
def public_site_edit(request, slug):
    group = _GROUPS.get(slug)
    if group is None:
        raise Http404("Unknown group")
    overrides = {row.key: row.value for row in PublicSiteSetting.objects.filter(key__in=_group_keys(group))}
    errors, posted = {}, None

    if request.method == "POST":
        posted = request.POST
        changes, to_store, to_delete = [], {}, []
        for section in registry.group_sections(group):
            for f in section.fields:
                if posted.get(_RESET_PREFIX + f.key):
                    if f.key in overrides:
                        to_delete.append(f.key)
                        changes.append((f.key, overrides[f.key], "پیش‌فرض"))
                    continue
                stored, error = services.validate(f, posted.get(f.key, ""))
                if error:
                    errors[f.key] = error
                    continue
                before = overrides.get(f.key)
                if stored is None:
                    if before is not None:
                        to_delete.append(f.key)
                        changes.append((f.key, before, "پیش‌فرض"))
                elif stored != before:
                    to_store[f.key] = stored
                    changes.append((f.key, before or f.default, stored))
        if errors:
            messages.error(request, "چند مقدار نامعتبر است؛ خطاها را اصلاح کنید. هیچ تغییری ذخیره نشد.")
        else:
            with transaction.atomic():
                for key, val in to_store.items():
                    PublicSiteSetting.objects.update_or_create(key=key, defaults={"value": val, "updated_by": request.user})
                if to_delete:
                    PublicSiteSetting.objects.filter(key__in=to_delete).delete()
            if changes:
                record_platform_audit_event(
                    actor=request.user, action_code="platform_admin.public_site_saved",
                    object_type="PublicSiteSetting", object_id=group.slug, object_label=group.title,
                    before={k: _short(b) for k, b, _a in changes[:30]},
                    after={k: _short(a) for k, _b, a in changes[:30]},
                    metadata={"changed_count": len(changes)},
                )
                messages.success(request, f"{len(changes)} تغییر ذخیره شد و در سایت عمومی اعمال شد.")
            else:
                messages.success(request, "تغییری برای ذخیره نبود.")
            return redirect("portal_platform_admin:public-site-edit", slug=group.slug)

    return render(request, "portal/platform_admin/public_site_edit.html", {
        "group": group,
        "sections": _field_rows(group, overrides, posted=posted, errors=errors),
        "preview_url": _preview_url(request, group.preview),
        "changed": len(overrides),
        "is_design": group.slug == "design",
        "active_nav": "public-site",
    })


@require_POST
@user_passes_test(_is_platform_staff, login_url=LOGIN)
def public_site_reset(request, slug):
    group = _GROUPS.get(slug)
    if group is None:
        raise Http404("Unknown group")
    rows = PublicSiteSetting.objects.filter(key__in=_group_keys(group))
    count = rows.count()
    if count:
        record_platform_audit_event(
            actor=request.user, action_code="platform_admin.public_site_reset",
            object_type="PublicSiteSetting", object_id=group.slug, object_label=group.title,
            before={"changed_fields": count}, after={"changed_fields": 0},
        )
        rows.delete()
        messages.success(request, f"همه تغییرات «{group.title}» حذف شد و پیش‌فرض برگشت.")
    else:
        messages.success(request, "این بخش تغییری نداشت.")
    return redirect("portal_platform_admin:public-site-edit", slug=group.slug)
