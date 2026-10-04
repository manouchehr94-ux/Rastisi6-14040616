"""Upload validation for platform-owned marketing website imagery only."""

from pathlib import Path

from django import forms
from django.core.exceptions import ValidationError

from .models import PublicSitePhoto


class PublicSitePhotoForm(forms.ModelForm):
    MAX_BYTES = 4 * 1024 * 1024

    class Meta:
        model = PublicSitePhoto
        fields = ("image", "alt_text")
        widgets = {
            "image": forms.ClearableFileInput(attrs={
                "accept": "image/webp,image/jpeg,image/png",
                "class": "pa-input",
            }),
            "alt_text": forms.TextInput(attrs={
                "class": "pa-input",
                "placeholder": "توصیف کوتاه و واقعی عکس",
                "maxlength": "180",
            }),
        }

    def clean_image(self):
        image = self.cleaned_data.get("image")
        if image is False or image is None:
            raise ValidationError("یک تصویر معتبر بارگذاری کنید.")
        if image.size > self.MAX_BYTES:
            raise ValidationError("حجم تصویر نباید بیشتر از ۴ مگابایت باشد.")

        suffix = Path(image.name).suffix.lower()
        if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
            raise ValidationError("فرمت مجاز فقط JPEG، PNG یا WebP است.")

        # Django's ImageField validates the actual bytes using Pillow.
        image_format = getattr(getattr(image, "image", None), "format", None)
        if image_format not in {"JPEG", "PNG", "WEBP"}:
            raise ValidationError("محتوای فایل با فرمت تصویری مجاز سازگار نیست.")
        if image.image.width > 5000 or image.image.height > 5000:
            raise ValidationError("ابعاد تصویر نباید بیشتر از ۵۰۰۰ پیکسل باشد.")
        return image
