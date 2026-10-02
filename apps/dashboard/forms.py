import re
from decimal import Decimal, InvalidOperation

from django import forms

from apps.catalog.models import Attribute, Brand, Category, Product, ProductTag
from apps.core.color_utils import contrast_ratio, safe_hex
from apps.core.models import ShopSettings
from apps.core.utils import normalize_digits
from apps.orders.models import TaxClass
from apps.sms.services.sms_service import SmsTemplateError, validate_template_body

from .services.catalog_admin_service import leaf_categories

PHONE_RE = re.compile(r"^09\d{9}$")


class NumericCleanMixin:
    """نرمال‌سازی ارقام فارسی/عربی به لاتین پیش از تبدیل به عدد — مثل بقیه‌ی فرم‌های سایت."""

    def _clean_int(self, field_name, *, min_value=None, max_value=None):
        raw = normalize_digits(self.cleaned_data.get(field_name, "")).strip()
        if raw == "":
            raise forms.ValidationError("این فیلد الزامی است")
        try:
            value = int(raw)
        except ValueError:
            raise forms.ValidationError("باید یک عدد صحیح باشد")
        if min_value is not None and value < min_value:
            raise forms.ValidationError(f"باید حداقل {min_value} باشد")
        if max_value is not None and value > max_value:
            raise forms.ValidationError(f"باید حداکثر {max_value} باشد")
        return value

    def _clean_decimal(self, field_name, *, min_value=None, max_value=None):
        raw = normalize_digits(self.cleaned_data.get(field_name, "")).strip()
        if raw == "":
            raise forms.ValidationError("این فیلد الزامی است")
        try:
            value = Decimal(raw)
        except InvalidOperation:
            raise forms.ValidationError("باید یک عدد باشد")
        if min_value is not None and value < min_value:
            raise forms.ValidationError(f"باید حداقل {min_value} باشد")
        if max_value is not None and value > max_value:
            raise forms.ValidationError(f"باید حداکثر {max_value} باشد")
        return value


class ProductForm(NumericCleanMixin, forms.Form):
    STATUS_CHOICES = [
        (Product.Status.ACTIVE, "فعال"),
        (Product.Status.INACTIVE, "غیرفعال"),
        (Product.Status.DRAFT, "پیش‌نویس"),
    ]

    name = forms.CharField(label="نام کالا", max_length=220)
    sku = forms.CharField(label="کد کالا (SKU)", max_length=40)
    category = forms.ModelChoiceField(
        label="زیرگروه کالا", queryset=Category.objects.none(),
        error_messages={"required": "انتخاب زیرگروه الزامی است"},
    )
    # واحدِ شمارش/مدل-کدِ فنی/کشورِ سازنده (Product Entry final wave 1) — هر
    # سه در تبِ «دسته‌بندی» فرم نمایش داده می‌شوند. ``required=False`` تا
    # ارسال‌های بدونِ این فیلد (فرم‌های قدیمی/تست‌هایی که آن را نمی‌فرستند —
    # دقیقاً همان قراردادِ ``product_type`` در همین فرم) رد نشوند؛ خالی یعنی
    # «پیشِ‌فرضِ PIECE» (نگاه کنید به ``_save_product``)، نه خطا.
    unit = forms.ChoiceField(
        label="واحد شمارش", choices=Product.Unit.choices, initial=Product.Unit.PIECE, required=False,
    )
    model_code = forms.CharField(label="مدل یا کد فنی", max_length=80, required=False)
    country_of_origin = forms.CharField(label="کشور سازنده", max_length=80, required=False)
    # «گروهِ دوم» (Product Entry final prototype) — یک ProductTagِ اختیاری با
    # purpose=COLLECTION؛ برخلافِ ``tags`` (چندتایی)، اینجا حداکثر یکی قابلِ
    # انتخاب است — دقیقاً همان قراردادِ ویجتِ تک‌انتخابیِ پروتوتایپ.
    second_group = forms.ModelChoiceField(label="گروه دوم", queryset=ProductTag.objects.none(), required=False)
    brand = forms.ModelChoiceField(label="برند", queryset=Brand.objects.none(), required=False)
    # required=False در سطحِ فیلد: چون بررسیِ واقعیِ الزامی‌بودن به status
    # بستگی دارد (پیش‌نویس مجاز به قیمتِ خالی است)، این تصمیم باید در
    # ``clean_price`` گرفته شود؛ اگر این فیلد required=True می‌ماند، خودِ
    # CharField پیش از رسیدن به ``clean_price`` با «این فیلد لازم است» رد
    # می‌شد و منطقِ ``clean_price`` هرگز اجرا نمی‌شد.
    price = forms.CharField(label="قیمت (تومان)", required=False)
    discount_percent = forms.CharField(label="تخفیف (٪)", required=False, initial="0")
    stock = forms.CharField(label="موجودی انبار", required=False, initial="0")
    status = forms.ChoiceField(label="وضعیت", choices=STATUS_CHOICES, initial=Product.Status.ACTIVE)
    icon = forms.CharField(label="آیکون (ایموجی)", max_length=10, required=False)
    description = forms.CharField(label="توضیحات کوتاه", widget=forms.Textarea, required=False)
    # اختیاری است تا فرم‌های قدیمی/تست‌هایی که این فیلد را ارسال نمی‌کنند همچنان کار کنند؛
    # وقتی خالی باشد یعنی «نوع کالا تغییر نکند» و از سرویس گذار نوع کالا استفاده نمی‌شود.
    product_type = forms.ChoiceField(
        label="نوع کالا", choices=Product.ProductType.choices, required=False,
    )

    # لجستیک (Phase 1C)
    barcode = forms.CharField(label="بارکد محصول", max_length=64, required=False)
    weight_grams = forms.CharField(label="وزن (گرم)", required=False)
    requires_shipping = forms.BooleanField(label="نیاز به ارسال فیزیکی", required=False, initial=True)
    tax_class = forms.ModelChoiceField(
        label="دسته‌ی مالیاتی", queryset=TaxClass.objects.none(), required=False,
        help_text="خالی = استفاده از دسته‌ی پیش‌فرضِ فروشگاه",
    )

    # سئو (Phase 1C)
    seo_title = forms.CharField(label="عنوان سئو", max_length=70, required=False)
    seo_description = forms.CharField(label="توضیحات متا", max_length=160, required=False, widget=forms.Textarea)
    # آدرسِ کالا (Product Entry rebuild) — اختیاری؛ خالی یعنی «خودکار از رویِ
    # نام بساز» (همان رفتارِ قبلی، بدون تغییر).
    slug = forms.CharField(label="آدرس محصول", max_length=240, required=False)
    # نمایش/زمان‌بندیِ انتشار (بخشِ ۱۹) — اختیاری؛ خالی یعنی بدونِ زمان‌بندی.
    visibility = forms.ChoiceField(
        label="نمایش", choices=Product.Visibility.choices, required=False, initial=Product.Visibility.PUBLIC,
    )
    publish_at = forms.CharField(label="زمانِ انتشارِ زمان‌بندی‌شده", required=False)
    # برچسب‌ها — رشته‌ی جداشده با کاما که ویجتِ چیپِ Alpine.js پر می‌کند.
    tags = forms.CharField(label="برچسب‌ها", required=False, widget=forms.HiddenInput)

    def __init__(self, *args, store, instance=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance = instance
        self.store = store
        self.fields["category"].queryset = leaf_categories(store)
        self.fields["brand"].queryset = Brand.objects.filter(store=store).order_by("name")
        self.fields["tax_class"].queryset = TaxClass.objects.filter(store=store, is_active=True).order_by("name")
        self.fields["second_group"].queryset = ProductTag.objects.filter(
            store=store, is_active=True, purpose=ProductTag.Purpose.COLLECTION,
        ).order_by("name")

    def clean_slug(self):
        from django.utils.text import slugify

        raw = (self.cleaned_data.get("slug") or "").strip()
        if not raw:
            return ""
        candidate = slugify(raw, allow_unicode=True)
        if not candidate:
            raise forms.ValidationError("آدرسِ وارد‌شده معتبر نیست.")
        qs = Product.objects.filter(store=self.store, slug=candidate)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("این آدرس قبلاً برای کالای دیگری استفاده شده است.")
        return candidate

    def clean_tags(self):
        from apps.core.utils import normalization_key

        raw = self.cleaned_data.get("tags") or ""
        names = []
        seen = set()
        for part in raw.split(","):
            name = part.strip()
            if not name:
                continue
            key = normalization_key(name)
            if key in seen:
                continue
            seen.add(key)
            names.append(name)
        return names

    def clean_weight_grams(self):
        raw = normalize_digits(self.cleaned_data.get("weight_grams", "")).strip()
        if not raw:
            return None
        try:
            value = int(raw)
        except ValueError:
            raise forms.ValidationError("وزن باید یک عدد صحیح باشد")
        if value < 0:
            raise forms.ValidationError("وزن نمی‌تواند منفی باشد")
        return value

    def clean_sku(self):
        sku = normalize_digits(self.cleaned_data["sku"]).strip()
        if not sku:
            raise forms.ValidationError("کد کالا الزامی است")
        qs = Product.objects.filter(store=self.store, sku=sku)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("این کد کالا قبلاً استفاده شده است")
        return sku

    def clean_category(self):
        category = self.cleaned_data["category"]
        if category.store_id != self.store.pk:
            raise forms.ValidationError("این دسته‌بندی متعلق به فروشگاه دیگری است")
        return category

    def clean_publish_at(self):
        from django.utils.dateparse import parse_datetime
        from django.utils.timezone import is_naive, make_aware

        raw = (self.cleaned_data.get("publish_at") or "").strip()
        if not raw:
            return None
        parsed = parse_datetime(raw)
        if parsed is None:
            raise forms.ValidationError("زمانِ انتشار معتبر نیست.")
        if is_naive(parsed):
            parsed = make_aware(parsed)
        return parsed

    def clean_price(self):
        # پیش‌نویس (دکمه‌ی «ذخیره‌ی پیش‌نویس») صراحتاً وعده می‌دهد که فقط
        # نام/کدِ کالا/دسته‌بندی الزامی‌اند؛ قیمت باید بتواند خالی بماند.
        # اعتبارسنجیِ واقعیِ «قیمت > ۰» پیش از انتشار همچنان توسط
        # ``validate_product_for_publish`` (وقتی status=active) اجرا می‌شود —
        # این‌جا الزامیِ بی‌قیدوشرط بودنِ قیمت با آن وعده در تضاد بود و باعث
        # می‌شد ذخیره‌ی پیش‌نویسِ بدونِ قیمت بی‌سروصدا شکست بخورد.
        if not self.data.get("price", "").strip() and self.data.get("status") == Product.Status.DRAFT:
            return 0
        return self._clean_int("price", min_value=1)

    def clean_discount_percent(self):
        if not self.data.get("discount_percent", "").strip():
            return 0
        return self._clean_int("discount_percent", min_value=0, max_value=100)

    def clean_stock(self):
        if not self.data.get("stock", "").strip():
            return 0
        return self._clean_int("stock", min_value=0)

    def clean_description(self):
        from apps.catalog.services.html_sanitizer import sanitize_product_description

        return sanitize_product_description(self.cleaned_data.get("description", ""))


class VariantBulkAddForm(NumericCleanMixin, forms.Form):
    """اعتبارسنجی ساختاری ورودی سریع تنوع؛ تجزیه و اعتبارسنجی کسب‌وکاری در سرویس تنوع انجام می‌شود."""

    attribute = forms.CharField(label="نام تنوع", max_length=60, help_text="مثلاً: رنگ، سایز، حجم، مدل")
    raw_values = forms.CharField(
        label="مقادیر تنوع", widget=forms.Textarea,
        help_text="هر مقدار را در یک خط، یا با کاما/سمیکالن از هم جدا کنید.",
    )
    default_stock = forms.CharField(label="موجودی پیش‌فرض", required=False, initial="0")
    default_extra_price = forms.CharField(label="تغییر قیمت پیش‌فرض (تومان)", required=False, initial="0")
    is_active = forms.BooleanField(label="فعال باشند", required=False, initial=True)

    def clean_attribute(self):
        attribute = self.cleaned_data["attribute"].strip()
        if not attribute:
            raise forms.ValidationError("نام تنوع نمی‌تواند خالی باشد")
        return attribute

    def clean_default_stock(self):
        if not self.data.get("default_stock", "").strip():
            return 0
        return self._clean_int("default_stock", min_value=0)

    def clean_default_extra_price(self):
        if not self.data.get("default_extra_price", "").strip():
            return 0
        return self._clean_decimal("default_extra_price")


class VariantEditForm(NumericCleanMixin, forms.Form):
    """اعتبارسنجی ساختاری ویرایش یک مقدار تنوع؛ یکتایی و نرمال‌سازی در سرویس تنوع انجام می‌شود."""

    attribute = forms.CharField(label="نام تنوع", max_length=60)
    value = forms.CharField(label="مقدار تنوع", max_length=60)
    sku = forms.CharField(label="کد کالا (SKU)", max_length=64, required=False)
    extra_price = forms.CharField(label="تغییر قیمت (تومان)", required=False, initial="0")
    stock = forms.CharField(label="موجودی", required=False, initial="0")
    is_active = forms.BooleanField(label="فعال", required=False)

    def clean_attribute(self):
        attribute = self.cleaned_data["attribute"].strip()
        if not attribute:
            raise forms.ValidationError("نام تنوع نمی‌تواند خالی باشد")
        return attribute

    def clean_value(self):
        value = self.cleaned_data["value"].strip()
        if not value:
            raise forms.ValidationError("مقدار تنوع نمی‌تواند خالی باشد")
        return value

    def clean_extra_price(self):
        if not self.data.get("extra_price", "").strip():
            return 0
        return self._clean_decimal("extra_price")

    def clean_stock(self):
        if not self.data.get("stock", "").strip():
            return 0
        return self._clean_int("stock", min_value=0)


class AttributeForm(forms.Form):
    """اعتبارسنجی ساختاری فرم ویژگی؛ یکتاییِ کد و سازگاری نوع داده/نمایش در سرویس ویژگی انجام می‌شود."""

    label = forms.CharField(label="عنوان نمایشی", max_length=120)
    code = forms.CharField(label="کد داخلی", max_length=60, required=False)
    description = forms.CharField(label="توضیحات", widget=forms.Textarea, required=False)
    data_type = forms.ChoiceField(label="نوع داده", choices=Attribute.DataType.choices)
    display_type = forms.ChoiceField(
        label="نوع نمایش", choices=[("", "—")] + list(Attribute.DisplayType.choices), required=False,
    )
    unit = forms.CharField(label="واحد", max_length=30, required=False)
    category = forms.ModelChoiceField(label="دسته‌بندی", queryset=Category.objects.none(), required=False)
    is_required = forms.BooleanField(label="الزامی", required=False)
    is_filterable = forms.BooleanField(label="قابل فیلتر", required=False)
    is_searchable = forms.BooleanField(label="قابل جست‌وجو", required=False)
    is_comparable = forms.BooleanField(label="قابل مقایسه", required=False)
    is_variant_axis = forms.BooleanField(label="واجد شرایط محور تنوع", required=False)
    is_image_driving = forms.BooleanField(label="تصویرمحور (سوییچِ خودکارِ تصویر)", required=False)

    def __init__(self, *args, store, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = Category.objects.filter(store=store).order_by("order", "name")

    def clean_label(self):
        label = self.cleaned_data["label"].strip()
        if not label:
            raise forms.ValidationError("عنوان نمایشی نمی‌تواند خالی باشد")
        return label


class BrandForm(forms.Form):
    """اعتبارسنجی ساختاری فرم برند؛ یکتاییِ اسلاگ و قاعده‌ی «حذف امن» در brand_service انجام می‌شود."""

    name = forms.CharField(label="نام برند (فارسی)", max_length=120)
    name_en = forms.CharField(label="نام انگلیسی (اختیاری)", max_length=120, required=False)
    description = forms.CharField(label="توضیح کوتاه", max_length=300, required=False, widget=forms.Textarea)
    website = forms.URLField(label="وب‌سایت (اختیاری)", max_length=300, required=False)
    country = forms.CharField(label="کشور (اختیاری)", max_length=80, required=False)
    logo = forms.ImageField(label="لوگو", required=False)

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if not name:
            raise forms.ValidationError("نام برند نمی‌تواند خالی باشد")
        return name


class CollectionForm(forms.Form):
    """اعتبارسنجی ساختاری فرم کالکشن؛ یکتاییِ اسلاگ در ``collection_service`` انجام می‌شود."""

    name = forms.CharField(label="نام کالکشن", max_length=150)
    description = forms.CharField(label="توضیحات (اختیاری)", required=False, widget=forms.Textarea)
    image = forms.ImageField(label="تصویر (اختیاری)", required=False)
    seo_title = forms.CharField(label="عنوان سئو (اختیاری)", max_length=70, required=False)
    seo_description = forms.CharField(label="توضیحات متا (اختیاری)", max_length=160, required=False, widget=forms.Textarea)

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if not name:
            raise forms.ValidationError("نام کالکشن نمی‌تواند خالی باشد")
        return name


class ProductQuickCategoryForm(forms.Form):
    """ساختِ سریعِ دسته‌بندی سه‌سطحی (گروه اصلی ← دسته ← زیرگروه نهایی) از
    داخلِ فرمِ کالا — هر مرحله یا یک گره‌ی موجود را انتخاب می‌کند یا نامِ
    تازه‌ای برایِ ساختِ آن می‌گیرد؛ مدیرِ فروشگاه هرگز برایِ همین یک کالا
    مجبور به ترکِ فرم نیست. کالا فقط به زیرگروهِ نهایی (برگ) وصل می‌شود."""

    group = forms.ModelChoiceField(label="گروه اصلی", queryset=Category.objects.none(), required=False)
    new_group_name = forms.CharField(label="نام گروهِ اصلیِ جدید", max_length=120, required=False)
    category = forms.ModelChoiceField(label="دسته", queryset=Category.objects.none(), required=False)
    new_category_name = forms.CharField(label="نام دسته‌ی جدید", max_length=120, required=False)
    sub_name = forms.CharField(label="نام زیرگروه نهایی", max_length=120)

    def __init__(self, *args, store, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["group"].queryset = Category.objects.filter(store=store, parent__isnull=True).order_by("order", "name")
        group_id = self.data.get("group") if self.is_bound else None
        if group_id:
            self.fields["category"].queryset = Category.objects.filter(
                store=store, parent_id=group_id,
            ).order_by("order", "name")
        else:
            self.fields["category"].queryset = Category.objects.none()

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("group") and not (cleaned.get("new_group_name") or "").strip():
            raise forms.ValidationError("یک گروهِ اصلیِ موجود را انتخاب کنید یا نامِ گروهِ جدید را وارد کنید")
        if not cleaned.get("category") and not (cleaned.get("new_category_name") or "").strip():
            raise forms.ValidationError("یک دسته‌ی موجود را انتخاب کنید یا نامِ دسته‌ی جدید را وارد کنید")
        if not (cleaned.get("sub_name") or "").strip():
            raise forms.ValidationError("نامِ زیرگروهِ نهایی الزامی است")
        return cleaned


class ProductQuickAttributeForm(forms.Form):
    """ساختِ سریعِ یک ویژگیِ متنی از داخلِ فرمِ کالا — تنظیماتِ پیشرفته‌تر
    (نوعِ داده، محورِ تنوع و...) همچنان فقط در صفحه‌ی ویژگی‌ها انجام می‌شود."""

    label = forms.CharField(label="عنوانِ ویژگی", max_length=120)

    def clean_label(self):
        label = self.cleaned_data["label"].strip()
        if not label:
            raise forms.ValidationError("عنوانِ ویژگی نمی‌تواند خالی باشد")
        return label


class AttributeValueForm(forms.Form):
    label = forms.CharField(label="برچسب", max_length=120)
    value = forms.CharField(label="مقدار داخلی", max_length=120, required=False)
    color_hex = forms.CharField(label="کد رنگ (Hex)", max_length=9, required=False)
    swatch_image = forms.ImageField(label="تصویر نمونه (اختیاری)", required=False)

    def clean_label(self):
        label = self.cleaned_data["label"].strip()
        if not label:
            raise forms.ValidationError("برچسب نمی‌تواند خالی باشد")
        return label


class ProductOptionForm(forms.Form):
    """اعتبارسنجی ساختاری فرم افزودن محور تنوع؛ اعتبارسنجی کسب‌وکاری در variant_engine_service است.

    ``input_type`` هرگز از کاربر پرسیده نمی‌شود (بدون فیلد «نوعِ ورودی»
    در UI) — به‌طور خودکار از رویِ اینکه آیا حداقل یک مقدارِ رنگ داده شده
    یا نه تشخیص داده می‌شود (نگاه کنید به ``color_values_json``/
    ``clean_color_values``)."""

    label = forms.CharField(label="نامِ ویژگی", max_length=60)
    raw_values = forms.CharField(
        label="مقادیر اولیه", widget=forms.Textarea, required=False,
        help_text="هر مقدار را در یک خط، یا با کاما/سمیکالن از هم جدا کنید.",
    )
    color_values_json = forms.CharField(
        label="مقادیرِ رنگ", widget=forms.HiddenInput, required=False,
        help_text="فهرستِ JSON از {label, color_hex} — از بخشِ «افزودنِ مقدارِ رنگ» ساخته می‌شود.",
    )

    def clean_label(self):
        label = self.cleaned_data["label"].strip()
        if not label:
            raise forms.ValidationError("عنوان محور نمی‌تواند خالی باشد")
        return label

    def clean_color_values_json(self):
        import json

        raw = self.cleaned_data.get("color_values_json", "").strip()
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
        except (ValueError, TypeError):
            raise forms.ValidationError("قالبِ مقادیرِ رنگ نامعتبر است")
        if not isinstance(parsed, list):
            raise forms.ValidationError("قالبِ مقادیرِ رنگ نامعتبر است")
        cleaned = []
        for item in parsed:
            if not isinstance(item, dict):
                continue
            label = str(item.get("label", "")).strip()
            color_hex = str(item.get("color_hex", "")).strip()
            if label and color_hex:
                cleaned.append({"label": label, "color_hex": color_hex})
        return cleaned


class ProductOptionValueAddForm(forms.Form):
    label = forms.CharField(label="برچسب مقدار", max_length=60)
    color_hex = forms.CharField(label="کد رنگ (Hex)", max_length=9, required=False)

    def clean_label(self):
        label = self.cleaned_data["label"].strip()
        if not label:
            raise forms.ValidationError("برچسب نمی‌تواند خالی باشد")
        return label


class CategoryAttributeAddForm(forms.Form):
    """اعتبارسنجی ساختاری فرم افزودن ویژگی به دسته‌بندی؛ اعتبارسنجی کسب‌وکاری در category_schema_service است."""

    attribute = forms.ModelChoiceField(label="ویژگی", queryset=Attribute.objects.none())
    group = forms.CharField(label="گروه/بخش", max_length=80, required=False)
    is_required = forms.BooleanField(label="الزامی", required=False)
    is_inherited_by_children = forms.BooleanField(
        label="به ارث برسد به زیردسته‌ها", required=False, initial=True,
    )
    help_text = forms.CharField(label="متن راهنما", max_length=300, required=False)
    placeholder = forms.CharField(label="متن جای‌گیر", max_length=120, required=False)

    def __init__(self, *args, store, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["attribute"].queryset = Attribute.objects.filter(store=store, is_active=True).order_by("label")


class MainCategoryForm(forms.Form):
    name = forms.CharField(label="نام گروه", max_length=120)
    icon = forms.CharField(label="آیکون (ایموجی)", max_length=10, required=False, initial="📁")
    image = forms.ImageField(label="تصویر دسته‌بندی", required=False)


class SubCategoryForm(forms.Form):
    parent = forms.ModelChoiceField(
        label="گروه والد", queryset=Category.objects.none(),
        error_messages={"required": "انتخاب گروه والد الزامی است"},
    )
    name = forms.CharField(label="نام زیرگروه", max_length=120)
    icon = forms.CharField(label="آیکون (ایموجی)", max_length=10, required=False)

    def __init__(self, *args, store, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["parent"].queryset = Category.objects.filter(
            store=store, parent__isnull=True
        ).order_by("order", "name")


class SubSubCategoryForm(forms.Form):
    """سومین و آخرین سطح از سلسله‌مراتب (گروه ← دسته ← زیردسته) — والد فقط
    می‌تواند یک «دسته» (سطحِ دوم، خودش زیرِ یک گروه) باشد، نه یک گروهِ
    ریشه و نه یک زیردسته‌ی دیگر؛ همین محدودیت عمقِ درخت را دقیقاً در سه
    سطح نگه می‌دارد."""

    parent = forms.ModelChoiceField(
        label="دسته‌ی والد", queryset=Category.objects.none(),
        error_messages={"required": "انتخاب دسته‌ی والد الزامی است"},
    )
    name = forms.CharField(label="نام زیردسته", max_length=120)
    icon = forms.CharField(label="آیکون (ایموجی)", max_length=10, required=False)

    def __init__(self, *args, store, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["parent"].queryset = Category.objects.filter(
            store=store, parent__isnull=False, parent__parent__isnull=True,
        ).order_by("parent__order", "order", "name")


class CategoryEditForm(forms.Form):
    name = forms.CharField(label="نام", max_length=120)
    icon = forms.CharField(label="آیکون (ایموجی)", max_length=10, required=False)
    image = forms.ImageField(label="تصویر دسته‌بندی", required=False)
    clear_image = forms.BooleanField(label="حذف تصویر", required=False)


class ShopInfoForm(forms.Form):
    name = forms.CharField(label="نام فروشگاه", max_length=150, widget=forms.TextInput(attrs={"class": "inp"}))
    tagline = forms.CharField(
        label="شعار فروشگاه", max_length=200, required=False, widget=forms.TextInput(attrs={"class": "inp"})
    )
    contact_phone = forms.CharField(
        label="شماره تماس", max_length=30, required=False,
        widget=forms.TextInput(attrs={"class": "inp", "dir": "ltr"}),
    )
    contact_email = forms.EmailField(
        label="ایمیل فروشگاه", required=False, widget=forms.EmailInput(attrs={"class": "inp", "dir": "ltr"})
    )
    contact_address = forms.CharField(
        label="آدرس", max_length=300, required=False,
        widget=forms.Textarea(attrs={"class": "inp", "rows": 2}),
    )
    description = forms.CharField(
        label="توضیحات فروشگاه", required=False, widget=forms.Textarea(attrs={"class": "inp", "rows": 3})
    )


class FinanceSettingsForm(NumericCleanMixin, forms.Form):
    tax_percent = forms.CharField(label="نرخ مالیات (٪)", widget=forms.TextInput(attrs={"class": "inp"}))
    free_shipping_threshold = forms.CharField(
        label="آستانه‌ی ارسال رایگان (تومان)", widget=forms.TextInput(attrs={"class": "inp"})
    )

    def clean_tax_percent(self):
        return self._clean_decimal("tax_percent", min_value=0, max_value=100)

    def clean_free_shipping_threshold(self):
        return self._clean_int("free_shipping_threshold", min_value=0)


class GiftWrapSettingsForm(NumericCleanMixin, forms.Form):
    """کادوپیچی — افزونه‌ی اختیاریِ سبد خرید (toranj_gifting و هر خانواده‌ی
    دیگری که این کنترل را نمایش دهد). مستقل از خانواده‌ی بصریِ فروشگاه؛
    مدیرِ هر Storeای می‌تواند این را روشن/خاموش کند."""

    gift_wrap_available = forms.BooleanField(label="کادوپیچی در دسترس است", required=False)
    gift_wrap_price = forms.CharField(
        label="هزینه‌ی کادوپیچی (تومان؛ ۰ = رایگان)", widget=forms.TextInput(attrs={"class": "inp"})
    )
    gift_wrap_pricing_scope = forms.ChoiceField(
        label="مبنای محاسبه‌ی هزینه", choices=ShopSettings.GiftWrapScope.choices, required=False,
        initial=ShopSettings.GiftWrapScope.PER_UNIT, widget=forms.Select(attrs={"class": "inp"}),
    )
    gift_wrap_title = forms.CharField(
        label="عنوان سرویس", max_length=80, required=False, widget=forms.TextInput(attrs={"class": "inp"}),
    )
    gift_wrap_description = forms.CharField(
        label="توضیح سرویس", max_length=300, required=False, widget=forms.TextInput(attrs={"class": "inp"}),
    )
    gift_wrap_message_enabled = forms.BooleanField(label="امکان نوشتن پیام کارت هدیه", required=False)
    gift_wrap_image = forms.ImageField(label="تصویر نمونه", required=False)
    remove_gift_wrap_image = forms.BooleanField(label="حذف تصویر فعلی", required=False)

    def clean_gift_wrap_price(self):
        return self._clean_int("gift_wrap_price", min_value=0)

    def clean_gift_wrap_title(self):
        return self.cleaned_data.get("gift_wrap_title", "").strip() or "کادوپیچی"


class SmsConnectionForm(forms.Form):
    """تنظیماتِ پیامکِ قابلِ‌مشاهده‌یِ Store — زیرساختِ ارسال (ارائه‌دهنده،
    کلیدِ API، شماره‌ی فرستنده) دیگر اینجا نیست؛ آن‌ها فقط از Platform Admin
    پیکربندی می‌شوند (نگاه کنید به ``apps.portal.forms.PlatformConfigurationForm``).
    تنها انتخابِ باقی‌مانده برایِ Store این است که از درگاهِ مرکزیِ پلتفرم
    استفاده کند (پیش‌فرض) یا گیت‌وی اندرویدِ اختصاصیِ خودش (SmsRasti) را
    به‌جایِ آن به‌کار ببرد — چون آن دستگاه، برخلافِ بقیه، متعلق به خودِ
    Store است، نه زیرساختِ پلتفرم."""

    sms_enabled = forms.BooleanField(label="فعال‌سازی سیستم پیامک", required=False)
    sms_backend = forms.ChoiceField(
        label="روشِ ارسال",
        choices=[
            (ShopSettings.SmsBackend.CONSOLE, "درگاهِ مرکزیِ پلتفرم (پیش‌فرض)"),
            (ShopSettings.SmsBackend.SMSRASTI, "دستگاهِ اسمس‌راستیِ اختصاصیِ من (پیشرفته)"),
        ],
        widget=forms.Select(attrs={"class": "inp"}),
    )


class SmsPackagePurchaseForm(forms.Form):
    package_id = forms.IntegerField(widget=forms.HiddenInput)


class SmsTemplateForm(forms.Form):
    body = forms.CharField(label="متن قالب", widget=forms.Textarea(attrs={"class": "inp", "rows": 4}))

    def __init__(self, *args, event_key=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.event_key = event_key

    def clean_body(self):
        body = self.cleaned_data["body"].strip()
        try:
            validate_template_body(self.event_key, body)
        except SmsTemplateError as exc:
            raise forms.ValidationError(str(exc)) from exc
        return body
        return body


class SmsTestForm(forms.Form):
    phone = forms.CharField(label="شماره موبایل گیرنده‌ی آزمایشی", max_length=15, widget=forms.TextInput(attrs={"class": "inp", "dir": "ltr"}))

    def clean_phone(self):
        phone = normalize_digits(self.cleaned_data["phone"]).strip()
        if not PHONE_RE.match(phone):
            raise forms.ValidationError("شماره موبایل معتبر نیست (مثال: 09123456789)")
        return phone


class MultiFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultiImageField(forms.FileField):
    """فیلد آپلود چندتایی — الگوی مستندشده‌ی Django برای FileField چندفایلی."""

    widget = MultiFileInput

    def clean(self, data, initial=None):
        single_file_clean = super().clean
        if isinstance(data, (list, tuple)):
            return [single_file_clean(item, initial) for item in data]
        return single_file_clean(data, initial)


class ProductImageUploadForm(forms.Form):
    images = MultiImageField(
        label="تصاویر", required=False, widget=MultiFileInput(attrs={"multiple": True, "accept": ".jpg,.jpeg,.png,.webp"})
    )


class ProductImageAltForm(forms.Form):
    alt = forms.CharField(label="متن جایگزین", max_length=200, required=False)



# --- هویت بصری ---

HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")

ALLOWED_LOGO_TYPES = {"image/png", "image/jpeg", "image/webp"}
ALLOWED_FAVICON_TYPES = {"image/png", "image/x-icon", "image/vnd.microsoft.icon"}
MAX_LOGO_SIZE = 2 * 1024 * 1024  # 2 MB
MAX_FAVICON_SIZE = 512 * 1024  # 512 KB


def _validate_hex_color(value):
    """اعتبارسنجی رنگ هگزادسیمال #RRGGBB — فقط مقادیر امن."""
    value = value.strip()
    if not HEX_COLOR_RE.match(value):
        raise forms.ValidationError("رنگ باید به فرمت #RRGGBB باشد (مثال: #6D28D9)")
    return value.upper()


def _validate_image_upload(file, allowed_types, max_size, label):
    """اعتبارسنجی فایل تصویر: نوع، اندازه، و محتوای واقعی."""
    if file.size > max_size:
        max_mb = max_size / (1024 * 1024)
        raise forms.ValidationError(f"حجم {label} نباید بیشتر از {max_mb:.0f} مگابایت باشد")

    if file.content_type not in allowed_types:
        raise forms.ValidationError(f"فرمت {label} معتبر نیست. فرمت‌های مجاز: PNG, JPEG, WebP")

    # Verify actual image content
    try:
        from PIL import Image
        img = Image.open(file)
        img.verify()
        file.seek(0)
    except Exception:
        raise forms.ValidationError(f"فایل {label} یک تصویر معتبر نیست")

    return file


def _color_field(label, required=False):
    return forms.CharField(
        label=label, max_length=7, required=required,
        widget=forms.TextInput(attrs={"class": "inp", "type": "color", "style": "width:60px;height:40px;padding:4px"}),
    )


class VisualIdentityForm(forms.Form):
    """فرم هویت بصری فروشگاه: لوگو، فاوآیکون و توکن‌های رنگی تم.

    ``primary_color``/``accent_color`` همیشه اجباری‌اند (سازگاری با فرم قدیمی).
    توکن‌های جدید تم (ثانویه، پس‌زمینه، سطح، متن، متن کم‌رنگ) اختیاری‌اند — اگر
    ارسال نشوند، مقدار فعلی/پیش‌فرض فروشگاه دست‌نخورده می‌ماند (view تصمیم می‌گیرد).
    """

    logo = forms.ImageField(label="لوگوی فروشگاه", required=False)
    remove_logo = forms.BooleanField(label="حذف لوگوی فعلی", required=False)

    favicon = forms.ImageField(label="فاوآیکون", required=False)
    remove_favicon = forms.BooleanField(label="حذف فاوآیکون فعلی", required=False)

    primary_color = _color_field("رنگ اصلی", required=True)
    accent_color = _color_field("رنگ مکمل", required=True)
    secondary_color = _color_field("رنگ ثانویه")
    background_color = _color_field("رنگ پس‌زمینه‌ی صفحه")
    surface_color = _color_field("رنگ پس‌زمینه‌ی کارت‌ها")
    text_color = _color_field("رنگ متن اصلی")
    muted_text_color = _color_field("رنگ متن کم‌رنگ")

    def __init__(self, *args, current_shop=None, **kwargs):
        """``current_shop`` مقادیر فعلیِ فیلدهای ارسال‌نشده را برای بررسی کنتراست کامل می‌کند."""
        self._current_shop = current_shop
        super().__init__(*args, **kwargs)

    def clean_primary_color(self):
        return _validate_hex_color(self.cleaned_data["primary_color"])

    def clean_accent_color(self):
        return _validate_hex_color(self.cleaned_data["accent_color"])

    def _clean_optional_color(self, field_name):
        value = self.cleaned_data.get(field_name, "").strip()
        if not value:
            return ""
        return _validate_hex_color(value)

    def clean_secondary_color(self):
        return self._clean_optional_color("secondary_color")

    def clean_background_color(self):
        return self._clean_optional_color("background_color")

    def clean_surface_color(self):
        return self._clean_optional_color("surface_color")

    def clean_text_color(self):
        return self._clean_optional_color("text_color")

    def clean_muted_text_color(self):
        return self._clean_optional_color("muted_text_color")

    def clean_logo(self):
        logo = self.cleaned_data.get("logo")
        if logo:
            return _validate_image_upload(logo, ALLOWED_LOGO_TYPES, MAX_LOGO_SIZE, "لوگو")
        return logo

    def clean_favicon(self):
        favicon = self.cleaned_data.get("favicon")
        if favicon:
            return _validate_image_upload(favicon, ALLOWED_FAVICON_TYPES, MAX_FAVICON_SIZE, "فاوآیکون")
        return favicon

    def clean(self):
        """کنتراست متن اصلی/کم‌رنگ در برابر پس‌زمینه و سطح را روی ترکیب نهایی (نه فقط فیلدهای تازه) بررسی می‌کند."""
        cleaned = super().clean()
        if self.errors:
            return cleaned

        shop = self._current_shop
        text = cleaned.get("text_color") or (safe_hex(shop.text_color, "#241C3A") if shop else "#241C3A")
        background = cleaned.get("background_color") or (safe_hex(shop.background_color, "#F7F5FC") if shop else "#F7F5FC")
        surface = cleaned.get("surface_color") or (safe_hex(shop.surface_color, "#FFFFFF") if shop else "#FFFFFF")
        muted = cleaned.get("muted_text_color") or (safe_hex(shop.muted_text_color, "#8B86A3") if shop else "#8B86A3")

        failures = []
        if contrast_ratio(text, background) < 4.5:
            failures.append("رنگ متن اصلی در برابر پس‌زمینه‌ی صفحه خوانا نیست (کنتراست کمتر از ۴.۵)")
        if contrast_ratio(text, surface) < 4.5:
            failures.append("رنگ متن اصلی در برابر پس‌زمینه‌ی کارت‌ها خوانا نیست (کنتراست کمتر از ۴.۵)")
        if contrast_ratio(muted, surface) < 3.0:
            failures.append("رنگ متن کم‌رنگ در برابر پس‌زمینه‌ی کارت‌ها خوانا نیست (کنتراست کمتر از ۳)")

        if failures:
            raise forms.ValidationError(failures)
        return cleaned
