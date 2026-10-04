"""فرمِ کمپین/مناسبت در پنل مدیریت. تبدیلِ ورودیِ فرم به فیلدهایِ ``Campaign``؛
اعتبارسنجیِ ساختاریِ قواعد و پیکربندی در ``campaign_service.validate_campaign``."""

import datetime as dt
import json
from decimal import Decimal, InvalidOperation

from django import forms

from apps.core.jalali_utils import JalaliDateError, parse_jalali_date, store_timezone
from apps.core.utils import normalize_digits
from apps.engagement.models import Campaign
from apps.engagement.services import simple_setup


def _jdate(raw) -> dt.date | None:
    text = (raw or "").strip()
    if not text:
        return None
    head = normalize_digits(text).replace("-", "/").split("/")[0]
    try:
        if head.isdigit() and int(head) >= 1700:
            return dt.date.fromisoformat(normalize_digits(text).replace("/", "-"))
        return parse_jalali_date(text)
    except (ValueError, JalaliDateError) as exc:
        raise forms.ValidationError("تاریخ نامعتبر است (نمونه: ۱۴۰۵/۰۷/۰۱).") from exc


class JalaliDateField(forms.CharField):
    def __init__(self, **kw):
        kw.setdefault("required", False)
        kw.setdefault("max_length", 12)
        super().__init__(**kw)

    def clean(self, value):
        value = super().clean(value)
        return _jdate(value)


class OptionalIntField(forms.CharField):
    def __init__(self, *, min_value=None, max_value=None, **kw):
        kw.setdefault("required", False)
        self.min_value, self.max_value = min_value, max_value
        super().__init__(**kw)

    def clean(self, value):
        value = super().clean(value)
        text = normalize_digits(value or "").replace(",", "").replace("٬", "").strip()
        if not text:
            return None
        try:
            number = int(Decimal(text))
        except (InvalidOperation, ValueError) as exc:
            raise forms.ValidationError("عدد صحیح وارد کنید.") from exc
        if self.min_value is not None and number < self.min_value:
            raise forms.ValidationError(f"حداقل {self.min_value} است.")
        if self.max_value is not None and number > self.max_value:
            raise forms.ValidationError(f"حداکثر {self.max_value} است.")
        return number


class FreeMultipleField(forms.MultipleChoiceField):
    """چندانتخابیِ بدونِ فهرستِ ثابت (شهر/شناسه‌ها)؛ اعتبارسنجیِ واقعی در ``simple_setup`` و با ``store`` است."""

    def valid_value(self, value):
        return True


class CampaignForm(forms.Form):
    """فرمِ ساده‌ی کمپین/مناسبت. نکته‌یِ امنیتی: **هیچ فیلدِ متنِ پیامکی وجود ندارد** — متنِ پیامک
    فقط از قالبِ پلتفرم می‌آید؛ پس هر ``custom_sms_body`` در POST کاملاً نادیده گرفته می‌شود."""

    name = forms.CharField(label="نام", max_length=150)
    description = forms.CharField(label="توضیحات", required=False, widget=forms.Textarea)
    trigger_type = forms.ChoiceField(label="نوعِ اجرا", choices=Campaign.Trigger.choices)
    rules_json = forms.CharField(label="قواعد", required=False, widget=forms.HiddenInput)
    # مخاطبِ ساده: اگر ارسال نشود (فراخوانیِ قدیمی) رفتار همان «قواعدِ سفارشی» است.
    audience_kind = forms.ChoiceField(label="مخاطبان", required=False, choices=[(c, c) for c in simple_setup.AUDIENCE_CHOICES])
    audience_extra_kind = forms.ChoiceField(label="مخاطبِ خاص", required=False, choices=[(c, c) for c in simple_setup.EXTRA_CHOICES])
    audience_extra_values = FreeMultipleField(label="موردهایِ مخاطبِ خاص", required=False)
    rule_scope = forms.ChoiceField(label="دامنه‌ی ارزیابی", required=False, choices=Campaign.Scope.choices)
    period_mode = forms.ChoiceField(label="بازه‌ی خرید", required=False, choices=Campaign.PeriodMode.choices)
    period_jalali_year = OptionalIntField(label="سالِ شمسی", min_value=1300, max_value=1600)
    period_start_month = OptionalIntField(label="ماهِ شروع", min_value=1, max_value=12)
    period_end_month = OptionalIntField(label="ماهِ پایان", min_value=1, max_value=12)
    period_start_date = JalaliDateField(label="از تاریخ")
    period_end_date = JalaliDateField(label="تا تاریخ")
    valid_payment_statuses = forms.MultipleChoiceField(
        label="وضعیت‌هایِ پرداختِ معتبر", required=False,
        choices=[("paid", "پرداخت‌شده"), ("pending", "در انتظار پرداخت"), ("refunded", "مسترد"), ("failed", "ناموفق")],
    )
    amount_basis = forms.ChoiceField(label="مبنای مبلغ", required=False, choices=Campaign.AmountBasis.choices)

    reward_type = forms.ChoiceField(label="پاداش", required=False, choices=Campaign.Reward.choices)
    coupon_type = forms.ChoiceField(label="نوعِ تخفیف", required=False, choices=[("percent", "درصدی"), ("fixed", "مبلغ ثابت"), ("free_ship", "ارسال رایگان")])
    coupon_value = OptionalIntField(label="مقدار", min_value=0)
    coupon_max_discount = OptionalIntField(label="سقفِ تخفیف", min_value=1)
    coupon_min_order = OptionalIntField(label="حداقل سفارش", min_value=0)
    coupon_applies_to_gift_wrap = forms.BooleanField(label="تخفیف روی کادوپیچی", required=False)
    code_prefix = forms.CharField(label="پیشوند", required=False, max_length=12)
    personalized = forms.BooleanField(label="کدِ اختصاصیِ هر مشتری", required=False)
    code_starts_at = JalaliDateField(label="فعال‌سازیِ کد")
    code_expires_at = JalaliDateField(label="انقضایِ کد")
    code_valid_days = OptionalIntField(label="اعتبار (روز)", min_value=1, max_value=3650)
    total_redemption_limit = OptionalIntField(label="سقفِ کلِ استفاده", min_value=1)
    per_customer_limit = OptionalIntField(label="سقف برایِ هر مشتری", min_value=1)
    max_issuances = OptionalIntField(label="ظرفیتِ کمپین", min_value=1)
    per_customer_period_days = OptionalIntField(label="پنجره‌ی سقفِ هر مشتری (روز)", min_value=1, max_value=3650)
    validity_from_delivery = forms.BooleanField(label="اعتبار از لحظه‌ی تحویلِ اعلان", required=False)

    channels = forms.MultipleChoiceField(label="کانال‌ها", required=False, choices=[("sms", "پیامک"), ("email", "ایمیل")])
    channels_explicit = forms.BooleanField(label="کانال‌ها صریح", required=False)
    reminder_days_before_expiry = OptionalIntField(label="یادآوریِ انقضا (روز)", min_value=1, max_value=365)

    occasion_kind = forms.ChoiceField(label="نوعِ مناسبت", required=False, choices=[("", "—")] + list(Campaign.Occasion.choices))
    occasion_name = forms.CharField(label="نامِ مناسبت", required=False, max_length=100)
    occasion_offset_days = OptionalIntField(label="فاصله‌ی روز", min_value=-365, max_value=365)
    occ_n = OptionalIntField(label="تعدادِ سفارش", min_value=1)
    occ_amount = OptionalIntField(label="مبلغ", min_value=1)
    occ_days = OptionalIntField(label="روزِ عدمِ خرید", min_value=1)
    occ_month = OptionalIntField(label="ماه", min_value=1, max_value=12)
    occ_day = OptionalIntField(label="روز", min_value=1, max_value=31)
    occ_date = JalaliDateField(label="تاریخِ مناسبت")

    active_from = JalaliDateField(label="شروعِ فعالیت")
    active_until = JalaliDateField(label="پایانِ فعالیت")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, (forms.CheckboxInput, forms.CheckboxSelectMultiple, forms.HiddenInput)):
                continue
            widget.attrs.setdefault("class", "inp")
            if isinstance(field, (OptionalIntField, JalaliDateField)):
                widget.attrs.setdefault("dir", "ltr")
                widget.attrs.setdefault("inputmode", "numeric")
        self.fields["valid_payment_statuses"].widget = forms.CheckboxSelectMultiple()
        self.fields["channels"].widget = forms.CheckboxSelectMultiple()
        for name in ("period_start_date", "period_end_date", "code_starts_at", "code_expires_at", "active_from", "active_until", "occ_date"):
            self.fields[name].widget.attrs["placeholder"] = "۱۴۰۵/۰۷/۰۱"
        self.fields["description"].widget.attrs["rows"] = 2

    def clean_rule_scope(self):
        return self.cleaned_data.get("rule_scope") or Campaign.Scope.AGGREGATE

    def clean_period_mode(self):
        return self.cleaned_data.get("period_mode") or Campaign.PeriodMode.NONE

    def clean_amount_basis(self):
        return self.cleaned_data.get("amount_basis") or Campaign.AmountBasis.NET

    def clean_reward_type(self):
        return self.cleaned_data.get("reward_type") or Campaign.Reward.COUPON

    def clean_coupon_type(self):
        return self.cleaned_data.get("coupon_type") or "percent"

    def clean_rules_json(self):
        raw = self.cleaned_data.get("rules_json", "").strip()
        if not raw:
            return {}
        try:
            data = json.loads(raw)
        except ValueError as exc:
            raise forms.ValidationError("ساختارِ قواعد نامعتبر است.") from exc
        if not isinstance(data, dict):
            raise forms.ValidationError("ساختارِ قواعد نامعتبر است.")
        return data

    def clean(self):
        cleaned = super().clean()
        kind = cleaned.get("audience_kind") or simple_setup.AUDIENCE_CUSTOM
        extra = cleaned.get("audience_extra_kind") or ""
        if kind != simple_setup.AUDIENCE_CUSTOM and extra and not cleaned.get("audience_extra_values"):
            self.add_error("audience_extra_values", "برای «مخاطبِ خاص» حداقل یک مورد را انتخاب کنید.")
        if cleaned.get("trigger_type") == Campaign.Trigger.OCCASION and not cleaned.get("occasion_kind"):
            self.add_error("occasion_kind", "مناسبت را انتخاب کنید.")
        return cleaned

    # --- تبدیل به مدل ---------------------------------------------------------
    def _audience_rules(self, campaign: Campaign) -> dict:
        """قواعدِ شمول: «مخاطبِ ساده» → درختِ معتبر؛ «سفارشی/قدیمی» → همان ``rules_json``."""
        cd = self.cleaned_data
        kind = cd.get("audience_kind") or simple_setup.AUDIENCE_CUSTOM
        if kind == simple_setup.AUDIENCE_CUSTOM:
            return cd["rules_json"]
        return simple_setup.build_audience_rules(
            kind, cd.get("audience_extra_kind") or "", cd.get("audience_extra_values") or [], campaign.store,
        )

    @staticmethod
    def _start_of_day(d):
        return dt.datetime.combine(d, dt.time.min, tzinfo=store_timezone()) if d else None

    @staticmethod
    def _end_of_day(d):
        return dt.datetime.combine(d, dt.time(23, 59, 59), tzinfo=store_timezone()) if d else None

    def apply_to(self, campaign: Campaign) -> Campaign:
        cd = self.cleaned_data
        campaign.name = cd["name"].strip()
        campaign.description = cd["description"]
        campaign.trigger_type = cd["trigger_type"]
        campaign.rules = self._audience_rules(campaign)
        campaign.rule_scope = cd["rule_scope"]
        campaign.period_mode = cd["period_mode"]
        campaign.period_jalali_year = cd["period_jalali_year"]
        campaign.period_start_month = cd["period_start_month"]
        campaign.period_end_month = cd["period_end_month"]
        campaign.period_start_date = cd["period_start_date"]
        campaign.period_end_date = cd["period_end_date"]
        campaign.valid_payment_statuses = cd["valid_payment_statuses"] or ["paid"]
        campaign.amount_basis = cd["amount_basis"]
        campaign.reward_type = cd["reward_type"]
        campaign.coupon_type = cd["coupon_type"]
        campaign.coupon_value = Decimal(cd["coupon_value"] or 0)
        campaign.coupon_max_discount = Decimal(cd["coupon_max_discount"]) if cd["coupon_max_discount"] else None
        campaign.coupon_min_order = Decimal(cd["coupon_min_order"] or 0)
        campaign.coupon_applies_to_gift_wrap = cd["coupon_applies_to_gift_wrap"]
        campaign.code_prefix = cd["code_prefix"].strip().upper()
        campaign.personalized = cd["personalized"]
        campaign.code_starts_at = self._start_of_day(cd["code_starts_at"])
        campaign.code_expires_at = self._end_of_day(cd["code_expires_at"])
        campaign.code_valid_days = cd["code_valid_days"]
        campaign.total_redemption_limit = cd["total_redemption_limit"]
        campaign.per_customer_limit = cd["per_customer_limit"]
        campaign.max_issuances = cd["max_issuances"]
        campaign.per_customer_period_days = cd["per_customer_period_days"]
        campaign.validity_from_delivery = cd["validity_from_delivery"]
        campaign.channels = cd["channels"]
        campaign.channels_explicit = cd["channels_explicit"]
        # متنِ پیامک (و متنِ اختیاریِ قدیمیِ ایمیل) عمداً دست‌نخورده می‌ماند: از فرم تغییر نمی‌کند.
        campaign.reminder_days_before_expiry = cd["reminder_days_before_expiry"]
        # نوعِ مناسبت فقط برایِ کمپینِ مناسبتی معنا دارد
        campaign.occasion_kind = (cd["occasion_kind"] or "") if campaign.trigger_type == Campaign.Trigger.OCCASION else ""
        campaign.occasion_name = cd["occasion_name"].strip()
        campaign.occasion_offset_days = cd["occasion_offset_days"] or 0
        params = {}
        kind = campaign.occasion_kind
        if kind == Campaign.Occasion.ORDER_MILESTONE:
            params = {"n": cd["occ_n"]}
        elif kind == Campaign.Occasion.SPENDING_MILESTONE:
            params = {"amount": cd["occ_amount"]}
        elif kind == Campaign.Occasion.REACTIVATION:
            params = {"days": cd["occ_days"]}
        elif kind == Campaign.Occasion.HOLIDAY:
            params = {"month": cd["occ_month"], "day": cd["occ_day"]}
        elif kind == Campaign.Occasion.CUSTOM_DATE:
            params = {"date": cd["occ_date"].isoformat() if cd["occ_date"] else ""}
        campaign.occasion_params = params
        campaign.active_from = self._start_of_day(cd["active_from"])
        campaign.active_until = self._end_of_day(cd["active_until"])
        return campaign

    @staticmethod
    def initial_from(campaign: Campaign) -> dict:
        from apps.core.jalali_utils import format_jalali
        from apps.core.utils import to_fa_digits

        def jd(value):
            return to_fa_digits(format_jalali(value)) if value else ""

        p = campaign.occasion_params or {}
        return {
            "name": campaign.name, "description": campaign.description, "trigger_type": campaign.trigger_type,
            "rules_json": json.dumps(campaign.rules or {}, ensure_ascii=False), "rule_scope": campaign.rule_scope,
            "period_mode": campaign.period_mode, "period_jalali_year": campaign.period_jalali_year,
            "period_start_month": campaign.period_start_month, "period_end_month": campaign.period_end_month,
            "period_start_date": jd(campaign.period_start_date), "period_end_date": jd(campaign.period_end_date),
            "valid_payment_statuses": campaign.valid_payment_statuses or ["paid"], "amount_basis": campaign.amount_basis,
            "reward_type": campaign.reward_type, "coupon_type": campaign.coupon_type,
            "coupon_value": int(campaign.coupon_value), "coupon_max_discount": int(campaign.coupon_max_discount) if campaign.coupon_max_discount else "",
            "coupon_min_order": int(campaign.coupon_min_order), "coupon_applies_to_gift_wrap": campaign.coupon_applies_to_gift_wrap,
            "code_prefix": campaign.code_prefix, "personalized": campaign.personalized,
            "code_starts_at": jd(campaign.code_starts_at), "code_expires_at": jd(campaign.code_expires_at),
            "code_valid_days": campaign.code_valid_days or "", "total_redemption_limit": campaign.total_redemption_limit or "",
            "per_customer_limit": campaign.per_customer_limit or "", "max_issuances": campaign.max_issuances or "",
            "per_customer_period_days": campaign.per_customer_period_days or "",
            "validity_from_delivery": campaign.validity_from_delivery,
            # کمپینِ قدیمیِ بدونِ انتخابِ صریح یعنی «همه‌ی کانال‌ها» — همان را نشان بده
            "channels": campaign.channels if (campaign.channels_explicit or campaign.channels) else ["sms", "email"],
            "channels_explicit": True,
            "reminder_days_before_expiry": campaign.reminder_days_before_expiry or "",
            "occasion_kind": campaign.occasion_kind, "occasion_name": campaign.occasion_name,
            "occasion_offset_days": campaign.occasion_offset_days,
            "occ_n": p.get("n", ""), "occ_amount": p.get("amount", ""), "occ_days": p.get("days", ""),
            "occ_month": p.get("month", ""), "occ_day": p.get("day", ""),
            "occ_date": to_fa_digits(format_jalali(dt.date.fromisoformat(p["date"]))) if p.get("date") else "",
            "active_from": jd(campaign.active_from), "active_until": jd(campaign.active_until),
            **{f"audience_{k}": v for k, v in simple_setup.detect_audience(campaign.rules, campaign.store).items()},
        }
