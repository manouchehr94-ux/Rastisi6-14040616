# DATA_MAPPING — نگاشت داده‌های دو فروشگاه

> این سند «قرارداد bundle» و نگاشت از منبع قدیمی به نصب تازه را شرح می‌دهد. چون داده‌ی اصلی در Git نیست ([`MISSING_INPUTS.md`](MISSING_INPUTS.md))، هر ردیف «چه چیزی، از کجا، به کجا» را تعریف می‌کند، نه اینکه ادعا کند وارد شده است.

## ۱. هویت دو فروشگاه (منبع حقیقت: `rebuild/manifests/demo_stores.json`)

| کلید bundle | slug مقصد | `admin_subdomain` | Host عمومی و مدیریتی | نام |
|---|---|---|---|---|
| `demo_v5` | `demo-v5` | `demo-v5` | `demo-v5.rastisi.ir` (`StoreDomain` اصلی، `platform_subdomain`، verified) | RastiSi Demo V5 |
| `demo_arch02` | `demo-arch02` | `demo-arch02` | `demo-arch02.rastisi.ir` | RastiSi Demo ARCH-02 |

- مسیر مدیریت هر فروشگاه: `https://<host>/admin-portal/` (همان الگوی موجود: `admin_subdomain.<RASTISI_ADMIN_DOMAIN_SUFFIX>`)؛ هیچ زیردامنه یا مسیر تازه‌ای ساخته نشد.
- Store با `status=active` و `onboarding_completed_at` پر ساخته می‌شود تا فروشگاه عمومی باشد (`publication_service`).
- نام/slug قبلی فروشگاه روی سرور قدیمی اهمیتی ندارد؛ هنگام export با `--store <slug-قدیمی>=demo_v5` به کلید نگاشت می‌شود.
- مقدارهای «`reported_previous_deployment`» در همان JSON (۵۰ محصول، ۱۵۰/۱۵۱ تصویر، ۴۲/۸۴ صفحه، ۱۷۲/۱۶۳ فایل رسانه) فقط **انتظار هشداری** هستند: اگر bundle متفاوت باشد validator `WARN` می‌دهد (`--strict-expected` آن را `FAIL` می‌کند). مدرک وجود فایل نیستند.

## ۲. ساختار bundle

```
bundle/
  manifest.json                    format=rastisi-store-bundle, version=1, شمارش هر مدل، sha256+size هر فایل رسانه
  stores/demo_v5/store.json        هویت فروشگاه منبع (اطلاعاتی)
  stores/demo_v5/data.json         ردیف‌های سریالایز‌شده‌ی Django (به ترتیب جدول ۳)
  stores/demo_arch02/…
  media/<مسیر نسبت به MEDIA_ROOT>  مثل products/gallery/x.jpg
```

## ۳. دامنه‌ی مدل‌ها و مسیر مالکیت (`contract.MODEL_SPECS`)

ردیف به فروشگاه تعلق دارد اگر یکی از مسیرهای ORM زیر به آن Store برسد.

| مدل | مسیر مالکیت | فایل‌ها |
|---|---|---|
| `orders.TaxClass` | `store` | — |
| `orders.TaxRate` | `store` | — |
| `catalog.Vendor` | `store` | logo |
| `catalog.Category` | `store` | image |
| `catalog.Brand` | `store` | logo |
| `catalog.ProductTag` | `store` | — |
| `catalog.Attribute` | `store` | — |
| `catalog.AttributeValue` | `attribute__store` | swatch_image |
| `catalog.Warehouse` | `store` | — |
| `catalog.Product` | `store` | — |
| `catalog.ProductVariant` | `store` | — |
| `catalog.ProductOption` | `product__store` | — |
| `catalog.ProductOptionValue` | `option__product__store` | — |
| `catalog.VariantOptionValue` | `variant__store` | — |
| `catalog.ProductImage` | `product__store` | image, thumbnail |
| `catalog.ProductVideo` | `product__store` | — |
| `catalog.ProductAttributeValue` | `product__store` | — |
| `catalog.ProductMetafield` | `product__store` | — |
| `catalog.Specification` | `product__store` | — |
| `catalog.WarehouseInventory` | `store` | — |
| `catalog.MerchantCollection` | `store` | image |
| `catalog.MerchantCollectionItem` | `collection__store` | — |
| `content.ContentPage` | `store` | — |
| `content.MediaAsset` | `store` | image |
| `content.Menu` | `store` | — |
| `content.MenuItem` | `menu__store` | — |
| `content.SocialLink` | `store` | — |
| `content.FooterSettings` | `store` | — |
| `content.FooterTrustBadge` | `store` | image |
| `content.FooterPaymentLogo` | `store` | image |
| `storefront_builder.StorefrontLayout` | `store` | — |
| `storefront_builder.StorefrontLayoutVersion` | `layout__store` | — |
| `storefront_builder.StorefrontPage` | `version__layout__store` | — |
| `storefront_builder.StorefrontContainer` | `page__version__layout__store` | — |
| `storefront_builder.StorefrontCell` | `container__page__version__layout__store` | — |
| `storefront_builder.StorefrontSection` | `page__version__layout__store` | — |
| `content.HeroSlide` | `store` یا `section__page__version__layout__store` | desktop_image, mobile_image |
| `content.PromotionalBanner` | `store` یا مسیر section | desktop_image, mobile_image |
| `content.StoryRailItem` | `store` یا مسیر section | image |
| `core.ShopSettings` | `store` | gift_wrap_image, logo, favicon |

### نگاشت به خواسته‌های دستور کار

| خواسته | کجا نگه‌داری می‌شود |
|---|---|
| محصولات، دسته‌بندی، مشخصات، تصاویر | `Product`, `Category`, `Brand`, `Specification`, `ProductAttributeValue`, `ProductImage` (+ thumbnail) و واریانت/گزینه‌ها |
| قالب و تم اصلی، رنگ‌ها، فونت | `StorefrontLayoutVersion.appearance_config` (+ `ShopSettings.primary_color/…`)؛ فونت به‌صورت نام خانواده (`Vazirmatn`, `Tahoma`, …) ذخیره می‌شود، فایل فونت جدا نیست |
| هدر / فوتر | `StorefrontLayoutVersion.header_config/footer_config` و `FooterSettings`, `FooterTrustBadge`, `FooterPaymentLogo`, `Menu/MenuItem`, `SocialLink` |
| لوگو و favicon | `ShopSettings.logo/favicon` |
| بنر، اسلایدر، استوری | `HeroSlide`, `PromotionalBanner`, `StoryRailItem` (+ `MediaAsset`) |
| نسخه‌های منتشرشده و پیش‌نویس Studio | `StorefrontLayout.published_version/draft_version` + همه‌ی `StorefrontLayoutVersion` (draft/published/archived) |
| صفحات خانه/جزئیات/فهرست/مجموعه/جست‌وجو/سبد | `StorefrontPage.page_type ∈ {home, product_detail, listing, collection, search, cart}` در هر نسخه (validator: نسخه‌ی منتشرشده باید هر شش را داشته باشد) |
| تنظیمات اختصاصی فروشگاه | `ShopSettings`, `FooterSettings`, `TaxClass/TaxRate`, `Warehouse(+Inventory)` |

## ۴. قواعد تبدیل هنگام import

1. **کلیدهای اصلی حفظ می‌شوند.** تنظیمات Section/Header/Footer در JSON به `product_ids`, `category_ids`, `brand_ids`, `collection_ids`, `menu_id`, `media_asset_id`, `image_media_asset_id`, `campaign_media_asset_id` با عدد ارجاع می‌دهند؛ شماره‌گذاری مجدد طرح‌ها را بی‌صدا می‌شکند. نتیجه (**محدودیت کلید اصلی**): ردیف‌های دو فروشگاه یک bundle باید کلید متمایز داشته باشند؛ یعنی هر دو را از **یک** دیتابیس منبع export کنید. اگر دو دیتابیس جدا با کلیدهای هم‌پوشان باشند validator با `pk.collision` متوقف می‌کند (هیچ remap حدسی انجام نمی‌شود). روی PostgreSQL پس از import، sequenceها reset می‌شوند.
2. FK به `Store` به Store مقصد بازنویسی می‌شود. FK به خارج از دامنه (کاربر، `IndustryTemplate*`) در export و دوباره در import `NULL` می‌شود (شمارش در `manifest.nulled_outside_references`).
3. **اسرار حذف می‌شوند:** ستون‌های `melipayamak_*`, `kavenegar_api_key`, `smsrasti_device_token` از `ShopSettings` و هر فیلدی با نام شامل `password|secret|token|api_key|credential` هرگز صادر نمی‌شوند؛ validator هر bundle را که مقدار غیرخالی چنین ستونی داشته باشد رد می‌کند (`secret.in_bundle`). تنظیمات پیامک پس از نصب باید دوباره وارد شود.
4. **ShopSettings / FooterSettings دقیقاً یکی:** اگر در bundle باشند همان‌ها (با رنگ‌ها و لوگو) وارد می‌شوند؛ اگر نباشند validator `BLOCKED (singleton.missing)` می‌دهد و import بدون `--allow-blocked singleton.missing` انجام نمی‌شود. حتی با آن، فقط `provision_for` خالی ساخته می‌شود و در گزارش `MISSING SOURCE` می‌ماند (هرگز از فروشگاه دیگری کپی نمی‌شود). singletonهای موجود با pk متفاوت روی همان ردیف نگاشت می‌شوند و FKهای وابسته (مثلاً `layout`) بازنویسی می‌شوند.
5. **Idempotent:** ذخیره‌ی خام (مثل `loaddata`) بر اساس pk داخل یک تراکنش؛ اجرای دوم هیچ ردیف/فایل تازه‌ای نمی‌سازد. `--prune` ردیف‌های همان فروشگاه را که در bundle نیستند حذف می‌کند (فقط با درخواست صریح).
6. **حفاظت tenant:** اگر pk موجود در DB متعلق به فروشگاه دیگری باشد، کل import (شامل Store/Domain) rollback می‌شود (`tenant.pk_conflict`).
7. **رسانه:** مسیرها نسبت به `MEDIA_ROOT` و با رد `..`/مطلق/backslash؛ هر فایل با sha256 بازبینی می‌شود؛ فایل موجود با محتوای متفاوت هرگز بازنویسی نمی‌شود (`media.conflict` → abort). تصاویر با Pillow decode می‌شوند.
8. `save()` سفارشی مدل‌ها و signalهای قیمت‌گذاری در حالت خام اجرا نمی‌شوند (`LayoutVersion.save` در حالت عادی شش صفحه‌ی خودکار می‌سازد که با صفحات bundle هم‌پوشان می‌شد)؛ برای همین `apps/catalog/signals.py` اکنون `raw=True` را نادیده می‌گیرد (رفتار معمول `loaddata`، تغییری برای مسیر عادی ندارد).

## ۵. آنچه عمداً منتقل نمی‌شود

کاربران و رمزها، مشتریان، آدرس‌ها، سبدها، سفارش‌ها/پرداخت‌ها/مرجوعی، SMS/اعلان‌ها/کمپین، اشتراک و صورتحساب، لاگ‌های حسابرسی، تاریخچه‌ی ویرایش Studio (`StorefrontEditHistoryEntry`)، نشست‌ها. (دموها داده‌ی مشتری واقعی ندارند؛ با افزودن مدل‌ها به `contract.MODEL_SPECS` می‌توان دامنه را گسترش داد.)

## ۶. حساب‌ها (نصب، نه import)

`create_install_accounts`: `platform_owner` (superuser+staff) و `shops_admin` (غیر staff؛ `OWNER` فعال هر دو فروشگاه). رمز فقط با `getpass` یا نام متغیر محیطی؛ هرگز آرگومان خط فرمان. جزئیات: [`SECURITY_NOTES.md`](SECURITY_NOTES.md).
