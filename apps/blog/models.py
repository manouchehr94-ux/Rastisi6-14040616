from django.db import models
from django.urls import reverse

from apps.core.models import TimeStampedModel


class BlogPost(TimeStampedModel):
    # NULL means a legacy, intentionally platform-wide editorial item.
    # New demo and merchant articles must always be owned by one Store.
    store = models.ForeignKey(
        "stores.Store", verbose_name="فروشگاه", on_delete=models.CASCADE,
        related_name="journal_posts", null=True, blank=True,
    )
    title = models.CharField("عنوان", max_length=220)
    slug = models.SlugField("اسلاگ", max_length=240, unique=True, allow_unicode=True)
    category_label = models.CharField("دسته‌ی نمایشی", max_length=80, blank=True)
    cover_emoji = models.CharField("اموجی کاور", max_length=10, blank=True)
    cover_image = models.ImageField("تصویر کاور", upload_to="blog/covers/", null=True, blank=True)
    tint = models.CharField("رنگ پس‌زمینه", max_length=20, blank=True)
    excerpt = models.CharField("خلاصه", max_length=300, blank=True)
    body = models.TextField("متن مطلب")
    published_at = models.DateTimeField("تاریخ انتشار", null=True, blank=True)

    class Meta:
        verbose_name = "مطلب وبلاگ"
        verbose_name_plural = "مطالب وبلاگ"
        ordering = ["-published_at", "-created_at"]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("blog:detail", kwargs={"slug": self.slug})

    @property
    def has_available_cover(self):
        """Avoid rendering an <img> for a missing demo-media file.

        Do not rewrite the saved ImageField or substitute an unrelated image.
        Storage can be remote; fail closed for unavailable assets.
        """
        if not self.cover_image or not self.cover_image.name:
            return False
        try:
            return self.cover_image.storage.exists(self.cover_image.name)
        except (OSError, ValueError):
            return False
