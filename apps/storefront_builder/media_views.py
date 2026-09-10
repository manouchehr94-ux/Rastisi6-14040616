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


def _media_config(kind: str, section) -> dict:
    config = _MEDIA_KINDS.get(kind)
    if config is None:
        raise Http404
    if section.section_key not in config["section_keys"]:
        raise Http404
    return config


def _media_list_body(request, section, kind, config):
    """پارشیالِ فهرستِ آیتم‌ها — یک بار نوشته شده، هم توسطِ صفحه‌ی کامل و هم
    توسطِ هر endpointِ htmx (toggle/delete/reorder/move) برایِ reswap
    استفاده می‌شود؛ دقیقاً همان الگویِ ``storefront_section_list_partial``
    برایِ خودِ section."""
    items = config["model"].objects.filter(section=section).order_by("display_order", "id")
    return render(request, "dashboard/storefront_builder/partials/section_media_list_body.html", {
        "section": section, "items": items, "kind": kind, "config": config,
    })


@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_section_media_list(request, pk, kind):
    section = _get_scoped_section(request, pk)
    config = _media_config(kind, section)
    items = config["model"].objects.filter(section=section).order_by("display_order", "id")
    return render(request, "dashboard/storefront_builder/section_media_list.html", {
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
    همان asset ارجاع بدهد؛ نگاه کنید به ``MediaAsset.is_referenced``)."""
    asset_fields = config.get("asset_fields")
    if not asset_fields:
        return
    from apps.content.models import MediaAsset

    update_fields = []
    for file_field, asset_field in asset_fields.items():
        if file_field not in changed_fields:
            continue
        file_obj = getattr(obj, file_field)
        if file_obj:
            asset = MediaAsset.objects.create(store=store, image=file_obj.name)
            setattr(obj, f"{asset_field}_id", asset.pk)
        else:
            setattr(obj, f"{asset_field}_id", None)
        update_fields.append(asset_field)
    if update_fields:
        obj.save(update_fields=update_fields)


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
            changed = set()
            files_to_delete = []
            for f in file_fields:
                name = f["name"]
                new_name = getattr(obj, name).name if getattr(obj, name) else None
                if old_names[name] != new_name:
                    changed.add(name)
                    if old_names[name]:
                        files_to_delete.append(old_names[name])
            if files_to_delete:
                transaction.on_commit(lambda names=files_to_delete: [storage.delete(f) for f in names if storage.exists(f)])
            if changed:
                _sync_asset_references(obj, config, store, changed_fields=changed)
            messages.success(request, f"«{config['label']}» ذخیره شد")
            return redirect("dashboard:storefront-builder-section-media-list", pk=section.pk, kind=kind)
        except (ValidationError, IntegrityError) as exc:
            error_message = str(exc.message_dict if hasattr(exc, "message_dict") else exc)
            messages.error(request, error_message)
            item = obj

    from apps.catalog.models import Brand, Category, MerchantCollection

    categories = Category.objects.filter(store=store, is_active=True).order_by("order", "name")
    brands = Brand.objects.filter(store=store, is_active=True).order_by("name")
    collections = MerchantCollection.objects.filter(store=store, is_active=True).order_by("name")
    return render(request, "dashboard/storefront_builder/partials/section_media_form.html", {
        "section": section, "item": item, "kind": kind, "config": config,
        "categories": categories, "brands": brands, "collections": collections,
    })


@require_POST
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_section_media_delete(request, pk, kind, item_pk):
    """حذفِ یک Placement.

    Phase 0.5 — تصمیمِ مالک ۸ (حذفِ امن): این Placement حذف می‌شود، اما
    ``MediaAsset``هایی که ارجاع می‌دهد **مستقیماً** حذف نمی‌شوند — به‌جایِ
    آن، ``delete_media_asset_if_unreferenced`` صدا زده می‌شود که فقط اگر
    هیچ Placementِ دیگری (مثلاً همینِ اسلاید در نسخه‌ی Published) به همان
    asset ارجاع ندهد، آن را (و فایلِ فیزیکی‌اش را) حذف می‌کند.

    برایِ ردیف‌هایِ قدیمی‌تر (بدونِ asset FK — از قبل از Phase 0.5) دقیقاً
    همان رفتارِ قبلی حفظ شده: پاک‌سازیِ مستقیمِ فایلِ فیزیکی بر اساسِ نامِ
    فیلدِ تصویرِ قدیمی."""
    from apps.content.services import delete_media_asset_if_unreferenced

    section = _get_scoped_section(request, pk)
    config = _media_config(kind, section)
    item = get_object_or_404(config["model"], pk=item_pk, section=section)
    # Phase 4 (Task 6) — every kind's file field now has a matching
    # ``asset_fields`` entry (unified with create/edit above), so no
    # per-kind fallback is needed here any more.
    asset_field_map = config["asset_fields"]

    # جفتِ (asset موجود، نامِ فایلِ legacy) — فقط برایِ فیلدهایی که asset
    # FK ندارند (ردیفِ قدیمی‌تر) نامِ فایل ذخیره می‌شود؛ برایِ بقیه، حذفِ
    # فایلِ فیزیکی کاملاً به عهده‌ی ``delete_media_asset_if_unreferenced``
    # است (که خودش reference-safety را چک می‌کند).
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

    if legacy_cleanup_names and storage is not None:
        def _cleanup():
            for name in legacy_cleanup_names:
                if storage.exists(name):
                    storage.delete(name)

        transaction.on_commit(_cleanup)

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
