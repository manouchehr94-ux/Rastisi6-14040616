"""رگرسیونِ نمایشِ ویدیوهای کالا در صفحه‌ی عمومیِ محصول — ریشه‌ی باگ:
``build_product_detail_context`` هرگز ``product.videos`` را در کانتکست
نمی‌گذاشت، پس ویدیوهایی که در ادمین با موفقیت ذخیره شده بودند، هرگز در
فروشگاه رندر نمی‌شدند — نگاه کنید به apps.catalog.views.build_product_detail_context
و apps.catalog.templates.catalog.product_detail.html (بخشِ «ویدئوهای محصول»)."""

from decimal import Decimal

from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.db import connection
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Category, Product, ProductVideo, Vendor
from apps.stores.models import Store, StoreDomain

VIDEO_HOST = "video-isolation.example.com"


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


def _verified_domain(store, hostname):
    return StoreDomain.objects.create(
        store=store, hostname=hostname, is_primary=True,
        verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
    )


class ProductDetailVideoTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-pdp-video")
        self.category = Category.objects.create(store=self.store, name="دسته", slug="cat-pdp-video")
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="کالای ویدیودار",
            slug="video-product", sku="SKU-VID1", price=Decimal("100000"),
        )
        self.url = reverse("catalog:product-detail", args=[self.product.slug])

    def test_no_videos_shows_no_video_section(self):
        response = self.client.get(self.url)
        self.assertNotContains(response, "ویدئوهای محصول")
        self.assertNotContains(response, "pdp-video-card")

    def test_youtube_video_renders_safe_embed_iframe(self):
        ProductVideo.objects.create(
            product=self.product, provider=ProductVideo.Provider.YOUTUBE,
            url="https://www.youtube.com/watch?v=dQw4w9WgXcQ", title="معرفی",
        )
        response = self.client.get(self.url)
        self.assertContains(response, "ویدئوهای محصول")
        self.assertContains(response, "https://www.youtube.com/embed/dQw4w9WgXcQ")
        self.assertContains(response, "allowfullscreen")
        self.assertContains(response, "معرفی")
        self.assertContains(response, "یوتیوب")

    def test_youtube_shorts_and_short_link_construct_correct_embed_url(self):
        ProductVideo.objects.create(
            product=self.product, provider=ProductVideo.Provider.YOUTUBE,
            url="https://www.youtube.com/shorts/dQw4w9WgXcQ", display_order=0,
        )
        ProductVideo.objects.create(
            product=self.product, provider=ProductVideo.Provider.YOUTUBE,
            url="https://youtu.be/dQw4w9WgXcQ", display_order=1,
        )
        response = self.client.get(self.url)
        content = response.content.decode()
        self.assertEqual(content.count("https://www.youtube.com/embed/dQw4w9WgXcQ"), 2)

    def test_aparat_video_renders_safe_embed_iframe(self):
        ProductVideo.objects.create(
            product=self.product, provider=ProductVideo.Provider.APARAT,
            url="https://www.aparat.com/v/abc123XY",
        )
        response = self.client.get(self.url)
        self.assertContains(response, "https://www.aparat.com/video/video/embed/videohash/abc123XY/vt/frame")
        self.assertContains(response, "آپارات")

    def test_malformed_or_unsafe_stored_url_is_skipped_not_crashed(self):
        """اگر یک ردیفِ نامعتبر (مثلاً از دستکاریِ مستقیمِ دیتابیس، نه مسیرِ
        عادیِ افزودنِ ویدیو که همیشه پیش از ذخیره اعتبارسنجی می‌کند) وجود
        داشته باشد، صفحه‌ی محصول نباید خطای ۵۰۰ بدهد — آن یک ردیف فقط
        نادیده گرفته می‌شود، بقیه‌ی ویدیوهایِ معتبر همچنان رندر می‌شوند."""
        ProductVideo.objects.create(
            product=self.product, provider=ProductVideo.Provider.YOUTUBE,
            url="javascript:alert(1)", title="ناامن",
        )
        ProductVideo.objects.create(
            product=self.product, provider=ProductVideo.Provider.YOUTUBE,
            url="https://www.youtube.com/watch?v=dQw4w9WgXcQ", title="معتبر",
        )
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ویدئوهای محصول")
        self.assertContains(response, "معتبر")
        self.assertNotContains(response, "ناامن")
        self.assertNotContains(response, "javascript:")

    def test_instagram_video_renders_safe_link_preview_not_iframe(self):
        ProductVideo.objects.create(
            product=self.product, provider=ProductVideo.Provider.INSTAGRAM,
            url="https://www.instagram.com/reel/CzXyZ12345/", title="ریلِ معرفی",
        )
        response = self.client.get(self.url)
        content = response.content.decode()
        self.assertIn("مشاهده در اینستاگرام", content)
        self.assertIn('href="https://www.instagram.com/reel/CzXyZ12345/"', content)
        self.assertIn('target="_blank"', content)
        self.assertIn('rel="noopener noreferrer"', content)
        self.assertIn("اینستاگرام", content)
        self.assertIn("ریلِ معرفی", content)
        # هیچ iframeی برای اینستاگرام نباید رندر شود.
        self.assertNotIn('<iframe src="https://www.instagram.com', content)

    def test_multiple_videos_preserve_display_order(self):
        ProductVideo.objects.create(
            product=self.product, provider=ProductVideo.Provider.YOUTUBE,
            url="https://www.youtube.com/watch?v=dQw4w9WgXcQ", title="دوم", display_order=1,
        )
        ProductVideo.objects.create(
            product=self.product, provider=ProductVideo.Provider.APARAT,
            url="https://www.aparat.com/v/abc123XY", title="اول", display_order=0,
        )
        response = self.client.get(self.url)
        content = response.content.decode()
        self.assertLess(content.index("اول"), content.index("دوم"))

    def test_cross_product_video_does_not_appear(self):
        other = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="کالای دیگر",
            slug="other-video-product", sku="SKU-VID2", price=Decimal("50000"),
        )
        ProductVideo.objects.create(
            product=other, provider=ProductVideo.Provider.YOUTUBE,
            url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        )
        response = self.client.get(self.url)
        self.assertNotContains(response, "ویدئوهای محصول")

    @override_settings(ALLOWED_HOSTS=[VIDEO_HOST, "testserver"])
    def test_cross_store_video_does_not_appear(self):
        """اگر Storeی دیگری با ``StoreDomain``ی واقعی و تأییدشده وجود داشته
        باشد، ویدیویِ آن هرگز نباید در صفحه‌ی محصولِ فروشگاهِ فعلی (که با
        همان Hostِ خودش resolve می‌شود) نشت کند — همان روشِ Hostِ واقعی که
        ``test_store_isolation.py`` استفاده می‌کند، نه fallbackِ
        تک‌فروشگاهیِ ``resolve_compatibility_store`` (که با ساختِ دومین
        Store همیشه fail-closed می‌شود)."""
        _verified_domain(self.store, VIDEO_HOST)
        other_store = Store.objects.create(
            name="فروشگاه دیگر", slug="other-video-store", status=Store.Status.ACTIVE,
        )
        other_vendor = Vendor.objects.create(store=other_store, name="فروشنده", slug="other-video-vendor")
        other_category = Category.objects.create(store=other_store, name="دسته", slug="other-video-cat")
        other_product = Product.objects.create(
            store=other_store, vendor=other_vendor, category=other_category, name="کالای فروشگاهِ دیگر",
            slug="video-product", sku="SKU-VID3", price=Decimal("50000"),
        )
        ProductVideo.objects.create(
            product=other_product, provider=ProductVideo.Provider.YOUTUBE,
            url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        )
        response = self.client.get(self.url, HTTP_HOST=VIDEO_HOST)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "ویدئوهای محصول")

    def test_no_n_plus_one_query_for_videos(self):
        for i in range(5):
            ProductVideo.objects.create(
                product=self.product, provider=ProductVideo.Provider.YOUTUBE,
                url="https://www.youtube.com/watch?v=dQw4w9WgXcQ", display_order=i,
            )
        self.client.get(self.url)  # first request provisions the Store's default composition once
        with CaptureQueriesContext(connection) as ctx_one:
            self.client.get(self.url)
        ProductVideo.objects.create(
            product=self.product, provider=ProductVideo.Provider.YOUTUBE,
            url="https://www.youtube.com/watch?v=dQw4w9WgXcQ", display_order=5,
        )
        with CaptureQueriesContext(connection) as ctx_two:
            self.client.get(self.url)
        # افزودنِ یک ویدیوی دیگر نباید تعدادِ کوئری‌ها را افزایش دهد —
        # prefetch_related("videos") باید یک کوئریِ ثابت برایِ کلِ فهرست
        # اجرا کند، نه یک کوئری به‌ازایِ هر ویدیو.
        self.assertEqual(len(ctx_one.captured_queries), len(ctx_two.captured_queries))

    def test_video_section_markup_is_mobile_responsive(self):
        ProductVideo.objects.create(
            product=self.product, provider=ProductVideo.Provider.YOUTUBE,
            url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        )
        response = self.client.get(self.url)
        content = response.content.decode()
        self.assertIn("pdp-video-grid", content)
        self.assertIn("pdp-video-frame", content)

    def test_single_video_uses_large_full_width_modifier_class(self):
        """رگرسیون: با یک ویدیو، شبکه نباید بازِ کوچکِ ``auto-fill`` با
        ``minmax(260px,...)`` بماند (باگی که پخش‌کننده را به‌اندازه‌ی یک
        تامبنیلِ باریک نشان می‌داد) — باید کلاسِ ``pdp-video-grid--single``
        بگیرد تا CSS آن را تمامِ‌عرض و وسط‌چین رندر کند."""
        ProductVideo.objects.create(
            product=self.product, provider=ProductVideo.Provider.YOUTUBE,
            url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        )
        response = self.client.get(self.url)
        content = response.content.decode()
        self.assertIn("pdp-video-grid--single", content)
        self.assertNotIn("pdp-video-grid--multi", content)

    def test_multiple_videos_use_multi_modifier_class(self):
        for i in range(2):
            ProductVideo.objects.create(
                product=self.product, provider=ProductVideo.Provider.YOUTUBE,
                url="https://www.youtube.com/watch?v=dQw4w9WgXcQ", display_order=i,
            )
        response = self.client.get(self.url)
        content = response.content.decode()
        self.assertIn("pdp-video-grid--multi", content)
        self.assertNotIn("pdp-video-grid--single", content)

    def test_instagram_link_card_still_uses_shared_responsive_frame_class(self):
        """پیش‌نمایشِ لینکِ اینستاگرام باید همان کلاسِ ``pdp-video-frame``یِ
        اسپکت‌ریشوی ۱۶:۹ را داشته باشد تا هم‌عرضِ بقیه‌ی پخش‌کننده‌ها بماند،
        نه یک کارتِ کوچکِ جداگانه."""
        ProductVideo.objects.create(
            product=self.product, provider=ProductVideo.Provider.INSTAGRAM,
            url="https://www.instagram.com/reel/CzXyZ12345/",
        )
        response = self.client.get(self.url)
        content = response.content.decode()
        self.assertIn('class="pdp-video-frame pdp-video-linkcard"', content)

    def test_no_hardcoded_small_iframe_dimensions_in_markup(self):
        """رگرسیون: ``<iframe>`` نباید صفتِ ``width``/``height``ِ اینلاین
        داشته باشد که بتواند اندازه‌ی CSSِ ریسپانسیو (۱۶:۹، عرضِ ۱۰۰٪) را
        override کند."""
        ProductVideo.objects.create(
            product=self.product, provider=ProductVideo.Provider.YOUTUBE,
            url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        )
        response = self.client.get(self.url)
        content = response.content.decode()
        iframe_start = content.index("<iframe")
        iframe_tag = content[iframe_start:content.index(">", iframe_start)]
        self.assertNotIn("width=", iframe_tag)
        self.assertNotIn("height=", iframe_tag)

    def test_merchant_preview_also_renders_videos(self):
        """پیش‌نمایشِ ادمین (``dashboard:product-preview``) همان تابعِ
        کانتکستِ صفحه‌ی محصول را به اشتراک می‌گذارد — نگاه کنید به
        apps.dashboard.views.product_preview."""
        from django.contrib.auth import get_user_model

        from apps.stores.models import StoreMembership
        from django.utils import timezone

        ProductVideo.objects.create(
            product=self.product, provider=ProductVideo.Provider.YOUTUBE,
            url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        )
        User = get_user_model()
        staff = User.objects.create_user(username="pdp-video-staff", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client.login(username="pdp-video-staff", password="pass12345")
        response = self.client.get(reverse("dashboard:product-preview", args=[self.product.pk]))
        self.assertContains(response, "ویدئوهای محصول")


class ProductVideoCSSSizeTests(TestCase):
    """رگرسیونِ CSS: باگِ اصلیِ «پخش‌کننده خیلی کوچک است» از
    ``grid-template-columns:repeat(auto-fill,minmax(260px,1fr))`` می‌آمد —
    با یک ویدیو، آن قاعده فقط اولین بازِ ۲۶۰px را پر می‌کرد و بقیه‌ی
    عرضِ ناحیه‌ی محتوا به‌صورتِ فضایِ خالیِ نامرئی رها می‌شد. این تست مستقیماً
    خودِ فایلِ CSS را می‌خواند تا اگر کسی دوباره یک اندازه‌ی کوچکِ ثابت
    اضافه کرد، رگرسیون بلافاصله مشخص شود."""

    def _read_css(self):
        import pathlib

        path = pathlib.Path(__file__).resolve().parents[1] / "static" / "css" / "product_detail.css"
        return path.read_text(encoding="utf-8")

    def test_no_small_auto_fill_minmax_260_remains(self):
        css = self._read_css()
        self.assertNotIn("grid-template-columns:repeat(auto-fill", css)
        self.assertNotIn("minmax(260px", css)

    def test_single_video_modifier_spans_full_width_with_readable_max_width(self):
        css = self._read_css()
        self.assertIn(".pdp-video-grid--single", css)
        self.assertIn("max-width:1100px", css)
        self.assertIn("margin:0 auto", css)

    def test_multi_video_modifier_uses_reasonable_minimum_width(self):
        css = self._read_css()
        self.assertIn(".pdp-video-grid--multi", css)
        self.assertIn("minmax(320px,1fr)", css)

    def test_video_frame_uses_responsive_aspect_ratio_not_fixed_height(self):
        css = self._read_css()
        self.assertIn(".pdp-video-frame{", css)
        self.assertIn("aspect-ratio:16/9", css)
        frame_rule_start = css.index(".pdp-video-frame{")
        frame_rule = css[frame_rule_start:css.index("}", frame_rule_start)]
        self.assertNotIn("height:2", frame_rule)  # no fixed pixel height like "height:220px"
        self.assertIn("width:100%", frame_rule)

    def test_iframe_fills_its_wrapper(self):
        css = self._read_css()
        self.assertIn(".pdp-video-frame iframe{", css)
        iframe_rule_start = css.index(".pdp-video-frame iframe{")
        iframe_rule = css[iframe_rule_start:css.index("}", iframe_rule_start)]
        self.assertIn("width:100%", iframe_rule)
        self.assertIn("height:100%", iframe_rule)
