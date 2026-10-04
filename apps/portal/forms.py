from django import forms

from apps.stores.services.enamad_verification_service import (
    EnamadBadgeError,
    EnamadVerificationMetaError,
    parse_enamad_badge_identifiers,
    parse_enamad_verification_meta_tag,
)


class OwnerPhoneRequestForm(forms.Form):
    full_name = forms.CharField(label="نام و نام خانوادگی", max_length=150, required=False)
    phone = forms.CharField(
        label="شماره موبایل", max_length=20,
        widget=forms.TextInput(attrs={"autocomplete": "tel", "dir": "ltr"}),
    )
    remember_me = forms.BooleanField(label="مرا به خاطر بسپار", required=False)


class OwnerOtpVerifyForm(forms.Form):
    phone = forms.CharField(widget=forms.HiddenInput)
    full_name = forms.CharField(widget=forms.HiddenInput, required=False)
    code = forms.CharField(
        label="کد تأیید", max_length=6, min_length=6,
        widget=forms.TextInput(attrs={"autocomplete": "one-time-code", "inputmode": "numeric"}),
    )


class OwnerRegisterForm(forms.Form):
    full_name = forms.CharField(label="نام و نام خانوادگی", max_length=150)
    email = forms.EmailField(label="ایمیل")
    password = forms.CharField(label="رمز عبور", widget=forms.PasswordInput)


class OwnerLoginForm(forms.Form):
    """اکنون فقط برایِ ورودِ مدیرِ پلتفرم استفاده می‌شود (ایمیل+رمز — بدونِ
    OTP، یک تصمیمِ محافظه‌کارانه‌ی امنیتی — نگاه کنید به یکپارچه‌سازیِ
    احرازِ هویت)؛ ورودِ مالک از ``OwnerIdentifierLoginForm`` استفاده می‌کند."""

    email = forms.EmailField(
        label="ایمیل", widget=forms.EmailInput(attrs={"autocomplete": "username"}),
    )
    password = forms.CharField(
        label="رمز عبور", widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )
    remember_me = forms.BooleanField(label="مرا به خاطر بسپار", required=False)


class OwnerIdentifierLoginForm(forms.Form):
    """فرمِ یکپارچه‌ی ورود با رمز: موبایل، نام کاربری یا ایمیل."""

    identifier = forms.CharField(
        label="شماره موبایل، نام کاربری یا ایمیل",
        widget=forms.TextInput(attrs={"autocomplete": "username", "dir": "ltr"}),
    )
    password = forms.CharField(
        label="رمز عبور",
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )
    remember_me = forms.BooleanField(label="مرا به خاطر بسپار", required=False)


class PasswordResetRequestForm(forms.Form):
    email = forms.EmailField(label="ایمیل")


class PasswordResetConfirmForm(forms.Form):
    password = forms.CharField(label="رمز عبور جدید", widget=forms.PasswordInput)
    password_confirm = forms.CharField(label="تکرار رمز عبور", widget=forms.PasswordInput)

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("password") and cleaned.get("password") != cleaned.get("password_confirm"):
            raise forms.ValidationError("رمز عبور و تکرار آن یکسان نیستند")
        return cleaned


class CreateStoreForm(forms.Form):
    name = forms.CharField(label="نام فروشگاه", max_length=200)
    industry_template_id = forms.IntegerField(label="صنف", required=False)
    submission_token = forms.CharField(widget=forms.HiddenInput, required=False)


class PlatformConfigurationForm(forms.ModelForm):
    """تنظیماتِ عمومیِ پلتفرم (Platform Owner Admin » تنظیماتِ پلتفرم) — هویت،
    پیش‌فرض‌هایِ تجاری، و عملیات. پیکربندیِ درگاهِ پیامکِ مرکزی از این فرم جدا
    است (نگاه کنید به ``PlatformSmsConfigForm``/صفحه‌ی «پیامک › تنظیماتِ
    درگاه») تا این دو دغدغه‌ی متفاوت (هویتِ برند در برابرِ اعتبارنامه‌ی
    زیرساخت) در یک فرم قاطی نشوند."""

    class Meta:
        from .models import PlatformConfiguration

        model = PlatformConfiguration
        fields = [
            "default_trial_days", "deletion_retention_days",
            "primary_brand_color", "secondary_brand_color",
            "temporary_logo_text", "logo",
            "support_contact_phone", "support_contact_email",
            "default_payment_provider", "enamad_verification_meta_tag",
            "enamad_id", "enamad_auth_code", "enamad_badge_enabled",
            "maintenance_mode_enabled", "new_store_registration_enabled",
        ]
        widgets = {
            "enamad_verification_meta_tag": forms.Textarea(attrs={
                "rows": 3,
                "dir": "ltr",
                "placeholder": '<meta name="..." content="...">',
                "spellcheck": "false",
            }),
        }

    def clean_enamad_verification_meta_tag(self):
        value = (self.cleaned_data.get("enamad_verification_meta_tag") or "").strip()
        if not value:
            return ""
        try:
            parse_enamad_verification_meta_tag(value)
        except EnamadVerificationMetaError as exc:
            raise forms.ValidationError(str(exc)) from exc
        return value

    def clean(self):
        cleaned_data = super().clean()
        enamad_id = (cleaned_data.get("enamad_id") or "").strip()
        auth_code = (cleaned_data.get("enamad_auth_code") or "").strip()
        try:
            parse_enamad_badge_identifiers(enamad_id, auth_code)
        except EnamadBadgeError as exc:
            self.add_error("enamad_auth_code", str(exc))
        cleaned_data["enamad_id"] = enamad_id
        cleaned_data["enamad_auth_code"] = auth_code
        return cleaned_data

    def clean_deletion_retention_days(self):
        days = self.cleaned_data["deletion_retention_days"]
        if not (180 <= days <= 365):
            raise forms.ValidationError("روزهای نگهداری باید بین ۱۸۰ تا ۳۶۵ باشد.")
        return days


class PlatformSmsConfigForm(forms.ModelForm):
    """درگاهِ پیامکِ مرکزیِ پلتفرم — صفحه‌ی جداگانه‌ی «پیامک › تنظیماتِ درگاه»
    (Platform Owner Admin بخشِ ۱۲)؛ اعتبارنامه‌ها فیلدهایِ مدل نیستند (داخلِ
    ``encrypted_sms_credentials`` رمزنگاری‌شده ذخیره می‌شوند) — اینجا صراحتاً
    به‌صورتِ فیلدِ اضافیِ فرم اعلام شده‌اند، write-only مثلِ
    ``dashboard.forms.SmsConnectionForm`` (هرگز مقدارِ ذخیره‌شده echo
    نمی‌شود؛ خالی‌ماندن یعنی «بدونِ تغییر»، نه «پاک‌کردن»)."""

    sms_melipayamak_username = forms.CharField(
        label="نام کاربری ملی‌پیامک", max_length=100, required=False,
    )
    sms_melipayamak_password = forms.CharField(
        label="رمز عبور ملی‌پیامک", max_length=100, required=False,
        widget=forms.PasswordInput(render_value=False, attrs={"placeholder": "برای تغییر وارد کنید"}),
    )
    sms_melipayamak_otp_body_id = forms.CharField(
        label="BodyId الگوی OTP ملی‌پیامک", max_length=30, required=False,
        help_text="BodyId الگوی خدماتی تأیید موبایل/OTP در پنل ملی‌پیامک.",
    )
    sms_melipayamak_otp_variables_order = forms.CharField(
        label="ترتیب متغیرهای الگوی OTP", max_length=120, required=False,
        initial="otp_code",
        help_text="مثال: otp_code یا otp_code,expire_minutes",
    )
    sms_otp_fallback_enabled = forms.BooleanField(
        label="اگر ملی‌پیامک خطا داد، OTP با کاوه‌نگار ارسال شود",
        required=False,
    )
    sms_kavenegar_api_key = forms.CharField(
        label="کلید API کاوه‌نگار", max_length=100, required=False,
        widget=forms.PasswordInput(render_value=False, attrs={"placeholder": "برای تغییر وارد کنید"}),
    )
    sms_kavenegar_otp_template = forms.CharField(
        label="نام Template کاوه‌نگار برای OTP", max_length=100, required=False,
        help_text="فقط برای Fallback VerifyLookup؛ در حالت عادی استفاده نمی‌شود.",
    )

    class Meta:
        from .models import PlatformConfiguration

        model = PlatformConfiguration
        fields = ["sms_backend", "sms_sender_number"]


class OnboardingIdentityForm(forms.Form):
    """مرحله‌ی ۱ ویزارد آنبوردینگ (Section 5): معرفیِ فروشگاه.

    راهنمای هر فیلدِ اختیاری فقط به‌صورت HTML ``placeholder`` نشان داده
    می‌شود — یک متنِ نمونه/راهنما هرگز نباید مقدارِ واقعیِ فیلد باشد و
    هرگز در دیتابیس ذخیره نمی‌شود؛ اگر کاربر چیزی وارد نکند، فیلد واقعاً
    خالی می‌ماند."""

    name = forms.CharField(
        label="نام فروشگاه", max_length=150,
        widget=forms.TextInput(attrs={"placeholder": "مثلاً: فروشگاه لوازم خانگی رضایی"}),
    )
    tagline = forms.CharField(
        label="شعار فروشگاه", max_length=200, required=False,
        widget=forms.TextInput(attrs={"placeholder": "مثلاً: بهترین کیفیت، مناسب‌ترین قیمت"}),
    )
    description = forms.CharField(
        label="درباره‌ی فروشگاه", required=False,
        widget=forms.Textarea(attrs={"placeholder": "مثلاً: فروشگاه ما از سال ... با هدف ... راه‌اندازی شده است."}),
    )
    contact_phone = forms.CharField(
        label="شماره تماس", max_length=30, required=False,
        widget=forms.TextInput(attrs={"placeholder": "مثلاً: 021-12345678"}),
    )
    contact_email = forms.EmailField(
        label="ایمیل فروشگاه", required=False,
        widget=forms.EmailInput(attrs={"placeholder": "مثلاً: info@example.com"}),
    )
    contact_address = forms.CharField(
        label="آدرس", max_length=300, required=False,
        widget=forms.TextInput(attrs={"placeholder": "مثلاً: تهران، خیابان ..."}),
    )


class OnboardingIndustryForm(forms.Form):
    """مرحله‌ی ۲ ویزارد آنبوردینگ: انتخابِ صنف (اختیاری، فقط یک‌بار قابلِ نصب - ADR-25)."""

    industry_template_id = forms.IntegerField(required=False)


class OnboardingBrandingForm(forms.Form):
    """مرحله‌ی ۳ ویزارد آنبوردینگ: هویتِ بصریِ فروشگاه (اختیاری).

    فقط لوگو — انتخابِ رنگِ اصلی/مکمل (کدِ hex) عمداً از آنبوردینگ حذف شده:
    یک تاجرِ معمولی نباید هنگامِ ساختِ اولیه‌ی فروشگاه با مقادیرِ hex سروکار
    داشته باشد؛ رنگ‌ها هر زمان از داخلِ Storefront Builder/پنلِ مدیریت
    قابلِ‌تنظیم‌اند (که کنترل‌های رنگِ خودش را همچنان دارد و از این تغییر
    متأثر نمی‌شود) — پیش‌فرضِ ``ShopSettings.primary_color``/``accent_color``
    هم دست‌نخورده می‌ماند."""

    logo = forms.ImageField(label="لوگو", required=False)


class ContactForm(forms.Form):
    full_name = forms.CharField(label="نام", max_length=150)
    email = forms.EmailField(label="ایمیل")
    subject = forms.CharField(label="موضوع", max_length=200, required=False)
    message = forms.CharField(label="پیام", widget=forms.Textarea, max_length=4000)
