"""ویوهای مدیریتِ رسانه‌یِ مخصوصِ یک section — اسلایدهایِ اسلایدرِ اصلی
(``HeroSlide``) و بنرها (``PromotionalBanner``)، هر دو از داخلِ سازنده
بصری، مقیّد به یک نمونه‌یِ مشخص از section (نه فهرستِ سراسریِ فروشگاه).

این ماژول عمداً از ``views.py`` جدا نگه داشته شده — منطقِ CRUD رسانه با
منطقِ CRUD خودِ section کاملاً متفاوت است (آپلودِ فایل، دو مدلِ مختلف)،
اما هر دو مدل (``HeroSlide``/``PromotionalBanner``) از نظرِ شکلِ فرم آنقدر
شبیه‌هم‌اند که یک پیاده‌سازیِ عمومیِ واحد (پارامتری‌شده با ``kind``) به‌جایِ
دو کپیِ تقریباً یکسان انتخاب شده — دقیقاً همان اصلِ «بدون معماریِ یک‌بارمصرفِ
جداگانه برایِ هر section جدید» که مستندسازیِ ``section_registry.py`` تأکید
می‌کند.

قوانینِ حیاتی که این ماژول باید حفظ کند:
- هر عملیات با ``_get_scoped_section`` شروع می‌شود (همان تابعِ ``views.py``) —
  یعنی مقیّد به Store + نسخه‌یِ Draft، دقیقاً همان محافظتِ دوگانه‌یِ مستأجر
  که بقیه‌یِ endpointهایِ section دارند.
- آپلود/حذفِ فایل دقیقاً همان الگویِ امنِ ``apps.dashboard.views.hero_form``
  (پاک‌سازیِ فایلِ قدیمی فقط پس از commit موفق) را تکرار می‌کند — نه
  ساده‌سازیِ آن.
"""

from __future__ import annotations

from django.contrib import messages
from django.db import IntegrityError, transaction
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.content.models import HeroSlide, PromotionalBanner, StoryRailItem
from apps.dashboard.decorators import permission_required, staff_required
from apps.stores.authorization import STOREFRONT_LAYOUT_MANAGE

from .views import _get_scoped_section, _resolve_store

#: پیکربندیِ عمومیِ هر دو نوعِ رسانه — کلیدِ URL (``kind``) → مدل + برچسبِ
#: فارسی + نامِ فیلدِ متنِ دومِ اختصاصی (``subtitle`` برایِ اسلاید،
#: ``description`` برایِ بنر) + مسیرِ section_key هایی که این رسانه را
#: مصرف می‌کنند (فقط برایِ اعتبارسنجیِ ورودیِ URL، نه چیزِ دیگر).
#: Phase 4 (Task 6) — ``file_fields`` (ordered) is what makes
#: ``storefront_section_media_form`` genuinely model-agnostic: each kind
#: declares its own real image field(s) here (a desktop/mobile pair for
#: ``HeroSlide``/``PromotionalBanner``, one single field for
#: ``StoryRailItem``) instead of the form hardcoding
#: ``desktop_image``/``mobile_image``. ``asset_fields`` (file field → asset
#: FK) is now the single mapping shared by create/edit AND delete — every
#: kind's file field has a matching entry, so
#: ``_sync_asset_references``/``storefront_section_media_delete`` need no
#: per-kind branching either.
_MEDIA_KINDS = {
    "hero-slides": {
        "model": HeroSlide,
        "label": "اسلاید",
        "label_plural": "اسلایدها",
        "text_field": "subtitle",
        "text_label": "زیرعنوان",
        "section_keys": {"hero_banner", "image_slider"},
        # Phase 0.5 — تصمیمِ مالک ۵: نگاشتِ فیلدِ فایلِ قدیمی → فیلدِ FKِ
        # asset متناظر، برایِ اینکه ``storefront_section_media_form`` بتواند
        # ردیفِ MediaAsset را ایجاد/به‌روزرسانی کند — بدونِ کپیِ بایتِ فایل،
        # فقط با اشاره‌گر به همان فایلِ تازه‌آپلودشده.
        "asset_fields": {"desktop_image": "desktop_asset", "mobile_image": "mobile_asset"},
        "file_fields": (
            {"name": "desktop_image", "label": "تصویر دسکتاپ", "required": True},
            {"name": "mobile_image", "label": "تصویر موبایل (اختیاری)", "required": False,
             "remove_field": "remove_mobile", "remove_label": "حذف تصویر موبایلِ فعلی"},
        ),
        # Phase 4 (Task 6) — the model attribute the media LIST partial shows
        # as a thumbnail (never a raw file field — both models resolve
        # MediaAsset->legacy-file precedence through this property).
        "thumb_field": "desktop_image_url",
    },
    "banners": {
        "model": PromotionalBanner,
        "label": "بنر",
        "label_plural": "بنرها",
        "text_field": "description",
        "text_label": "توضیحات",
        "section_keys": {"single_banner", "multi_banner"},
        "asset_fields": {"desktop_image": "desktop_asset", "mobile_image": "mobile_asset"},
        "file_fields": (
            {"name": "desktop_image", "label": "تصویر دسکتاپ", "required": True},
            {"name": "mobile_image", "label": "تصویر موبایل (اختیاری)", "required": False,
             "remove_field": "remove_mobile", "remove_label": "حذف تصویر موبایلِ فعلی"},
        ),
        "thumb_field": "desktop_image_url",
    },
    "story-items": {
        "model": StoryRailItem,
        "label": "آیتم استوری",
        "label_plural": "آیتم‌های استوری",
        "text_field": "title",
        "text_label": "عنوان",
        "section_keys": {"story_rail"},
        # Phase 4 (Task 6) — ``StoryRailItem`` has exactly one image field
        # (``image``), unlike the desktop/mobile pair above; the shared form
        # now reads that shape from ``file_fields`` instead of assuming the
        # pair exists.
        "asset_fields": {"image": "image_asset"},
        "file_fields": (
            {"name": "image", "label": "تصویر", "required": True},
        ),
        # ``StoryRailItem`` has no ``desktop_image_url``; its own resolved
        # thumbnail property is ``image_url`` (``apps.content.models.StoryRailItem``).
        "thumb_field": "image_url",
    },
}


def media_kind_for_section_key(section_key: str) -> str | None:
    """R4 Task 7 (Batch 3) — the reverse lookup R4's Inspector needs: given
    a section_key, which (if any) ``_MEDIA_KINDS`` entry owns its media.
    Public (unlike ``_media_config``, which additionally needs a real
    Section instance to validate against) because the R4 editor only has
    the section_key at Inspector-render time, before it knows whether this
    is a schema-enabled section, a media-only one, or neither."""
    for kind, config in _MEDIA_KINDS.items():
        if section_key in config["section_keys"]:
            return kind
    return None


def media_label_for_kind(kind: str) -> str:
    """R4 Task 7 (final-review fix, MINOR-6) — the same public-accessor
    reasoning as ``media_kind_for_section_key`` above: R4's Inspector needs
    this kind's plural Persian label without reaching into ``_MEDIA_KINDS``
    directly from another module."""
    return _MEDIA_KINDS[kind]["label_plural"]


def media_config_for_kind(kind: str) -> dict:
    """Phase 5 Task 4 (remediation R1a) — the same public-accessor reasoning as
    the two accessors above: the R4 Inspector needs this kind's config (model +
    labels + thumb field) to render the canonical media list body inline,
    without importing the private ``_MEDIA_KINDS`` mapping. The caller has
    already resolved ``kind`` from the section's own key via
    ``media_kind_for_section_key`` (so section↔kind ownership is guaranteed);
    unlike ``_media_config`` this needs no section instance. The media list/
    CRUD endpoints still re-scope every request through ``_get_scoped_section``
    — this accessor never bypasses that authority."""
    return _MEDIA_KINDS[kind]


def _media_config(kind: str, section) -> dict:
    config = _MEDIA_KINDS.get(kind)
    if config is None:
        raise Http404
    if section.section_key not in config["section_keys"]:
        raise Http404
    return config


#: Phase 5 Task 4 (final review fix) — the EXPLICIT R4-inline context marker.
#: R4-inline context must NOT be inferred from ``HX-Request`` alone: the LEGACY
#: full-page media screen also drives toggle/delete/move/reorder over htmx and
#: reswaps through ``_media_list_body`` — those responses must stay legacy
#: context (never gain the R4-only ``hx-target="closest [data-r4-media-manager]"``
#: on the Edit link, which has no ancestor to match on the legacy page). The R4
#: embed sends this header on every htmx request it originates (inherited via
#: the manager container's ``hx-headers``, and passed explicitly on the
#: drag-reorder ``htmx.ajax`` call); the legacy page never sends it. Same
#: canonical endpoints own everything — this is only a context flag.
_R4_INLINE_HEADER = "HX-R4-Inline"


def _is_r4_inline(request) -> bool:
    """True only when the request explicitly declares R4-inline context via the
    ``HX-R4-Inline`` header — never merely because it is an HX request."""
    return request.headers.get(_R4_INLINE_HEADER) == "1"


def _media_list_body(request, section, kind, config):
    """پارشیالِ فهرستِ آیتم‌ها — یک بار نوشته شده، هم توسطِ صفحه‌ی کامل و هم
    توسطِ هر endpointِ htmx (toggle/delete/reorder/move) برایِ reswap
    استفاده می‌شود؛ دقیقاً همان الگویِ ``storefront_section_list_partial``
    برایِ خودِ section.

    Phase 5 Task 4 (final review fix): ``inline_media`` is driven by the
    EXPLICIT R4-inline marker (``_is_r4_inline``), NOT by HX-Request — because
    the legacy full-page media screen reswaps through here over htmx too and
    must remain legacy context. This flag only toggles whether the list body's
    per-row "edit" link loads inline (into the R4 manager) or navigates the
    full page; the rows/CRUD endpoints themselves are identical either way."""
    items = config["model"].objects.filter(section=section).order_by("display_order", "id")
    return render(request, "dashboard/storefront_builder/partials/section_media_list_body.html", {
        "section": section, "items": items, "kind": kind, "config": config,
        "inline_media": _is_r4_inline(request),
    })


@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_section_media_list(request, pk, kind):
    section = _get_scoped_section(request, pk)
    config = _media_config(kind, section)
    items = config["model"].objects.filter(section=section).order_by("display_order", "id")
    # Phase 5 Task 4 (remediation R1a + final review fix) — R4-native media
    # editing. Only an EXPLICIT R4-inline request (``_is_r4_inline``) returns
    # the body-only media manager (add control + list) that the R4 Inspector
    # embeds/refreshes INLINE; a legacy full-page GET (with or without htmx)
    # still returns the unchanged full legacy page. R4-inline context is never
    # inferred from HX-Request alone. Same canonical view, no second media CRUD
    # path.
    template_name = (
        "dashboard/storefront_builder/partials/section_media_manager_body.html"
        if _is_r4_inline(request)
        else "dashboard/storefront_builder/section_media_list.html"
    )
    return render(request, template_name, {
        "section": section, "items": items, "kind": kind, "config": config,
    })


def _apply_destination_fields(obj, request):
    obj.destination_type = request.POST.get("destination_type", "none")
    obj.destination_external_url = request.POST.get("destination_external_url", "").strip()
    obj.open_in_new_tab = request.POST.get("open_in_new_tab") == "on"
    cat_id = request.POST.get("destination_category") or None
    prod_id = request.POST.get("destination_product") or None
    brand_id = request.POST.get("destination_brand") or None
    collection_id = request.POST.get("destination_collection") or None
    obj.destination_category_id = int(cat_id) if cat_id else None
    obj.destination_product_id = int(prod_id) if prod_id else None
    obj.destination_brand_id = int(brand_id) if brand_id else None
    obj.destination_collection_id = int(collection_id) if collection_id else None


def _sync_asset_references(obj, config, store, *, changed_fields: set[str]) -> None:
    """Phase 0.5 — تصمیمِ مالک ۵: پس از ذخیره‌ی موفقِ ``obj`` (که فیلدِ
    فایلِ قدیمی‌اش از قبل ذخیره شده)، برایِ هر جفتِ (فیلدِ فایلِ قدیمی →
    فیلدِ FKِ asset) که واقعاً تغییر کرده، یک ``MediaAsset`` جدید ایجاد
    می‌کند که به همان فایلِ تازه‌ذخیره‌شده اشاره می‌کند — **بدونِ کپیِ
    بایتِ فایل** (فقط ``image=obj.<file_field>.name``، همان مسیرِ ذخیره‌شده).

    اگر فیلدِ فایل حذف شده باشد (مثلاً ``remove_mobile``)، FKِ asset متناظر
    فقط به ``None`` تنظیم می‌شود — هرگز خودِ ردیفِ ``MediaAsset`` را حذف
    نمی‌کند (ممکن است Placementِ دیگری، مثلاً نسخه‌ی Published، هنوز به
    همان asset ارجاع بدهد؛ نگاه کنید به ``MediaAsset.is_referenced``).

    MED-001: قبلِ ساختنِ FKِ asset تازه، اگر فیلدِ فایلِ قدیمیِ همینِ
    ``obj`` (پیش از تغییر) خودش قبلاً به یک ``MediaAsset`` وصل بود، آن
    asset را برمی‌گرداند — فراخوانِ (تنها همینجا، در ``storefront_section_
    media_form``) مسئولِ فراخوانیِ ``delete_media_asset_if_unreferenced``
    رویِ آن است تا اگر دیگر جایی به آن ارجاع ندهد، هم ردیفِ متادیتا و هم
    (فقط اگر مسیرِ فیزیکی هنوز از طریقِ هیچ alias/ImageFieldِ قدیمیِ
    دیگری ادعا نشود) بایتِ فیزیکی‌اش حذف شود."""
    asset_fields = config.get("asset_fields")
    if not asset_fields:
        return {}
    from apps.content.models import MediaAsset

    old_assets = {}
    update_fields = []
    for file_field, asset_field in asset_fields.items():
        if file_field not in changed_fields:
            continue
        old_asset_id = getattr(obj, f"{asset_field}_id", None)
        old_assets[asset_field] = MediaAsset.objects.filter(pk=old_asset_id).first() if old_asset_id else None
        file_obj = getattr(obj, file_field)
        if file_obj:
            asset = MediaAsset.objects.create(store=store, image=file_obj.name)
            setattr(obj, f"{asset_field}_id", asset.pk)
        else:
            setattr(obj, f"{asset_field}_id", None)
        update_fields.append(asset_field)
    if update_fields:
        obj.save(update_fields=update_fields)
    return old_assets


@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_section_media_form(request, pk, kind, item_pk=None):
    section = _get_scoped_section(request, pk)
    config = _media_config(kind, section)
    model = config["model"]
    store = _resolve_store(request)
    item = get_object_or_404(model, pk=item_pk, section=section) if item_pk else None

    file_fields = config["file_fields"]

    if request.method == "POST":
        obj = item or model(store=store, section=section)
        old_names = {
            f["name"]: (getattr(obj, f["name"]).name if obj.pk and getattr(obj, f["name"]) else None)
            for f in file_fields
        }

        obj.title = request.POST.get("title", "").strip()
        setattr(obj, config["text_field"], request.POST.get(config["text_field"], "").strip())
        obj.button_label = request.POST.get("button_label", "").strip()
        obj.show_button = request.POST.get("show_button") == "on"
        obj.is_active = request.POST.get("is_active", "on") == "on"
        if not item:
            last = model.objects.filter(section=section).order_by("-display_order").first()
            obj.display_order = (last.display_order + 1) if last else 0
        _apply_destination_fields(obj, request)

        for f in file_fields:
            name = f["name"]
            if name in request.FILES:
                setattr(obj, name, request.FILES[name])
            remove_field = f.get("remove_field")
            if remove_field and request.POST.get(remove_field) == "on" and name not in request.FILES:
                setattr(obj, name, "")

        try:
            obj.full_clean()
            obj.save()
            storage = getattr(model, file_fields[0]["name"]).field.storage
            # Phase 0.5 — تصمیمِ مالک ۵: فقط برایِ فیلدهایی که واقعاً تغییر
            # کردند (نه هر بار ذخیره)، یک ردیفِ MediaAsset تازه بساز و FKِ
            # asset را به آن وصل کن. اگر چیزی تغییر نکرده (مثلاً فقط عنوان
            # ویرایش شده)، asset FKِ قبلی (اگر باشد) دست‌نخورده می‌ماند.
            #
            # MED-001 (Retention-First، تصمیمِ معمار): این‌جا هرگز مستقیماً
            # ``storage.delete(old_name)`` صدا زده نمی‌شود، و مسیرهایِ زیر
            # هم دیگر هیچ حذفِ فیزیکی/متادیتایی انجام نمی‌دهند. نامِ فایلِ
            # قدیمیِ هر فیلدِ واقعاً تغییریافته جمع‌آوری می‌شود؛ اگر آن فیلد
            # پیش از تغییر یک FKِ ``MediaAsset`` داشت (``old_assets``ی که
            # ``_sync_asset_references`` برمی‌گرداند)، فراخوانِ
            # ``delete_media_asset_if_unreferenced`` انجام می‌شود — که اکنون
            # صرفاً یک no-opِ نگه‌دارنده است (نه ردیف حذف می‌شود، نه فایل)؛
            # در غیرِ این‌صورت (ردیفِ قدیمی‌تر بدونِ asset FK) نامِ فایل
            # مستقیماً به همان مرجعِ کانونیک (``cleanup_reusable_media_file``)
            # سپرده می‌شود که خودش هم اکنون یک no-opِ نگه‌دارنده است. asset
            # قدیمی/فایلِ قدیمی عمداً orphan باقی می‌ماند — این نشتِ کوچکِ
            # storage/metadata هزینه‌ی پذیرفته‌شده‌یِ حذفِ کاملِ مسابقه‌یِ
            # TOCTOUِ attach-vs-delete در همینِ P0 است (نگاه کنید به
            # یادداشتِ Retention-First در ``apps.content.services``).
            from apps.content.services import (
                cleanup_reusable_media_file,
                delete_media_asset_if_unreferenced,
            )

            changed = set()
            legacy_files_to_cleanup = []
            for f in file_fields:
                name = f["name"]
                new_name = getattr(obj, name).name if getattr(obj, name) else None
                if old_names[name] != new_name:
                    changed.add(name)
            old_assets = _sync_asset_references(obj, config, store, changed_fields=changed) if changed else {}
            for f in file_fields:
                name = f["name"]
                if name not in changed or not old_names[name]:
                    continue
                asset_field = (config.get("asset_fields") or {}).get(name)
                old_asset = old_assets.get(asset_field) if asset_field else None
                if old_asset is not None:
                    delete_media_asset_if_unreferenced(old_asset)
                else:
                    legacy_files_to_cleanup.append(old_names[name])
            for legacy_name in legacy_files_to_cleanup:
                cleanup_reusable_media_file(legacy_name, storage)
            messages.success(request, f"«{config['label']}» ذخیره شد")
            # Phase 5 Task 4 (final review fix) — when the save came from the R4
            # inline manager (explicit marker), return the refreshed manager
            # body so the merchant stays inside R4; a redirect would be
            # re-followed by htmx WITHOUT the R4-inline header and would render
            # the legacy full page. The legacy full-page flow still redirects
            # exactly as before. Same canonical list body either way.
            if _is_r4_inline(request):
                items = model.objects.filter(section=section).order_by("display_order", "id")
                return render(
                    request,
                    "dashboard/storefront_builder/partials/section_media_manager_body.html",
                    {"section": section, "items": items, "kind": kind, "config": config},
                )
            return redirect("dashboard:storefront-builder-section-media-list", pk=section.pk, kind=kind)
        except (ValidationError, IntegrityError) as exc:
            error_message = str(exc.message_dict if hasattr(exc, "message_dict") else exc)
            messages.error(request, error_message)
            item = obj

    from apps.catalog.models import Brand, Category, MerchantCollection

    categories = Category.objects.filter(store=store, is_active=True).order_by("order", "name")
    brands = Brand.objects.filter(store=store, is_active=True).order_by("name")
    collections = MerchantCollection.objects.filter(store=store, is_active=True).order_by("name")
    # Phase 5 Task 4 (remediation R1a + final review fix) — body-only form
    # under HX-Request so the add/edit form loads INLINE in the R4 Inspector;
    # unchanged full page otherwise. The htmx submit/cancel wiring back into the
    # inline manager is gated by the EXPLICIT R4-inline marker, never HX-Request
    # alone (a legacy full page never sends the marker, so it submits normally).
    # Same canonical view/persistence, no second form.
    is_hx = request.headers.get("HX-Request") == "true"
    is_r4_inline = _is_r4_inline(request)
    template_name = (
        "dashboard/storefront_builder/partials/section_media_form_body.html"
        if is_hx
        else "dashboard/storefront_builder/partials/section_media_form.html"
    )
    return render(request, template_name, {
        "section": section, "item": item, "kind": kind, "config": config,
        "categories": categories, "brands": brands, "collections": collections,
        "inline_media": is_r4_inline,
    })


@require_POST
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_section_media_delete(request, pk, kind, item_pk):
    """حذفِ یک Placement.

    Phase 0.5 — تصمیمِ مالک ۸ (حذفِ امن) + MED-001 (Retention-First،
    تصمیمِ معمار): این Placement حذف می‌شود، اما ``MediaAsset``هایی که
    ارجاع می‌دهد **هرگز** حذف نمی‌شوند — نه ردیفِ متادیتا، نه فایلِ
    فیزیکی — چه هنوز از جایِ دیگری ارجاع شوند چه نشوند. ``delete_media_
    asset_if_unreferenced`` صدا زده می‌شود که اکنون صرفاً یک no-opِ
    نگه‌دارنده است.

    برایِ ردیف‌هایِ قدیمی‌تر (بدونِ asset FK — از قبل از Phase 0.5) هم
    دقیقاً همینِ سیاست: نامِ فایلِ قدیمی به ``cleanup_reusable_media_file``
    سپرده می‌شود که آن هم اکنون صرفاً یک no-opِ نگه‌دارنده است — هرگز
    ``storage.delete`` مستقیم."""
    from apps.content.services import cleanup_reusable_media_file, delete_media_asset_if_unreferenced

    section = _get_scoped_section(request, pk)
    config = _media_config(kind, section)
    item = get_object_or_404(config["model"], pk=item_pk, section=section)
    # Phase 4 (Task 6) — every kind's file field now has a matching
    # ``asset_fields`` entry (unified with create/edit above), so no
    # per-kind fallback is needed here any more.
    asset_field_map = config["asset_fields"]

    # جفتِ (asset موجود، نامِ فایلِ legacy) — فقط برایِ فیلدهایی که asset
    # FK ندارند (ردیفِ قدیمی‌تر) نامِ فایل ذخیره می‌شود؛ برایِ بقیه، مسیرِ
    # کانونیکِ ``delete_media_asset_if_unreferenced`` صدا زده می‌شود. هر دو
    # مسیر اکنون Retention-Firstاند (MED-001، تصمیمِ معمار): هرگز
    # ``storage.delete`` مستقیم، هرگز حذفِ ردیفِ ``MediaAsset``.
    legacy_cleanup_names = []
    assets_to_check = []
    for file_field, asset_field in asset_field_map.items():
        asset = getattr(item, asset_field, None)
        if asset is not None:
            assets_to_check.append(asset)
        else:
            file_obj = getattr(item, file_field, None)
            if file_obj:
                legacy_cleanup_names.append(file_obj.name)
    storage_field = getattr(item, config["file_fields"][0]["name"], None)
    storage = storage_field.storage if storage_field is not None else None

    item.delete()

    for asset in assets_to_check:
        delete_media_asset_if_unreferenced(asset)

    if storage is not None:
        for legacy_name in legacy_cleanup_names:
            cleanup_reusable_media_file(legacy_name, storage)

    messages.success(request, f"«{config['label']}» حذف شد")
    return _media_list_body(request, section, kind, config)


@require_POST
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_section_media_toggle(request, pk, kind, item_pk):
    section = _get_scoped_section(request, pk)
    config = _media_config(kind, section)
    item = get_object_or_404(config["model"], pk=item_pk, section=section)
    item.is_active = not item.is_active
    item.save(update_fields=["is_active", "updated_at"])
    return _media_list_body(request, section, kind, config)


@require_POST
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_section_media_move(request, pk, kind, item_pk):
    """جابه‌جاییِ یک آیتم به بالا/پایین — fallback برایِ موبایل/کیبورد،
    دقیقاً همان الگویِ ``storefront_section_move`` برایِ خودِ section."""
    section = _get_scoped_section(request, pk)
    config = _media_config(kind, section)
    model = config["model"]
    direction = request.POST.get("direction")
    item = get_object_or_404(model, pk=item_pk, section=section)
    siblings = list(model.objects.filter(section=section).order_by("display_order", "id"))
    index = next((i for i, s in enumerate(siblings) if s.pk == item.pk), None)
    if index is not None:
        swap_index = index - 1 if direction == "up" else index + 1
        if 0 <= swap_index < len(siblings):
            other = siblings[swap_index]
            item.display_order, other.display_order = other.display_order, item.display_order
            model.objects.bulk_update([item, other], ["display_order"])
    return _media_list_body(request, section, kind, config)


@require_POST
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_section_media_reorder(request, pk, kind):
    section = _get_scoped_section(request, pk)
    config = _media_config(kind, section)
    model = config["model"]
    item_ids = request.POST.getlist("item_ids")

    valid_ids = set(model.objects.filter(section=section).values_list("pk", flat=True))
    ordered_ids = [int(i) for i in item_ids if i.isdigit() and int(i) in valid_ids]

    if len(set(ordered_ids)) != len(ordered_ids):
        messages.error(request, "فهرست مرتب‌سازی شامل شناسه‌ی تکراری است — ترتیب تغییر نکرد")
        return _media_list_body(request, section, kind, config)

    with transaction.atomic():
        for index, item_id in enumerate(ordered_ids):
            model.objects.filter(pk=item_id, section=section).update(display_order=index)

    return _media_list_body(request, section, kind, config)
