import re

from django import forms

from apps.core.utils import normalize_digits

PHONE_RE = re.compile(r"^09\d{9}$")
POSTAL_RE = re.compile(r"^\d{10}$")


class CheckoutAddressForm(forms.Form):
    """فرم اطلاعات گیرنده‌ی سفارش — مرحله‌ی ۱ تسویه‌حساب."""

    receiver_name = forms.CharField(label="نام و نام خانوادگی", max_length=150)
    phone = forms.CharField(label="شماره موبایل", max_length=15)
    province = forms.CharField(label="استان", max_length=80)
    city = forms.CharField(label="شهر", max_length=80)
    postal_code = forms.CharField(label="کد پستی", max_length=10, required=False)
    full_address = forms.CharField(label="آدرس پستی کامل", widget=forms.Textarea)
    note = forms.CharField(label="توضیحات سفارش", max_length=300, required=False)
    # اختیاری — خالی بودن هرگز تولدِ ذخیره‌شده‌ی مشتری را پاک نمی‌کند.
    birth_date = forms.CharField(label="تاریخ تولد (اختیاری)", max_length=12, required=False)
    # رضایتِ تبلیغاتی: اختیاری، هرگز از پیش‌تیک‌خورده؛ نزدنِ تیک رضایتِ قبلی را پس نمی‌گیرد (فقط تنظیماتِ حساب).
    accepts_promotional_sms = forms.BooleanField(label="دریافت پیامک‌های تبلیغاتی", required=False)
    accepts_promotional_email = forms.BooleanField(label="دریافت ایمیل‌های تبلیغاتی", required=False)

    def clean_birth_date(self):
        from apps.customers.services.profile_service import BirthDateError, parse_birth_date

        try:
            return parse_birth_date(self.cleaned_data.get("birth_date", ""))
        except BirthDateError as exc:
            raise forms.ValidationError(str(exc)) from exc

    def clean_phone(self):
        phone = normalize_digits(self.cleaned_data["phone"]).strip()
        if not PHONE_RE.match(phone):
            raise forms.ValidationError("شماره موبایل معتبر نیست (مثال: 09123456789)")
        return phone

    def clean_postal_code(self):
        postal_code = normalize_digits(self.cleaned_data.get("postal_code", "")).strip()
        if postal_code and not POSTAL_RE.match(postal_code):
            raise forms.ValidationError("کد پستی باید ۱۰ رقم باشد")
        return postal_code
