"""Host-isolated public marketing photo administration (not Store media)."""

from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import redirect, render
from django.templatetags.static import static
from django.views.decorators.http import require_POST

from .forms_public_photos import PublicSitePhotoForm
from .models import PublicSitePhoto
from .services.platform_config_service import record_platform_audit_event


def _is_platform_staff(user):
    return user.is_authenticated and user.is_staff and user.is_superuser


def _slot_labels():
    return dict(PublicSitePhoto.SLOT_CHOICES)


@user_passes_test(_is_platform_staff, login_url="portal_platform_admin:login")
def public_photos(request):
    overrides = {photo.slot: photo for photo in PublicSitePhoto.objects.all()}
    rows = []
    for slot, label in PublicSitePhoto.SLOT_CHOICES:
        photo = overrides.get(slot)
        rows.append({
            "slot": slot,
            "label": label,
            "photo": photo,
            "preview_url": photo.image.url if photo and photo.image
                else static(f"portal/images/public/{slot}.webp"),
        })
    return render(
        request, "portal/platform_admin/public_photos.html",
        {"rows": rows, "active_nav": "public-photos"},
    )


@user_passes_test(_is_platform_staff, login_url="portal_platform_admin:login")
def public_photo_edit(request, slot):
    labels = _slot_labels()
    if slot not in labels:
        from django.http import Http404
        raise Http404("Unknown public-site image slot")

    current = PublicSitePhoto.objects.filter(slot=slot).first()
    if request.method == "POST":
        form = PublicSitePhotoForm(request.POST, request.FILES, instance=current)
        if form.is_valid():
            photo = form.save(commit=False)
            photo.slot = slot
            photo.updated_by = request.user
            previous = current.image.name if current and current.image else ""
            photo.save()
            record_platform_audit_event(
                actor=request.user, action_code="platform_admin.public_photo_saved",
                object_type="PublicSitePhoto", object_id=slot,
                object_label=labels[slot],
                before={"image": previous},
                after={"image": photo.image.name, "alt_text": photo.alt_text},
            )
            messages.success(request, "تصویر سایت عمومی ذخیره شد.")
            return redirect("portal_platform_admin:public-photos")
    else:
        form = PublicSitePhotoForm(instance=current)

    return render(request, "portal/platform_admin/public_photo_form.html", {
        "form": form,
        "slot": slot,
        "label": labels[slot],
        "preview_url": current.image.url if current and current.image
            else static(f"portal/images/public/{slot}.webp"),
        "is_override": bool(current),
        "active_nav": "public-photos",
    })


@require_POST
@user_passes_test(_is_platform_staff, login_url="portal_platform_admin:login")
def public_photo_reset(request, slot):
    labels = _slot_labels()
    if slot not in labels:
        from django.http import Http404
        raise Http404("Unknown public-site image slot")
    current = PublicSitePhoto.objects.filter(slot=slot).first()
    if current is not None:
        previous = current.image.name if current.image else ""
        current.delete()
        record_platform_audit_event(
            actor=request.user, action_code="platform_admin.public_photo_reset",
            object_type="PublicSitePhoto", object_id=slot, object_label=labels[slot],
            before={"image": previous}, after={"image": "static fallback"},
        )
        messages.success(request, "تصویر پیش‌فرض سایت عمومی بازگردانده شد.")
    return redirect("portal_platform_admin:public-photos")
