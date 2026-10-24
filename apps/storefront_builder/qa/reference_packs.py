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
        for index, name in enumerate(_DECOR_NAMES)
    ],
    hero=[{"title": ""}, {"title": ""}, {"title": ""}],
    banners=[{"title": ""}, {"title": ""}],
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
        for index, name in enumerate(_BEAUTY_NAMES)
    ],
    hero=[{"title": ""}],
    banners=[],
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
         "category": index % 4, "stock": (3 if index == 0 else 14)}
        for index, name in enumerate(_GALLERY_NAMES)
    ],
    hero=[{"title": ""}, {"title": ""}],
    banners=[{"title": ""}, {"title": ""}, {"title": ""}],
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
        for index, name in enumerate(_HONEY_NAMES)
    ],
    hero=[{"title": ""}, {"title": ""}],
    banners=[{"title": ""}, {"title": ""}, {"title": ""},
             {"title": "مشاور اول (مشاور تخصصی)", "button": "مشاوره واتس‌اپ", "kind": "products"},
             {"title": "مشاور دوم (پشتیبان سایت)", "button": "ارتباط تلفنی", "kind": "products"},
             {"title": "مشاور سوم (امور مشتریان)", "button": "ارتباط تلفنی", "kind": "products"},
             {"title": "مشاور چهارم (مشاور تخصصی)", "button": "مشاوره واتس‌اپ", "kind": "products"}],
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
    logo_file="",
    exclude_images=r"logo|icon|badge|34tyyyy|3R34TTT|min-|11zon",
    header={},
    store_name="فروشگاه ماگ و فلاسک", tagline="تراول ماگ، ماگ و هدیه", phone="09120000000",
    footer_text="فروشگاه تخصصی انواع ماگ، تراول ماگ، فلاسک و لوازم قهوه‌خوری.",
    copyright="تمامی حقوق برای این فروشگاه محفوظ است.",
    brands=("برند اول", "برند دوم", "برند سوم"),
    categories=(("ماگ", "squares"), ("استنلی و سانتکو", "squares"), ("فلاسک", "squares"), ("تراول ماگ", "squares"),
                ("ظرف غذا و کیف غذا", "squares"), ("قمقمه و شکر", "squares"), ("لوازم قهوه", "squares"), ("لوازم سفر", "squares"),
                ("اکسسوری", "squares"), ("دیزنی لند", "squares"), ("هوم", "squares"), ("تخفیف‌ها", "squares")),
    menu=("صفحه اصلی", "ماگ", "ترموس و فلاسک", "لوازم سفر", "هدیا", "تخفیف‌ها", "وبلاگ"),
    products=[
        {"name": name, "price": 1_580_000 + index * 190_000, "discount": (15 if index % 3 == 0 else 0), "reviews": 8 + index,
         "category": index % 12}
        for index, name in enumerate(_COCOA_NAMES)
    ],
    hero=[{"title": "تراول ماگ", "button": "لیست محصولات"}, {"title": "دیزنی لند", "button": "لیست محصولات"},
          {"title": "فلاسک", "button": "لیست محصولات"}],
    banners=[{"title": ""} for _ in range(19)],
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
        for index, name in enumerate(_NEON_NAMES)
    ],
    hero=[{"title": "پریمیوم بودن با ما قشنگه", "subtitle": "بدون محدودیت از اکانت‌های پریمیوم استفاده کن", "button": "چه اکانتی برام مناسبه"}],
    banners=[{"title": "پشتیبان سریع", "description": "هروقت کمک خواستی"}, {"title": "قیمت منصفانه", "description": "خیالت راحت باشه"},
             {"title": "صرفه‌جویی هزینه", "description": "با هزینه کمتر"}, {"title": "پکیج هدیه", "description": "دوره و مشاوره همراه سرویس"}],
    description="<p>توضیحات سرویس، شرایط فعال‌سازی و روش تحویل در این بخش قرار می‌گیرد.</p>",
)
