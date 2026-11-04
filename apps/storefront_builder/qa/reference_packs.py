"""Demo content packs for the reference-capture harness (store-owned demo data; generic names, no third-party copy)."""

from .reference_capture import register_pack


def _extend(names: tuple, count: int) -> list:
    """``count`` demo names: the listed ones, then the same names with a counter (a catalogue the size of the reference one)."""
    return [name if index < len(names) else f"{name} {index // len(names) + 1}" for index, name in zip(range(count), names * (count // len(names) + 1))]

_DECOR_NAMES = (
    "کاسه شیشه و سنگ سایز کوچک", "سرویس غذاخوری سرامیکی", "استند کیک و میوه", "کاسه پایه بلند",
    "ست بانکه مدرن سنگ", "پیاله سنگی", "اردوخوری سه خانه", "اردوخوری دو خانه",
    "اردوخوری کاسه‌دار", "جاقاشقی لیوانی", "کاسه آجیل‌خوری", "شکلات‌خوری دربدار",
    "گلدان سنگ ساده", "میوه‌خوری سنگی", "لوح پیاده‌روی سنگ", "لوح سنگ ریز",
)

register_pack(
    "Dize",
    gift_wrap_price=98_000, gift_wrap_title="بسته‌بندی هدیه",
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
        for index, name in enumerate(_extend(_DECOR_NAMES, 24))
    ],
    hero=[{"title": ""}, {"title": ""}, {"title": ""}],
    banners=[{"title": ""}, {"title": ""}],
    pdp={"article_blocks": 2, "paragraphs": 2, "reviews": 0},
    description="<p>توضیحات کامل محصول، جنس و ابعاد در این بخش قرار می‌گیرد.</p>",
)

_BEAUTY_NAMES = (
    "ریمل حجم‌دهنده و بلندکننده", "رژگونه دوتایی", "تینت پوست مرطوب‌کننده", "ژل ابرو", "پالت رژگونه و هایلایتر",
    "پودر فیکس صورتی", "پنکک فول کاور", "کانسیلر مایع", "رژلب مایع مات", "بی‌بی کرم SPF50",
    "کرم آبرسان صورت", "ماسک مو ترمیم‌کننده", "اسکراب لایه‌بردار صورت", "ست براش آرایشی", "مداد چشم ضدآب", "هایلایتر مایع",
)

register_pack(
    "lilikacosmetics",
    logo_file="logo.png",
    exclude_images=r"^[1-7]\.png$|logo|Untitled|background_removed|photo-output",
    header={},
    store_name="فروشگاه لوازم آرایشی", tagline="لوازم آرایشی و بهداشتی", phone="09300000000",
    footer_text="تضمین کیفیت، شفافیت قیمت، دسترسی آسان به محصولات از ارزش‌های فروشگاه ماست.",
    copyright="کلیه حقوق این سایت متعلق به فروشگاه می‌باشد.",
    categories=(("محصولات آرایشی", "file:1.png"), ("محصولات پوستی", "file:2.png"), ("محصولات مینی سایز", "file:3.png")),
    children={0: (("آرایش صورت", "file:4.png"), ("آرایش لب", "file:5.png"), ("ابزار آرایشی", "file:6.png"), ("آرایش چشم", "file:7.png"))},
    menu=("صفحه نخست", "فروشگاه", "وبلاگ", "تماس با ما"),
    products=[
        {"name": name, "price": 480_000 + index * 330_000, "discount": (15 if index % 4 == 1 else 0), "reviews": 6 + index, "category": index % 3,
         "child": (index % 4) if index % 3 == 0 else None}
        for index, name in enumerate(_extend(_BEAUTY_NAMES, 32))
    ],
    hero=[{"title": ""}],
    banners=[],
    media_assets=[r"^s3\.jpg$"],
    section_fixtures=[{"page": "home", "section_key": "image_text", "settings": {"image_media_asset_id": "@media:0"}}],
    pdp={"article_blocks": 3, "paragraphs": 2, "reviews": 0},
    posts=[
        {"title": "چگونه می‌توان تعادل را به پوست مختلط بازگرداند؟", "kind": "products"},
        {"title": "اشتباهات رایج در استفاده از اسکراب صورت", "kind": "products"},
        {"title": "۱۰ فایده کرم صورت؛ چرا این محصول ضروری است؟", "kind": "products"},
        {"title": "راهنمای انتخاب کانسیلر مناسب پوست", "kind": "products"},
    ],
    description="<p>توضیحات کامل محصول، ترکیبات و روش استفاده در این بخش قرار می‌گیرد.</p>",
)

_GALLERY_NAMES = (
    "سرم ضد ریزش مو", "تونیک تقویت‌کننده مو", "سرم کلاژن و بیوتین", "رژگونه پودری", "کرم بدن معطر وانیل", "کرم بدن لومینوس",
    "سرم ضد آفتاب SPF50", "فوم شستشوی ضد جوش", "پک آرایشی پالت سایه", "ست رژلب ماندگار", "ماسک صورت ترمیم‌کننده", "اسپری مو براق‌کننده",
)

register_pack(
    "lilium-gallery",
    pdp_discounted=True,
    logo_file="",
    exclude_images=r"logo|icon",
    header={
        "announcement_text": "ارسال رایگان برای سفارش‌های بالای ۵ میلیون تومان",
        "announcement_show_phone": True,
    },
    store_name="گالری زیبایی", tagline="عرضه‌کننده برندهای آرایشی بهداشتی", phone="09120000000",
    footer_text="گالری آنلاین زیبایی با تنوع کالا و پشتیبانی همیشگی در کنار شماست.",
    copyright="تمامی حقوق مادی و معنوی متعلق به فروشگاه است.",
    brands=("برند اول", "برند دوم", "برند سوم"),
    categories=(("مراقبت از مو", "squares"), ("آرایشی", "squares"), ("پوست", "squares"), ("عطر و ادکلن", "squares")),
    menu=("لیلیوم تخفیف", "آرایشی", "پوست", "مو", "عطر و ادکلن"),
    products=[
        {"name": name, "price": 1_198_000 + index * 640_000, "discount": (12 if index % 3 == 1 else 0), "reviews": 4 + index,
         "category": index % 4, "stock": (3 if index == 1 else 14)}
        for index, name in enumerate(_extend(_GALLERY_NAMES, 24))
    ],
    hero=[{"title": "", "desktop_file": r"بنر-پالت-سایه", "mobile_file": r"بنر-پالت-سایه"},
          {"title": "", "desktop_file": r"بنر-دستگاه-های-مو"}],
    banners=[{"title": "", "file": r"بنر-ایر-فلو"}, {"title": "", "file": r"بنر-اکوال"}],
    pdp={"article_blocks": 5, "paragraphs": 2, "reviews": 0,
         "specs": (("برند", "نمونه"), ("حجم", "نمونه"), ("کشور سازنده", "نمونه"), ("نوع پوست", "همه"), ("تاریخ انقضا", "نمونه"))},
    banner_sections=[{"page": "home", "section_key": "linked_image", "title": "", "file": r"بنر-محصولات-کراستاس"}],
    section_fixtures=[{"page": "home", "section_key": "trust_features", "settings": {"items": [
        {"icon": "◎", "title": "پرداخت امن", "subtitle": "درگاه فعال فروشگاه", "claim": "payment"},
        {"icon": "⇢", "title": "ارسال سفارش", "subtitle": "روش‌های ارسال فروشگاه", "claim": "shipping"},
        {"icon": "⌂", "title": "تحویل حضوری", "subtitle": "دریافت از فروشگاه", "claim": "pickup"},
        {"icon": "✓", "title": "ضمانت اصالت کالا", "subtitle": "تأییدشده توسط فروشندهٔ QA", "verified": True}]}}],
    description="<h3>درباره این محصول</h3><p>توضیحات کامل محصول، ترکیبات و روش استفاده در این بخش قرار می‌گیرد.</p><ul><li>ویژگی اول محصول</li><li>ویژگی دوم محصول</li></ul>",
)

_HONEY_NAMES = (
    "رژلب مایع مات", "رژگونه مایع", "رژگونه کالیستا", "خط چشم ماندگار", "تینت لب و گونه", "اسپری فیکس آرایش",
    "ضد آفتاب مای SPF50", "کرم ضد جوش", "کرم مرطوب‌کننده", "ژل شستشوی صورت", "لوسیون بدن", "عطر زنانه",
    "شامپو ترمیم‌کننده", "ماسک مو", "پنکک کرمی", "کرم پودر",
)

register_pack(
    "AsalBanoo",
    pdp_discounted=True,
    logo_file="",
    exclude_images=r"logo|icon|badge",
    header={"announcement_text": "ارسال رایگان به سراسر کشور برای خریدهای بالای ۲ میلیون تومان", "announcement_show_phone": False},
    store_name="فروشگاه آرایشی بهداشتی", tagline="فروشگاه آرایشی و بهداشتی", phone="09120000000",
    footer_text="فروشگاه آرایشی بهداشتی با سال‌ها تجربه، ارائه‌دهندهٔ محصولات اورجینال و مشاورهٔ تخصصی.",
    copyright="تمام حقوق این سایت متعلق به فروشگاه است.",
    brands=("برند اول", "برند دوم", "برند سوم"),
    categories=(("کرم پودر", "squares"), ("شوینده و پاک کننده", "squares"), ("شامپو", "squares"), ("عطر و پرفیوم", "squares"),
                ("ضد آفتاب", "squares"), ("رژلب", "squares"), ("آبرسان", "squares"), ("مراقبت از مو", "squares")),
    menu=("صفحه اصلی", "برندها", "تخفیفات", "اپلیکیشن", "بلاگ", "تماس با ما", "درباره ما"),
    products=[
        {"name": name, "price": 480_000 + index * 95_000, "discount": (10 if index % 2 == 0 else 0), "reviews": 12 + index,
         "category": index % 8, "rating": "4.6"}
        for index, name in enumerate(_extend(_HONEY_NAMES, 32))
    ],
    hero=[{"title": "", "desktop_file": r"^perfume\.webp$", "mobile_file": r"^perfumemo\.webp$"},
          {"title": "", "desktop_file": r"^cosmetic\.webp$", "mobile_file": r"^cosmeticmo\.webp$"}],
    banners=[{"title": "", "file": r"^brush-banner\.webp$"}, {"title": "", "file": r"^fix-banner\.webp$"}, {"title": "", "file": r"^foundation\.webp$"},
             {"title": "مشاور اول (مشاور تخصصی)", "button": "مشاوره واتس‌اپ", "file": r"^Faranak\.webp$"},
             {"title": "مشاور دوم (پشتیبان سایت)", "button": "ارتباط تلفنی", "file": r"^Foroozan\.webp$"},
             {"title": "مشاور سوم (امور مشتریان)", "button": "ارتباط تلفنی", "file": r"^Shiba\.webp$"},
             {"title": "مشاور چهارم (مشاور تخصصی)", "button": "مشاوره واتس‌اپ", "file": r"^sima\.webp$"}],
    media_assets=[r"IMG_0075"],
    pdp={"article_blocks": 6, "paragraphs": 3, "reviews": 7,
         "specs": (("حجم", "۱۰۰ میلی‌لیتر"), ("تاریخ انقضا", "نمونه"), ("مناسب برای", "همه انواع پوست"), ("کشور مبدا برند", "نمونه"))},
    section_fixtures=[
        {"page": "home", "section_key": "video_section", "settings": {"videos": [
            {"url": "https://www.youtube.com/watch?v=qa000000001", "title": "عنوان ویدیوی نمونه ۱"},
            {"url": "https://www.youtube.com/watch?v=qa000000002", "title": "عنوان ویدیوی نمونه ۲"},
            {"url": "https://www.youtube.com/watch?v=qa000000003", "title": "عنوان ویدیوی نمونه ۳"}]}},
        {"page": "home", "section_key": "image_text", "settings": {"image_media_asset_id": "@media:0",
            "body_html": "<p>متن نمونهٔ آزمایشی دربارهٔ فروشگاه؛ طول و ریتم این بند از روی یک صفحهٔ معرفی معمول تنظیم شده و محتوای واقعی را مدیر فروشگاه می‌نویسد.</p>"}},
        {"page": "home", "section_key": "trust_features", "settings": {"items": [
            {"icon": "◎", "title": "پرداخت امن", "subtitle": "درگاه فعال فروشگاه", "claim": "payment"},
            {"icon": "⇢", "title": "ارسال سفارش", "subtitle": "روش‌های ارسال فروشگاه", "claim": "shipping"},
            {"icon": "⌂", "title": "تحویل حضوری", "subtitle": "دریافت از فروشگاه", "claim": "pickup"},
            {"icon": "✓", "title": "ضمانت اصالت کالا", "subtitle": "تأییدشده توسط فروشندهٔ QA", "verified": True}]}},
        {"page": "product_detail", "section_key": "faq", "settings": {"items": [
            {"question": "پرسش نمونهٔ اول دربارهٔ محصول؟", "answer": "پاسخ نمونهٔ آزمایشی؛ پاسخ واقعی را مدیر فروشگاه می‌نویسد."},
            {"question": "پرسش نمونهٔ دوم دربارهٔ ارسال؟", "answer": "پاسخ نمونهٔ آزمایشی؛ پاسخ واقعی را مدیر فروشگاه می‌نویسد."},
            {"question": "پرسش نمونهٔ سوم دربارهٔ استفاده؟", "answer": "پاسخ نمونهٔ آزمایشی؛ پاسخ واقعی را مدیر فروشگاه می‌نویسد."},
            {"question": "پرسش نمونهٔ چهارم دربارهٔ بازگشت؟", "answer": "پاسخ نمونهٔ آزمایشی؛ پاسخ واقعی را مدیر فروشگاه می‌نویسد."}]}}],
    posts=[
        {"title": "بهترین روتین پوستی برای پوست مختلط", "label": "مراقبت پوستی", "excerpt": "راهنمای کامل انتخاب و استفاده از محصولات.", "kind": "wide"},
        {"title": "نحوه تمیز کردن صحیح برس‌های آرایشی", "label": "لوازم آرایشی", "excerpt": "نکاتی برای نگهداری بهتر از ابزار آرایش.", "kind": "wide"},
        {"title": "آبرسانی پوست در فصل سرد", "label": "مراقبت پوستی", "excerpt": "چند توصیهٔ ساده برای پوست شاداب.", "kind": "wide"},
        {"title": "علت رنگ‌گذاری موی بلوند", "label": "مو", "excerpt": "توضیحی دربارهٔ تغییر رنگ مو و راه‌حل‌ها.", "kind": "wide"},
    ],
    description="<p>توضیحات کامل محصول، ترکیبات و روش استفاده.</p><ul><li>ویژگی اول</li><li>ویژگی دوم</li></ul>",
)

_COCOA_NAMES = (
    "ماگ سرامیکی دسته‌دار", "تراول ماگ ۷۵۰ میل", "فلاسک استیل ۱ لیتری", "ظرف غذا و کیف غذا", "ست قهوه‌ساز", "هم‌زن برقی",
    "کیف مسافرتی", "بطری آب ورزشی", "ماگ دیزنی", "پیک‌نیک‌ست", "قمقمه ضدزنگ", "لیوان حرارتی",
    "جعبه هدیه", "ظرف شکلات", "فنجان و نعلبکی", "ترموس چای",
)

register_pack(
    "khanehshokolati",
    gift_wrap_price=98_000, gift_wrap_title="میخواهم سفارشم کادو شود",
    pdp_discounted=True,
    logo_file="logo.png",
    exclude_images=r"logo|icon|badge|34tyyyy|3R34TTT|min-|11zon",
    header={},
    store_name="فروشگاه ماگ و فلاسک", tagline="تراول ماگ، ماگ و هدیه", phone="09120000000",
    footer_text="فروشگاه تخصصی انواع ماگ، تراول ماگ، فلاسک و لوازم قهوه‌خوری.",
    copyright="تمامی حقوق برای این فروشگاه محفوظ است.",
    brands=("برند اول", "برند دوم", "برند سوم"),
    categories=(("ماگ", "file:11-min-510x510_11zon.png"), ("استنلی و سانتکو", "file:12-min-510x510_11zon.png"), ("فلاسک", "file:3-min-510x510_11zon.png"),
                ("تراول ماگ", "file:4-min-510x510_11zon.png"), ("ظرف غذا و کیف غذا", "file:6-min-510x510_11zon.png"), ("قمقمه و شکر", "file:8-min-510x510_11zon.png"),
                ("لوازم قهوه", "file:قوری-وارمر@3x-510x478-1.png"), ("لوازم سفر", "file:lnhk-2-510x510_11zon.png"),
                ("اکسسوری", "file:جعبه-هدیه@3x-510x478-1.png"), ("دیزنی لند", "file:12-min-510x510_11zon.png"), ("هوم", "file:3-min-510x510_11zon.png"),
                ("تخفیف‌ها", "file:آف2-510x510-1.png")),
    menu=("صفحه اصلی", "ماگ", "ترموس و فلاسک", "لوازم سفر", "هدیا", "تخفیف‌ها", "وبلاگ"),
    products=[
        {"name": name, "price": 1_580_000 + index * 190_000, "discount": (15 if index % 3 == 0 else 0), "reviews": 8 + index,
         "category": index % 12}
        for index, name in enumerate(_extend(_COCOA_NAMES, 32))
    ],
    pdp={"article_blocks": 4, "paragraphs": 2, "reviews": 2,
         "variants": (("رنگ", ("آبی", "سبز", "سفید", "مشکی", "صورتی", "قهوه‌ای", "بنفش", "طوسی", "زرد")),),
         "specs": (("جنس", "نمونه"), ("حجم", "۱۰۵۰ میلی‌لیتر"), ("ارتفاع", "نمونه"), ("قطر", "نمونه"), ("نگهداری دما", "نمونه"))},
    hero=[{"title": "تراول ماگ", "button": "لیست محصولات", "desktop_file": r"11_08_10", "mobile_file": r"11_08_10"},
          {"title": "دیزنی لند", "button": "لیست محصولات", "desktop_file": r"11_18_45", "mobile_file": r"11_18_45"},
          {"title": "فلاسک", "button": "لیست محصولات", "desktop_file": r"11_38_32", "mobile_file": r"11_38_32"},
          {"title": "ظرف غذا", "button": "لیست محصولات", "desktop_file": r"12_01_41", "mobile_file": r"12_01_41"},
          {"title": "لوازم سفر", "button": "لیست محصولات", "desktop_file": r"10_59_23", "mobile_file": r"10_59_23"}],
    banners=[{"title": "", "file": pattern} for pattern in (
        r"khaneh-stanley-products", r"SANTECO", r"kolm", r"ssda", r"termos", r"12_01_41", r"khaneh-stanley-products", r"11_08_10", r"11_18_45",
        r"SANTECO", r"kolm", r"ssda", r"termos", r"11_38_32", r"12_01_41", r"11_08_10", r"11_18_45", r"SANTECO", r"kolm")],
    posts=[
        {"title": "طرز تهیه کافه لاته در خانه", "kind": "wide"},
        {"title": "چطور محصولات استنلی را قبل از استفاده آماده کنیم؟", "kind": "wide"},
        {"title": "بهترین مارک پاور بانک چیست؟", "kind": "wide"},
    ],
    description="<p>توضیحات کامل محصول، جنس و ابعاد در این بخش قرار می‌گیرد.</p>",
)

_NEON_NAMES = (
    "اکانت پریمیوم هوش مصنوعی", "اکانت طراحی گرافیک", "اشتراک استریم موسیقی", "اشتراک آموزش آنلاین", "اکانت ویدیو استریم", "سرویس مدیریت پروژه",
    "اکانت ابزار نوشتن", "اشتراک ذخیره‌سازی ابری", "اکانت ویرایش عکس", "اشتراک کتاب صوتی", "سرور مجازی VPS", "ابزار ترجمه هوشمند",
)

register_pack(
    "zhimunplus",
    pdp_discounted=True,
    logo_file="",
    exclude_images=r"logo|icon|badge|avatar",
    header={},
    store_name="فروشگاه اکانت پریمیوم", tagline="همیشه پریمیوم باش", phone="09120000000",
    footer_text="فروشگاه خدمات دیجیتال و اشتراک‌های پریمیوم با پشتیبانی همیشگی.",
    copyright="تمامی حقوق مادی و معنوی این وب‌سایت محفوظ است.",
    brands=("سرویس اول", "سرویس دوم", "سرویس سوم"),
    categories=(("هوش مصنوعی", "squares"), ("طراحی گرافیک", "squares"), ("استریم ویدیو", "squares"), ("آموزش و یادگیری", "squares"),
                ("استریم موسیقی", "squares"), ("شبکه‌های اجتماعی", "squares"), ("خدمات مالی", "squares")),
    menu=("اکانت هوش مصنوعی", "سرویس ویدیو", "سرویس آموزشی", "سرویس گرافیکی", "سرویس موزیک", "درباره ما", "قوانین"),
    products=[
        {"name": name, "price": 299_000 + index * 410_000, "discount": (14 if index % 4 == 0 else 0), "reviews": 6 + index,
         "category": index % 7, "stock": 50, "rating": "4.9"}
        for index, name in enumerate(_extend(_NEON_NAMES, 24))
    ],
    hero=[{"title": "عنوان نمونهٔ هیرو", "subtitle": "زیرعنوان نمونه برای سنجش چیدمان", "button": "دکمهٔ اصلی",
           "desktop_file": r"Neon-Coca-Wallet-Robot", "mobile_file": r"Neon-Coca-Wallet-Robot"}],
    banners=[{"title": "پنل نمونهٔ اول", "description": "توضیح کوتاه نمونه", "file": r"^(robot|painting)\.png$", "alpha": True},
             {"title": "پنل نمونهٔ دوم", "description": "توضیح کوتاه نمونه", "file": r"^(music|circus-tent)\.png$", "alpha": True},
             {"title": "پنل نمونهٔ سوم", "description": "توضیح کوتاه نمونه", "file": r"^(brand-loyalty)\.png$", "alpha": True},
             {"title": "پنل نمونهٔ چهارم", "description": "توضیح کوتاه نمونه", "file": r"^(3d-glasses)\.png$", "alpha": True}],
    pdp={"article_blocks": 8, "paragraphs": 3, "reviews": 3,
         "specs": (("نوع سرویس", "نمونه"), ("مدت", "نمونه"), ("روش تحویل", "نمونه"))},
    section_fixtures=[{"page": "home", "section_key": "testimonials", "settings": {"items": [
        {"name": "مشتری نمونهٔ ۱", "role": "نقش نمونه", "rating": 5, "quote": "متن نمونهٔ آزمایشی برای سنجش طول و ارتفاع کارت نظر؛ این متن واقعی نیست و فقط در فروشگاه QA ساخته می‌شود."},
        {"name": "مشتری نمونهٔ ۲", "role": "نقش نمونه", "rating": 5, "quote": "متن نمونهٔ آزمایشی برای سنجش طول و ارتفاع کارت نظر؛ این متن واقعی نیست و فقط در فروشگاه QA ساخته می‌شود."},
        {"name": "مشتری نمونهٔ ۳", "role": "نقش نمونه", "rating": 4, "quote": "متن نمونهٔ آزمایشی برای سنجش طول و ارتفاع کارت نظر؛ این متن واقعی نیست و فقط در فروشگاه QA ساخته می‌شود."},
        {"name": "مشتری نمونهٔ ۴", "role": "نقش نمونه", "rating": 5, "quote": "متن نمونهٔ آزمایشی برای سنجش طول و ارتفاع کارت نظر؛ این متن واقعی نیست و فقط در فروشگاه QA ساخته می‌شود."}]}}],
    description="<p>توضیحات سرویس، شرایط فعال‌سازی و روش تحویل در این بخش قرار می‌گیرد.</p>",
)
