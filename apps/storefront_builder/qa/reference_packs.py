"""Demo content packs for the reference-capture harness (store-owned demo data; generic names, no third-party copy)."""

from .reference_capture import register_pack

_DECOR_NAMES = (
    "کاسه شیشه و سنگ سایز کوچک", "سرویس غذاخوری سرامیکی", "استند کیک و میوه", "کاسه پایه بلند",
    "ست بانکه مدرن سنگ", "پیاله سنگی", "اردوخوری سه خانه", "اردوخوری دو خانه",
    "اردوخوری کاسه‌دار", "جاقاشقی لیوانی", "کاسه آجیل‌خوری", "شکلات‌خوری دربدار",
    "گلدان سنگ ساده", "میوه‌خوری سنگی", "لوح پیاده‌روی سنگ", "لوح سنگ ریز",
)

register_pack(
    "Dize",
    logo_file="logonomy-1721942993137.png",
    header={
        "announcement_text": "در کانال ما همراه باشید و از تخفیف‌های جذاب زودتر باخبر بشید!",
        "announcement_links": [{"label": "عضو شوید", "url": "#"}],
        "announcement_show_phone": False,
    },
    store_name="فروشگاه دکور و لوازم خانه", tagline="لوازم خانه و دکوراسیون", phone="09120000000",
    footer_text="", copyright="تمام حقوق محفوظ و متعلق به فروشگاه است.",
    categories=(("محصولات سنگی", "squares"), ("محصولات سرامیکی", "squares")),
    menu=("خانه", "فروشگاه", "محصولات", "تماس با ما"),
    products=[
        {"name": name, "price": 1_890_000 + index * 310_000, "discount": 0, "reviews": 9 + index, "category": index % 2}
        for index, name in enumerate(_DECOR_NAMES)
    ],
    hero=[{"title": ""}, {"title": ""}, {"title": ""}],
    banners=[{"title": ""}, {"title": ""}],
    description="<p>توضیحات کامل محصول، جنس و ابعاد در این بخش قرار می‌گیرد.</p>",
)
