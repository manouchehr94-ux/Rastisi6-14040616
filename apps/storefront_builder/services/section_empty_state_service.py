"""قرارداد یکپارچه‌ی «حالت خالی» برای بخش‌هایِ داده‌محور.

قانون مالک: قالبِ آماده تعیین می‌کند چه بخش‌هایی *وجود دارند*؛ داده‌ی فروشگاه فقط
تعیین می‌کند آن بخش‌ها *چه نشان می‌دهند*. نبودِ برند/کالا/دسته/مقاله/بنر هرگز
باعثِ حذفِ بخش نمی‌شود:

* در استودیو، همان بخش با یک پیامِ فارسیِ روشن و لینک به همان مدیریتِ موجود
  نمایش داده می‌شود (مثلاً «فروشگاه شما هنوز برندی تعریف نکرده است.»)؛
* در ویترین عمومی، همان بخش با یک نمایشِ مؤدب و غیرمدیریتی می‌ماند — بدونِ هیچ
  دستورِ ادمین و بدونِ داده‌ی ساختگی (کالا/لوگو/قیمتِ جعلی هرگز ساخته نمی‌شود).

این تنها نقطه‌ی تصمیم است؛ هیچ رندرر یا CSS مخصوصِ یک قالب وجود ندارد. وقتی
مرچنت داده‌ی واقعی اضافه کند، *همان* بخش خودکار آن را نشان می‌دهد (چیزی دوباره
نصب نمی‌شود).
"""

import dataclasses

from django.urls import NoReverseMatch, reverse


@dataclasses.dataclass(frozen=True)
class EmptyStateSpec:
    kind: str
    context_keys: tuple
    default_title: str
    studio_message: str
    studio_hint: str
    public_note: str
    action_label: str = ""
    action_url_name: str = ""
    #: True = the section has no shell of its own when empty, so the shared empty state replaces its body at the wrapper.
    #: False = the section keeps its own shell (heading, campaign panel, presentation attributes) and renders the shared
    #: empty-state body INSIDE its grid/slot (``context["empty_state"]``).
    replace_section: bool = True


_SPECS = {
    "brand_carousel": EmptyStateSpec(
        kind="brand", context_keys=("brands",), default_title="برندها",
        studio_message="فروشگاه شما هنوز برندی تعریف نکرده است.",
        studio_hint="با افزودن برند، همین بخش به‌صورت خودکار پر می‌شود؛ نیازی به نصب دوباره‌ی قالب نیست.",
        public_note="برندهای همکار ما به‌زودی در این بخش نمایش داده می‌شوند.",
        action_label="مدیریت برندها", action_url_name="dashboard:brand-list",
    ),
    "category_grid": EmptyStateSpec(
        kind="category", context_keys=("top_categories",), default_title="دسته‌بندی‌ها",
        studio_message="فروشگاه شما هنوز دسته‌بندی‌ای تعریف نکرده است.",
        studio_hint="با افزودن دسته‌بندی، همین بخش به‌صورت خودکار پر می‌شود.",
        public_note="دسته‌بندی‌های فروشگاه به‌زودی در این بخش نمایش داده می‌شوند.",
        action_label="مدیریت دسته‌بندی‌ها", action_url_name="dashboard:category-list",
    ),
    "blog_posts": EmptyStateSpec(
        kind="blog", context_keys=("posts",), default_title="مجله",
        studio_message="هنوز مقاله‌ای برای نمایش در این بخش منتشر نشده است.",
        studio_hint="با انتشار مقاله، همین بخش به‌صورت خودکار پر می‌شود.",
        public_note="مقالات به‌زودی در این بخش منتشر می‌شوند.",
    ),
    "collection_tiles": EmptyStateSpec(
        kind="collection", context_keys=("collection_tiles",), default_title="کالکشن‌ها",
        studio_message="فروشگاه شما هنوز کالکشنی تعریف نکرده است.",
        studio_hint="با ساخت کالکشن، همین بخش به‌صورت خودکار پر می‌شود.",
        public_note="کالکشن‌های فروشگاه به‌زودی در این بخش نمایش داده می‌شوند.",
        action_label="مدیریت کالکشن‌ها", action_url_name="dashboard:collection-list",
    ),
    "multi_banner": EmptyStateSpec(
        kind="banner", context_keys=("banners",), default_title="پیشنهادها",
        studio_message="برای این بخش هنوز بنری انتخاب نشده است.",
        studio_hint="بنر را از همین بخش (پنل «رسانه» در Inspector) اضافه کنید، یا بنرهای مشترک فروشگاه را بسازید تا همهٔ قالب‌ها از آن‌ها استفاده کنند.",
        public_note="پیشنهادهای ویژه به‌زودی در این بخش نمایش داده می‌شوند.",
        action_label="بنرهای مشترک فروشگاه", action_url_name="dashboard:banner-list",
    ),
    "single_banner": EmptyStateSpec(
        kind="banner", context_keys=("banners",), default_title="پیشنهاد ویژه",
        studio_message="برای این بخش هنوز بنری انتخاب نشده است.",
        studio_hint="بنر را از همین بخش (پنل «رسانه» در Inspector) اضافه کنید، یا بنرهای مشترک فروشگاه را بسازید تا همهٔ قالب‌ها از آن‌ها استفاده کنند.",
        public_note="پیشنهاد ویژه به‌زودی در این بخش نمایش داده می‌شود.",
        action_label="بنرهای مشترک فروشگاه", action_url_name="dashboard:banner-list",
    ),
    "story_rail": EmptyStateSpec(
        kind="story", context_keys=("story_items",), default_title="استوری‌ها",
        studio_message="برای این بخش هنوز استوری‌ای افزوده نشده است.",
        studio_hint="با افزودن آیتم، همین بخش به‌صورت خودکار پر می‌شود.",
        public_note="استوری‌ها به‌زودی در این بخش نمایش داده می‌شوند.",
    ),
    "catalog_product_wall": EmptyStateSpec(
        kind="product", context_keys=("catalog_product_wall_groups",), default_title="محصولات",
        studio_message="هنوز کالایی برای نمایش در این بخش وجود ندارد.",
        studio_hint="با افزودن کالا (یا دسته‌بندی/کالکشن)، همین بخش به‌صورت خودکار پر می‌شود.",
        public_note="محصولات به‌زودی در این بخش نمایش داده می‌شوند.",
        action_label="مدیریت محصولات", action_url_name="dashboard:product-list",
    ),
}

_PRODUCT_INLINE_SPEC = EmptyStateSpec(
    kind="product", context_keys=("products",), default_title="محصولات", replace_section=False,
    studio_message="هنوز کالایی برای نمایش در این بخش وجود ندارد.",
    studio_hint="با افزودن کالای واجد شرایط (موجود و منتشرشده)، همین بخش به‌صورت خودکار پر می‌شود.",
    public_note="محصولات این بخش به‌زودی اضافه می‌شوند.",
    action_label="مدیریت محصولات", action_url_name="dashboard:product-list",
)
_PRODUCT_SPEC = EmptyStateSpec(
    kind="product", context_keys=("products",), default_title="محصولات",
    studio_message="هنوز کالایی برای نمایش در این بخش وجود ندارد.",
    studio_hint="با افزودن کالای واجد شرایط (موجود و منتشرشده)، همین بخش به‌صورت خودکار پر می‌شود.",
    public_note="محصولات این بخش به‌زودی اضافه می‌شوند.",
    action_label="مدیریت محصولات", action_url_name="dashboard:product-list",
)
for _key in ("product_section", "featured_products", "newest_products", "best_sellers", "discounted_products"):
    _SPECS[_key] = _PRODUCT_INLINE_SPEC
_SPECS["amazing_offers"] = _PRODUCT_SPEC  # no shell of its own when empty -> replaced at the wrapper


def _is_empty(value) -> bool:
    if value is None:
        return True
    from django.db.models import QuerySet

    if isinstance(value, QuerySet):
        # len() evaluates AND caches the result on this same object, so the template that iterates it later does not
        # issue a second query (an ``exists()`` here would).
        return len(value) == 0
    return not value


def spec_for(section_key):
    return _SPECS.get(section_key)


def resolve(item: dict):
    """اگر بخشِ این آیتم داده‌محور و *الان* خالی است، یک dict برای قالب برمی‌گرداند
    (وگرنه ``None``). هیچ نوشتن/کوئریِ اضافه‌ای جز ``exists()`` روی QuerySetهای
    خالی انجام نمی‌شود."""
    section = item.get("section")
    spec = spec_for(getattr(section, "section_key", None))
    if spec is None:
        return None
    context = item.get("context") or {}
    if not all(_is_empty(context.get(key)) for key in spec.context_keys):
        return None
    campaign = context.get("campaign")
    if isinstance(campaign, dict) and campaign.get("enabled"):
        # A campaign band's panel (copy / call to action) is merchant-authored content, not product data: the
        # section is not "empty" and must keep rendering its own panel.
        return None
    settings = context.get("settings") or {}
    action_url = ""
    if spec.action_url_name:
        try:
            action_url = reverse(spec.action_url_name)
        except NoReverseMatch:
            action_url = ""
    return {
        "kind": spec.kind,
        "title": settings.get("title") or spec.default_title,
        "studio_message": spec.studio_message,
        "studio_hint": spec.studio_hint,
        "public_note": spec.public_note,
        "action_label": spec.action_label,
        "action_url": action_url,
        "replace_section": spec.replace_section,
    }
