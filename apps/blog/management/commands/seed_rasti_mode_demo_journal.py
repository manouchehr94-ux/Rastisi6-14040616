"""Opt-in, idempotent editorial starter for the existing Rasti Mode demo ONLY.

Run with --dry-run to preview. No template, Product, Category, Brand, Footer,
Published layout or other Store is touched. No media paths are fabricated.
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.blog.models import BlogPost
from apps.stores.models import Store


ARTICLES = (
    {
        "slug": "demo-fashion-capsule-wardrobe",
        "title": "راهنمای ساخت کمد کپسولی با چند لباس کاربردی",
        "category_label": "راهنمای استایل",
        "cover_emoji": "👔",
        "tint": "#E5EAF0",
        "excerpt": "چطور با انتخاب چند لباس هماهنگ، ترکیب‌های متنوعی برای روزهای مختلف بسازیم؟",
        "body": (
            "کمد کپسولی یعنی به جای جمع‌آوری لباس‌های زیاد، تعداد محدودی لباس قابل ترکیب و کاربردی انتخاب کنیم. "
            "هدف این روش، کاهش خریدهای کم‌استفاده و ساده‌تر شدن تصمیم‌گیری روزانه است.\n\n"
            "ابتدا لباس‌هایی را که مرتب استفاده می‌کنید بررسی کنید. یک شلوار جین خوش‌فرم، شلوار پارچه‌ای ساده، "
            "پیراهن یا تی‌شرت بدون طرح و یک رویه متناسب با فصل می‌تواند نقطه شروع خوبی باشد. رنگ‌های خنثی "
            "را پایه بگذارید و برای تنوع، یک یا دو رنگ دلخواه به آن اضافه کنید.\n\n"
            "هنگام خرید به سایز واقعی، جنس پارچه و روش شست‌وشو توجه کنید. لباس‌های خوش‌دوختی که با چند قلم "
            "دیگر هماهنگ می‌شوند معمولاً کاربرد بیشتری از خریدهای هیجانی دارند."
        ),
    },
    {
        "slug": "demo-fashion-select-denim-fit",
        "title": "چطور سایز و فرم مناسب شلوار جین را انتخاب کنیم؟",
        "category_label": "راهنمای خرید",
        "cover_emoji": "👖",
        "tint": "#E4E9E4",
        "excerpt": "تفاوت فیت‌ها، اندازه‌گیری دور کمر و قد شلوار قبل از خرید اینترنتی.",
        "body": (
            "برای انتخاب شلوار جین فقط به عدد سایز اکتفا نکنید. فرم شلوار، میزان کشسانی پارچه و اندازه واقعی "
            "دور کمر، دور باسن و قد داخل پا در نتیجه نهایی نقش دارند.\n\n"
            "با متر نرم، اندازه‌های بدن خود را بگیرید و با جدول سایزبندی همان محصول مقایسه کنید. اگر بین "
            "دو سایز مردد هستید، ترکیب پارچه را بخوانید؛ پارچه‌های دارای الیاف کشی معمولاً آزادی حرکت بیشتری دارند.\n\n"
            "در عکس‌های محصول به فرم شلوار روی مدل و ارتفاع فاق توجه کنید. پیش از سفارش، شرایط تعویض سایز "
            "و روش مراقبت از پارچه را هم بررسی کنید."
        ),
    },
    {
        "slug": "demo-fashion-bag-shoe-colors",
        "title": "هماهنگ‌کردن کیف و کفش؛ فراتر از رنگ یکسان",
        "category_label": "ترکیب رنگ",
        "cover_emoji": "👜",
        "tint": "#EFE4DC",
        "excerpt": "چند راه ساده برای ساخت استایل منسجم با کیف و کفش، بدون الزام به ست کامل.",
        "body": (
            "برای هماهنگی کیف و کفش لازم نیست همیشه هر دو دقیقاً یک رنگ باشند. تناسب جنس، میزان رسمیت و "
            "شدت رنگ‌ها اغلب از یکسان بودن رنگ مهم‌تر است.\n\n"
            "اگر لباس‌های شما ساده‌اند، یک کیف با رنگ شاخص می‌تواند نقطه تمرکز استایل باشد. در مقابل، "
            "برای لباس‌های طرح‌دار، کیف و کفش خنثی معمولاً تعادل بیشتری ایجاد می‌کنند.\n\n"
            "در خرید آنلاین، ابعاد کیف، جنس رویه کفش و نوع استفاده روزانه را کنار رنگ و ظاهر بسنجید. "
            "هماهنگی خوب باید هم زیبا باشد و هم نیاز واقعی شما را برآورده کند."
        ),
    },
    {
        "slug": "demo-fashion-caring-cotton",
        "title": "مراقبت از لباس‌های نخی برای ماندگاری بیشتر",
        "category_label": "مراقبت از پوشاک",
        "cover_emoji": "🧺",
        "tint": "#E5E5EF",
        "excerpt": "نکته‌های ساده شست‌وشو، خشک‌کردن و نگهداری لباس‌های نخی.",
        "body": (
            "لباس نخی برای استفاده روزمره مناسب است، اما شست‌وشو و خشک‌کردن نادرست می‌تواند باعث جمع‌شدگی "
            "یا تغییر فرم آن شود. همیشه برچسب مراقبت خود لباس را مبنا قرار دهید.\n\n"
            "پیش از شست‌وشو لباس را پشت‌ورو کنید، رنگ‌های روشن و تیره را جدا نگه دارید و از شوینده متناسب با "
            "نوع پارچه استفاده کنید. دمای بالاتر لزوماً به تمیزی بهتر منجر نمی‌شود.\n\n"
            "برای خشک‌کردن، لباس را بدون کشیدن آویزان یا روی سطح مناسب پهن کنید. نگهداری دور از نور مستقیم "
            "و رطوبت زیاد نیز به حفظ کیفیت پارچه کمک می‌کند."
        ),
    },
)


class Command(BaseCommand):
    help = "Opt-in 4 Store-scoped demo-fashion journal articles; no catalog/media/layout writes."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Show planned articles, no writes.")

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Only available with DEBUG=True; no production writes.")
        store = Store.objects.filter(slug="rasti-mode-demo").first()
        if not store:
            raise CommandError("Rasti Mode demo Store does not exist; nothing changed.")
        for item in ARTICLES:
            clash = BlogPost.objects.filter(slug=item["slug"]).exclude(store=store).first()
            if clash:
                raise CommandError(f"Blog slug belongs to a different Store: {item['slug']}")
        missing = [item for item in ARTICLES if not BlogPost.objects.filter(
            store=store, slug=item["slug"],
        ).exists()]
        self.stdout.write(f"Demo: {store.slug}; new articles: {len(missing)}; total defined: {len(ARTICLES)}")
        for item in missing:
            self.stdout.write(f"  + {item['title']}")
        if options["dry_run"]:
            return
        with transaction.atomic():
            for item in missing:
                BlogPost.objects.get_or_create(
                    store=store, slug=item["slug"],
                    defaults={**{k: v for k, v in item.items() if k != "slug"},
                              "published_at": timezone.now()},
                )
        self.stdout.write(self.style.SUCCESS("Demo-only journal created. No other Store, catalog or layouts modified."))
