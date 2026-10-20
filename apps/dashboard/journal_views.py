"""RS-02 — «مقالات مجله»: the merchant can see which articles lack a cover (or whose cover FILE is missing) and fix it in plain
language. Store-scoped (``BlogPost.store``); the legacy platform-wide posts (``store IS NULL``) are not editable from a store.
Replacing/removing a cover never deletes the old file from storage (media-deletion-safety contract)."""

from django import forms
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.http import require_POST

from apps.blog.models import BlogPost
from apps.content.models import validate_image_content, validate_image_size
from apps.stores.authorization import CONTENT_MANAGE

from .decorators import permission_required, staff_required


class JournalPostForm(forms.ModelForm):
    """فرمِ واحدِ ایجاد/ویرایشِ مقاله (عنوان، خلاصه، متنِ کامل، برچسب، اسلاگ، کاور). متن به‌صورتِ متنِ ساده ذخیره و در سایت با جداسازیِ پاراگراف
    نمایش داده می‌شود (همان قراردادِ صفحه‌هایِ محتوا؛ HTML خام پذیرفته/اجرا نمی‌شود). انتشار هرگز با ذخیره انجام نمی‌شود."""

    cover_image = forms.ImageField(required=False, validators=[validate_image_size, validate_image_content], label="تصویر کاور")
    remove_cover = forms.BooleanField(required=False, label="حذف تصویر کاور")
    slug = forms.CharField(required=False, max_length=240, label="نشانی مقاله (اسلاگ)")

    class Meta:
        model = BlogPost
        fields = ("title", "excerpt", "body", "category_label", "cover_image")

    def __init__(self, *args, store=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.store = store
        for field in self.fields.values():
            if not isinstance(field.widget, (forms.CheckboxInput, forms.ClearableFileInput, forms.FileInput)):
                field.widget.attrs.setdefault("class", "inp")
        self.fields["body"].widget.attrs.update({"rows": 14, "style": "min-height:240px"})
        self.fields["slug"].widget.attrs.update({"dir": "ltr", "placeholder": "خودکار از عنوان"})
        self.fields["title"].required = True
        self.fields["body"].required = True
        self.fields["body"].error_messages["required"] = "متن مقاله را بنویسید."
        self.fields["title"].error_messages["required"] = "عنوان مقاله لازم است."
        # اسلاگ فقط تا پیش از انتشار قابل تغییر است (تغییرِ آدرسِ مقالهٔ منتشرشده لینک‌ها را می‌شکند).
        self.slug_locked = bool(self.instance.pk and self.instance.published_at is not None)
        if self.instance.pk:
            self.initial.setdefault("slug", self.instance.slug)

    def clean_slug(self):
        if self.slug_locked:
            return self.instance.slug
        raw = (self.cleaned_data.get("slug") or "").strip()
        title = self.data.get("title", "")
        slug = slugify(raw or title, allow_unicode=True)[:240]
        if not slug:
            raise forms.ValidationError("برای ساختِ نشانیِ مقاله یک عنوان یا اسلاگِ معتبر لازم است.")
        clash = BlogPost.objects.filter(slug=slug)
        if self.instance.pk:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            if raw:
                raise forms.ValidationError("این نشانی قبلاً استفاده شده است؛ نشانیِ دیگری بنویسید.")
            base, n = slug[:230], 2
            while BlogPost.objects.filter(slug=f"{base}-{n}").exists():
                n += 1
            slug = f"{base}-{n}"
        return slug

    def clean_body(self):
        return (self.cleaned_data.get("body") or "").strip().replace("\r\n", "\n")

    def save(self, commit=True):
        post = super().save(commit=False)
        post.slug = self.cleaned_data["slug"]
        if self.store is not None and post.store_id is None:
            post.store = self.store
        uploaded = bool(self.files.get("cover_image"))  # cleaned_data would hand back the EXISTING file as "initial"
        if self.cleaned_data.get("remove_cover") and not uploaded:
            post.cover_image = None  # the stored file is NOT deleted from storage
        if commit:
            post.save()
        return post


def _cover_state(post) -> str:
    if not post.cover_image or not post.cover_image.name:
        return "none"
    return "ok" if post.has_available_cover else "missing"


def _publication_state(post) -> str:
    if post.published_at is None:
        return "draft"
    return "scheduled" if post.published_at > timezone.now() else "published"


@staff_required
@permission_required(CONTENT_MANAGE)
def journal_list(request):
    posts = list(BlogPost.objects.filter(store=request.store).order_by("-published_at", "-created_at"))
    for post in posts:
        post.cover_state = _cover_state(post)
        post.publication_state = _publication_state(post)
    return render(request, "dashboard/journal_list.html", {
        "posts": posts, "active_page": "journal",
        "without_cover": sum(1 for p in posts if p.cover_state != "ok"),
    })


def _after_save(request, post, publish_requested):
    """ذخیرهٔ ساده وضعیتِ انتشار را تغییر نمی‌دهد؛ فقط دکمهٔ صریحِ «ذخیره و انتشار» پیش‌نویس را منتشر می‌کند."""
    if publish_requested and post.published_at is None:
        post.published_at = timezone.now()
        post.save(update_fields=["published_at", "updated_at"])
        messages.success(request, f"«{post.title}» ذخیره و منتشر شد.")
    else:
        messages.success(request, "مقاله ذخیره شد." + (" (هنوز پیش‌نویس است؛ برای نمایش در سایت منتشرش کنید.)" if post.published_at is None else ""))


@staff_required
@permission_required(CONTENT_MANAGE)
def journal_create(request):
    if request.method == "POST":
        form = JournalPostForm(request.POST, request.FILES, store=request.store)
        if form.is_valid():
            post = form.save()  # published_at stays None: a new article is always a draft
            _after_save(request, post, request.POST.get("action") == "publish")
            return redirect("dashboard:journal-list")
    else:
        form = JournalPostForm(store=request.store)
    return render(request, "dashboard/journal_form.html", {"form": form, "post": None, "active_page": "journal"})


@staff_required
@permission_required(CONTENT_MANAGE)
def journal_edit(request, pk):
    post = get_object_or_404(BlogPost, pk=pk, store=request.store)
    if request.method == "POST":
        form = JournalPostForm(request.POST, request.FILES, instance=post, store=request.store)
        if form.is_valid():
            post = form.save()
            _after_save(request, post, request.POST.get("action") == "publish")
            return redirect("dashboard:journal-list")
    else:
        form = JournalPostForm(instance=post, store=request.store)
    post.cover_state = _cover_state(post)
    post.publication_state = _publication_state(post)
    return render(request, "dashboard/journal_form.html", {"form": form, "post": post, "active_page": "journal"})


@require_POST
@staff_required
@permission_required(CONTENT_MANAGE)
def journal_publish_toggle(request, pk):
    post = get_object_or_404(BlogPost, pk=pk, store=request.store)
    if _publication_state(post) == "draft":
        post.published_at = timezone.now()
        messages.success(request, f"«{post.title}» منتشر شد.")
    else:
        post.published_at = None
        messages.info(request, f"«{post.title}» به پیش‌نویس برگشت.")
    post.save(update_fields=["published_at", "updated_at"])
    return redirect("dashboard:journal-list")
