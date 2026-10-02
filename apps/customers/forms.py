import re

from django import forms

from apps.core.phone import InvalidPhoneError, normalize_iranian_phone
from apps.core.utils import normalize_digits

POSTAL_RE = re.compile(r"^\d{10}$")


class PhoneCleanMixin:
    def clean_phone(self):
        try:
            return normalize_iranian_phone(self.cleaned_data["phone"])
        except InvalidPhoneError as exc:
            raise forms.ValidationError(exc.messages[0] if exc.messages else str(exc)) from exc


class LoginForm(forms.Form):
    """فرمِ کانونیکالِ ورودِ مشتری با رمز عبور — شناسه می‌تواند ایمیل یا
    شماره موبایل باشد (یکپارچه‌سازیِ احرازِ هویت)."""

    identifier = forms.CharField(
        label="ایمیل یا شماره موبایل", max_length=150,
        widget=forms.TextInput(attrs={"autocomplete": "username", "dir": "ltr"}),
    )
    password = forms.CharField(
        label="رمز عبور", widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )
    remember_me = forms.BooleanField(label="مرا به خاطر بسپار", required=False)

    def clean_identifier(self):
        value = normalize_digits(self.cleaned_data.get("identifier") or "").strip()
        if "@" in value:
            return value
        try:
            return normalize_iranian_phone(value)
        except InvalidPhoneError as exc:
            raise forms.ValidationError(exc.messages[0] if exc.messages else str(exc)) from exc


class OtpRequestForm(PhoneCleanMixin, forms.Form):
    phone = forms.CharField(
        label="شماره موبایل", max_length=15,
        widget=forms.TextInput(attrs={"autocomplete": "tel", "dir": "ltr"}),
    )
    remember_me = forms.BooleanField(label="مرا به خاطر بسپار", required=False)


class OtpVerifyForm(PhoneCleanMixin, forms.Form):
    phone = forms.CharField(label="شماره موبایل", max_length=15, widget=forms.HiddenInput)
    code = forms.CharField(
        label="کد تأیید", max_length=6,
        widget=forms.TextInput(attrs={"autocomplete": "one-time-code", "inputmode": "numeric"}),
    )
    remember_me = forms.BooleanField(widget=forms.HiddenInput, required=False)


class SignupForm(PhoneCleanMixin, forms.Form):
    full_name = forms.CharField(label="نام و نام خانوادگی", max_length=150)
    phone = forms.CharField(label="شماره موبایل", max_length=15)
    password = forms.CharField(label="رمز عبور", widget=forms.PasswordInput)


class BirthDateFieldMixin:
    """فیلدِ اختیاریِ تاریخ تولد (ورودی/نمایشِ جلالی) — مقدارِ خالی یعنی «تغییر نده»."""

    def clean_birth_date(self):
        from apps.customers.services.profile_service import BirthDateError, parse_birth_date

        try:
            return parse_birth_date(self.cleaned_data.get("birth_date", ""))
        except BirthDateError as exc:
            raise forms.ValidationError(str(exc)) from exc


class ProfileForm(BirthDateFieldMixin, forms.Form):
    full_name = forms.CharField(label="نام و نام خانوادگی", max_length=150)
    email = forms.EmailField(label="ایمیل", required=False)
    city = forms.CharField(label="شهر", max_length=80, required=False)
    birth_date = forms.CharField(label="تاریخ تولد", max_length=12, required=False)
    accepts_promotional_sms = forms.BooleanField(label="دریافت پیامک‌های تبلیغاتی", required=False)
    accepts_promotional_email = forms.BooleanField(label="دریافت ایمیل‌های تبلیغاتی", required=False)


class AddressForm(PhoneCleanMixin, forms.Form):
    receiver_name = forms.CharField(label="نام گیرنده", max_length=150)
    phone = forms.CharField(label="شماره موبایل گیرنده", max_length=15)
    province = forms.CharField(label="استان", max_length=80)
    city = forms.CharField(label="شهر", max_length=80)
    postal_code = forms.CharField(label="کد پستی", max_length=10, required=False)
    full_address = forms.CharField(label="آدرس پستی کامل", widget=forms.Textarea)

    def clean_postal_code(self):
        postal_code = normalize_digits(self.cleaned_data.get("postal_code", "")).strip()
        if postal_code and not POSTAL_RE.match(postal_code):
            raise forms.ValidationError("کد پستی باید ۱۰ رقم باشد")
        return postal_code
