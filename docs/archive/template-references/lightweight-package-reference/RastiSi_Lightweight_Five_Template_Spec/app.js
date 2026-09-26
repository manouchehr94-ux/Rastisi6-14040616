const ROOT = document.body.dataset.root || ".";

const SPECS = {
  beraito: {
    number: "01",
    brand: "Beraito reference",
    name: "قالب ۱ — کاتالوگ رنگی",
    family: "Vibrant Catalog",
    accent: "#FD445D",
    miniBg: "#ffe6eb",
    emojis: "✏️ 📒 🎨 🎒",
    summary: "فروشگاه پرتراکم، قیمت‌محور و تبلیغاتی با هدر سه‌لایه، داشبورد پیشنهادها و ردیف‌های متعدد محصول.",
    layout: [
      "عرض محتوای اصلی نزدیک 1140px؛ پس‌زمینه بعضی بخش‌ها تمام‌عرض.",
      "هدر سه‌لایه: Utility، لوگو/جست‌وجو/سبد، Navigation و Mega Menu.",
      "شروع صفحه با Promo dashboard؛ نه Hero سینمایی تک‌تصویری.",
      "ترتیب: پیشنهاد لحظه‌ای، دسته سریع، مزایا، کالکشن‌ها، بنرها، برندها، بلاگ و Footer تیره.",
      "چگالی زیاد است و چند محصول هم‌زمان باید در نخستین اسکرول دیده شود."
    ],
    components: [
      "Product card واقعی: تصویر 1:1، عنوان و قیمت وسط‌چین، قیمت قبلی/جدید، Discount badge، CTA لمس‌پذیر.",
      "Bannerها نسبت‌های متنوع دارند؛ Shine و Zoom کوتاه و فروش‌محور.",
      "Footer تیره چندستونه با خدمات، دسته‌های سریع، تماس و Trust badges.",
      "Radius کارت حدود 10px، Search حدود 22px، Shell #F4F5F9 و Accent #FD445D."
    ],
    mobile: [
      "Navigation دسکتاپ با Header موبایل جایگزین شود.",
      "ردیف محصول به Rail افقی یا Grid دو ستونه تبدیل شود.",
      "هیچ CTA حیاتی فقط روی Hover باقی نماند.",
      "Sticky add-to-cart فقط در صفحه محصول فعال باشد."
    ],
    product: [
      "Gallery استاندارد در کنار پنل خرید؛ عنوان، قیمت، موجودی، تعداد و CTA واضح.",
      "اطلاعات تخفیف و قیمت نسبت به توضیحات اولویت بصری دارند.",
      "محصولات مرتبط از همان square_centered_commerce renderer استفاده کنند."
    ],
    avoid: ["Mega Menu بیش از حد شلوغ", "صفحه بی‌نهایت طولانی", "رنگ تخفیف hard-coded", "متن تبلیغاتی داخل bitmap"]
  },
  cactus: {
    number: "02",
    brand: "Cactus Leather reference",
    name: "قالب ۲ — پرمیوم چرمی",
    family: "Heritage Premium",
    accent: "#07705E",
    miniBg: "#e5efe9",
    emojis: "👜 👞 🎒 🧥",
    summary: "فروشگاه پرمیوم و تصویرمحور با Hero تمام‌عرض، کارت‌های 3:4 و صفحه محصول مناسب رنگ، سایز و Gallery بزرگ.",
    layout: [
      "Container عریض تا حدود 1600px و فضای سفید فراوان.",
      "Promotion strip، هدر ثابت، Navigation دسته‌ها و Full-bleed campaign hero.",
      "ترتیب: Hero، شش دسته Portrait، کمپین، جدیدترین‌ها، Promo grid، خدمات، پرفروش‌ها، بلاگ و Footer روشن.",
      "تصویر و Lifestyle از فهرست ویژگی‌ها مهم‌ترند؛ چگالی متوسط و ریتم آرام است."
    ],
    components: [
      "Product card واقعی: تصویر نزدیک 3:4، اطلاعات زیر تصویر، ابزار محدود، Badge کمپین و Overlay اختیاری قسط.",
      "دو renderer مجزا: premium_portrait و premium_campaign.",
      "Palette پایه سبز #07705E، طلایی چرمی نزدیک #DDB475 و خنثی گرم.",
      "Footer روشن و هویتی؛ تماس، آدرس و شبکه اجتماعی پررنگ‌تر از تبلیغات."
    ],
    mobile: [
      "Hero می‌تواند Asset/Crop مخصوص Mobile داشته باشد، بدون Duplicate کامل markup.",
      "Actionهای کناری باید به دکمه ثابت یا لمس‌پذیر تبدیل شوند.",
      "CTA خرید در پایین صفحه محصول Sticky باشد.",
      "از Min-heightهای جادویی و شکننده برای تصاویر خودداری شود."
    ],
    product: [
      "Gallery عمودی بزرگ، پنل خرید، انتخاب سایز و رنگ، موجودی، قیمت و پرداخت اختیاری.",
      "تب مشخصات، دیدگاه و ویدیوی کالا؛ ویدیو Capability است نه بخشی اجباری از قالب.",
      "Variant image با انتخاب رنگ باید تصویر متناظر را نمایش دهد."
    ],
    avoid: ["Share روی همه کارت‌ها", "Action فقط Hover", "Duplicate desktop/mobile", "وابستگی به سرویس پرداخت خاص"]
  },
  deeyar: {
    number: "03",
    brand: "Deeyar reference",
    name: "قالب ۳ — صنایع‌دستی روایی",
    family: "Artisan Editorial",
    accent: "#888210",
    miniBg: "#efeadf",
    emojis: "🏺 🧶 🪡 🧵",
    summary: "فروشگاه فرهنگی و داستان‌محور که محصول، سازنده، کارگاه، مجله و محتوای اجتماعی را در یک روایت پیوسته ترکیب می‌کند.",
    layout: [
      "Layout بسیار عریض تا حدود 1540–1676px و Header آرام دو‌لایه.",
      "ترتیب: Hero، چهار Category banner، محصولات جدید، بنر صنایع، کالکشن‌های Tabbed، About، کارگاه/مجله، Social gallery و Footer.",
      "About section یک بخش اصلی Homepage است و نباید به چند خط در Footer تقلیل یابد.",
      "چگالی متوسط، فضای گرم و نسبت‌های تصویری آگاهانه و متنوع."
    ],
    components: [
      "Product card: تصویر بالا، عنوان وسط‌چین، قیمت قبلی/جدید، badge گوشه، Border/Shadow ملایم.",
      "Metadata کوتاه سازنده/منطقه اختیاری است و کارت را از کارت عمومی جدا می‌کند.",
      "Banner با عنوان Overlay و Backdrop blur؛ Blog/Workshop card renderer جدا.",
      "Accent زیتونی #888210، فونت سلسله‌مراتبی، Radius 8–15px و Motion بسیار آرام."
    ],
    mobile: [
      "در موبایل دو کارت کوچک در ردیف قابل قبول است؛ برای محتوای روایی Rail افقی استفاده شود.",
      "About split به یک ستون تبدیل شود و متن همچنان خوانا بماند.",
      "ارتفاع تصاویر کنترل شود، بدون وابستگی به Placeholderهای خارجی.",
      "Social gallery اختیاری و قابل خاموش‌کردن باشد."
    ],
    product: [
      "Gallery و پنل خرید ساده‌تر از قالب فنی؛ داستان محصول نزدیک عنوان، قیمت و CTA.",
      "Wishlist، تعداد، محصولات مرتبط و توضیحات بلند Editorial.",
      "مشخصات فنی اهمیت ثانویه دارد اما حذف نمی‌شود."
    ],
    avoid: ["Blog اجباری", "Instagram اجباری", "سبز hard-coded در component", "Navigation طولانی بدون grouping"]
  },
  ibolak: {
    number: "04",
    brand: "iBolak reference",
    name: "قالب ۴ — مد مدرن",
    family: "Modern Fashion",
    accent: "#FCBD15",
    miniBg: "#fff3cc",
    emojis: "👗 👕 👖 👟",
    summary: "فروشگاه مد سفید و اجتماعی با Story rail، دسته‌های Editorial، Hero carousel و کارت 9:12 دارای Gallery چندتصویری.",
    layout: [
      "Header دو‌لایه: لوگو/جست‌وجوی بزرگ/ورود/سبد و Navigation همراه لینک‌های اجتماعی.",
      "ترتیب: Story rail، Hero سه‌اسلایدی، هشت Category tile عمودی، ردیف‌های محصول، Blog و Footer مینیمال.",
      "Shell سفید، فضای خالی زیاد، Shadow محدود و Radius پایه 16px.",
      "چگالی متوسط و تمرکز اصلی بر تصویر مدل و Product discovery سریع."
    ],
    components: [
      "Product card واقعی با DOM مستقل: تصویر 9:12، Wishlist، discount pill، عنوان راست و قیمت چپ.",
      "Desktop: Zoom 1.08 و Thumbnail reveal؛ Mobile: Swipe/Tap و نه Hover.",
      "Story rail دایره‌ای یک Section مستقل و اختیاری است.",
      "رنگ پایه #FCBD15، تخفیف #FF0080، متن #323232؛ Palette باید قابل Override باشد."
    ],
    mobile: [
      "Navigation ثانویه حذف و لوگو مرکزی شود.",
      "ردیف محصول به Horizontal rail با کارت حدود 70vw تبدیل شود.",
      "Thumbnail hover با Swipe/Tap جایگزین شود.",
      "Size chart و انتخاب Variant کاملاً Touch-friendly باشند."
    ],
    product: [
      "Gallery بزرگ با Thumbnail عمودی، انتخاب رنگ و سایز، Size chart و CTA برجسته.",
      "تب مشخصات/دیدگاه، توضیحات Editorial، FAQ و محصولات مرتبط.",
      "انتخاب رنگ باید Gallery همان Variant را فعال کند."
    ],
    avoid: ["Storyهای بیش از حد", "Hover بدون fallback", "9:12 اجباری برای همه صنایع", "صورتی hard-coded برای تخفیف"]
  },
  ikalajam: {
    number: "05",
    brand: "IkalaJam reference",
    name: "قالب ۵ — خانه و زندگی نوردیک",
    family: "Nordic Living",
    accent: "#183E85",
    miniBg: "#e9e4d9",
    emojis: "🛋️ ☕ 🕯️ 🪑",
    summary: "فروشگاه خانه و دکور Search-first با بنرهای خنثی، کاتالوگ متوسط‌متراکم و کارت محصول دارای تصویر دوم.",
    layout: [
      "Announcement مشکی، Utility، Header اصلی با Search برجسته و Mega Navigation.",
      "Container حدود 1200px و در نمایشگر بزرگ تا 1440px.",
      "ترتیب: Hero خنثی، نوار مزایا، کالکشن‌ها، چهار بنر موضوعی و Footer چندسطحی.",
      "Category-led است نه Discount-led؛ فضا آرام اما کاتالوگ کامل است."
    ],
    components: [
      "Product card: نسبت ملایم 7:8، تصویر جلو/دوم، عنوان دوخطی، قیمت و توضیح کوتاه اختیاری.",
      "Desktop: Crossfade حدود 0.6s و action rail؛ Mobile: CTA ثابت.",
      "Header search-first برای کاتالوگ عمیق و Mega Menu گروه‌بندی‌شده.",
      "آبی #183E85، زرد #FFDB01، خاکستری #F2F2F2؛ Border/Background مهم‌تر از Shadow."
    ],
    mobile: [
      "زیر 991px Mobile bar برای Menu/Search فعال شود.",
      "Action rail مخفی و CTA لمس‌پذیر جایگزین شود.",
      "Grid در breakpointهای 480/768/992 تعداد ستون را کم کند.",
      "Mega Menu در موبایل Accordion گروه‌بندی‌شده باشد."
    ],
    product: [
      "Gallery و اطلاعات در ستون‌های جدا؛ عنوان، برند، توضیح کوتاه، Favorite و CTA.",
      "ویژگی‌های متوسط، توضیح Editorial بلند و Related products.",
      "تصویر دوم برای نمایش زاویه یا کاربرد محصول استفاده شود، نه تزئین بی‌هدف."
    ],
    avoid: ["Mega menu پوشاننده صفحه", "محصولات بسیار زیاد در DOM", "Accentهای ناسازگار", "وابستگی به نام یا ظاهر IKEA"]
  }
};

const PRODUCTS = {
  beraito: [["✏️","ست نوشت‌افزار رنگی"],["📒","دفتر برنامه‌ریزی"],["🎨","بسته نقاشی کودک"],["🎒","کوله سبک روزانه"]],
  cactus: [["👜","کیف چرمی دست‌دوز"],["👞","کفش رسمی چرم"],["🎒","کوله چرمی شهری"],["🧥","اکسسوری چرمی"]],
  deeyar: [["🏺","ظرف سفالی دست‌ساز"],["🧶","بافت هنری محلی"],["🪡","دوخت سنتی"],["🧵","پارچه نقش‌دار"]],
  ibolak: [["👗","پیراهن زنانه آزاد"],["👕","تیشرت مینیمال"],["👖","شلوار روزمره"],["👟","کتانی سبک"]],
  ikalajam: [["🛋️","کوسن بافت‌دار"],["☕","ماگ سرامیکی"],["🕯️","چراغ دکوراتیو"],["🪑","صندلی چوبی"]]
};

function pathTo(file) { return `${ROOT}/${file}`.replace(/\/\.\//g, "/"); }

function reviewBar(key, page) {
  const spec = SPECS[key];
  const other = page === "home" ? "product" : "home";
  return `<nav class="review-bar" aria-label="کنترل مرجع">
    <strong>${spec.name} · ${page === "home" ? "صفحه اصلی" : "صفحه محصول"}</strong>
    <a href="${pathTo("index.html")}">همه قالب‌ها</a>
    <a href="${pathTo(`pages/${key}-${other}.html`)}">${other === "home" ? "صفحه اصلی" : "صفحه محصول"}</a>
    <button type="button" data-spec-toggle>مشخصات دقیق این صفحه</button>
  </nav>`;
}

function specDrawer(key, page) {
  const s = SPECS[key];
  const list = (title, items) => `<h3>${title}</h3><ul>${items.map(x => `<li>${x}</li>`).join("")}</ul>`;
  return `<aside class="spec-drawer" data-spec-drawer>
    <button class="spec-close" type="button" data-spec-close aria-label="بستن">×</button>
    <h2>${s.name}</h2><p><code>${s.family}</code> · مرجع: ${s.brand}</p>
    <p><b>نکته:</b> ایموجی فقط جانشین کم‌حجم تصویر است. نسبت کادر، جایگاه، فاصله و رفتار Responsive بخشی از مشخصات قالب‌اند.</p>
    ${list("ساختار و ترتیب", s.layout)}
    ${list("اجزا و هویت دیداری", s.components)}
    ${page === "product" ? list("قرارداد صفحه محصول", s.product) : ""}
    ${list("رفتار موبایل", s.mobile)}
    ${list("موارد ممنوع", s.avoid)}
  </aside>`;
}

function media(emoji, cls = "", badge = "") {
  return `<div class="emoji-media ${cls}">${badge ? `<span class="badge">${badge}</span>` : ""}<span aria-hidden="true">${emoji}</span></div>`;
}

function cards(key, variant = "") {
  return PRODUCTS[key].map((p, i) => `<article class="product-card ${variant}">
    ${key === "ibolak" ? `<span class="wishlist">♡</span>` : ""}
    ${media(p[0], "", i === 1 ? "٪۲۰" : "")}
    ${key === "ikalajam" ? `<div class="action-rail">مشاهده سریع · افزودن به سبد</div>` : ""}
    <div class="product-info">
      ${key === "deeyar" ? `<p>ساخته‌شده در کارگاه محلی</p>` : ""}
      <div class="${key === "ibolak" ? "split-info" : ""}"><h3>${p[1]}</h3><div class="price"><del>۱٬۴۹۰٬۰۰۰</del> ۱٬۱۹۰٬۰۰۰ تومان</div></div>
      ${key === "ikalajam" ? `<p>توضیح کوتاه و اختیاری برای کاربرد محصول</p>` : ""}
    </div>
  </article>`).join("");
}

function serviceStrip() {
  return `<div class="container service-strip"><div class="service"><b>🚚</b>ارسال مطمئن</div><div class="service"><b>↩️</b>ضمانت بازگشت</div><div class="service"><b>💬</b>پشتیبانی</div><div class="service"><b>✓</b>تضمین اصالت</div></div>`;
}

function footer(key) {
  return `<footer class="site-footer"><div class="container footer-grid"><div><h3>${SPECS[key].name}</h3><p>این متن نمونه و قابل‌ویرایش است. نام، آدرس، شماره تماس و ادعاهای برند مرجع وارد قالب عمومی نمی‌شوند.</p></div><div><h3>راهنمای خرید</h3><ul><li>روش ثبت سفارش</li><li>ارسال و بازگشت</li><li>پرسش‌های متداول</li></ul></div><div><h3>دسترسی سریع</h3><ul><li>محصولات جدید</li><li>پرفروش‌ها</li><li>تماس با ما</li></ul></div><div><h3>اعتماد و ارتباط</h3><p>🔒 پرداخت امن<br>✉️ عضویت خبرنامه<br>◎ شبکه‌های اجتماعی</p></div></div></footer>`;
}

function standardHead(key, mode) {
  const s = SPECS[key];
  if (key === "beraito") return `<div class="utility-top"><div class="container utility"><span>راهنما · تماس · ایمیل</span><span>ارسال رایگان برای خرید منتخب</span></div></div><header><div class="container main-head"><div class="logo">قالب ۱</div><label class="search">⌕ <input aria-label="جست‌وجو" placeholder="جست‌وجو میان هزاران کالا"></label><div class="actions">♙ <span>حساب من</span> 🛒</div></div><div class="nav-shell"><nav class="container nav">همه دسته‌ها · پیشنهاد لحظه‌ای · لوازم تحریر · سرگرمی · هدیه · برندها</nav></div></header>`;
  if (key === "cactus") return `<div class="promo-strip">کمپین قابل‌ویرایش فروشگاه · متن ساختاری، نه نوشته داخل تصویر</div><header><div class="container main-head"><div class="logo">قالب ۲</div><label class="search">⌕ <input aria-label="جست‌وجو" placeholder="جست‌وجوی محصول"></label><div class="actions">حساب ♙ · سبد 🛒</div></div><nav class="container nav">زنانه · مردانه · کیف · کفش · اکسسوری · کالکشن‌ها</nav></header>`;
  if (key === "deeyar") return `<header><div class="container main-head"><div class="logo">قالب ۳</div><div class="actions">⌕ جست‌وجو · ♙ حساب · 🛒 سبد</div></div><nav class="container nav">تازه‌ها · صنایع‌دستی · خانه و دکور · هدیه · داستان ما · مجله</nav></header>`;
  if (key === "ibolak") return `<header><div class="container main-head"><div class="logo">قالب ۴</div><label class="search">⌕ <input aria-label="جست‌وجو" placeholder="جست‌وجوی استایل و محصول"></label><div class="actions">ورود ♙ · سبد 🛒</div></div><nav class="container nav">جدیدها · زنانه · مردانه · Beauty · Club · App · Instagram</nav></header>`;
  return `<div class="announce">اطلاعیه کوتاه و قابل‌ویرایش فروشگاه</div><div class="utility-top"><div class="container utility"><span>سفارش اختصاصی · پشتیبانی</span><span>شبکه‌های اجتماعی · پیگیری سفارش</span></div></div><header><div class="container main-head"><div class="logo">قالب ۵</div><label class="search">⌕ <input aria-label="جست‌وجو" placeholder="جست‌وجو در خانه، آشپزخانه و دکور"></label><div class="actions">حساب ♙ · سبد 🛒</div></div><div class="nav-shell"><nav class="container nav">همه محصولات · آشپزخانه · پذیرایی · دکور · روشنایی · نظم‌دهنده</nav></div></header>`;
}

function beraitoHome() {
  const quick = [["✏️","نوشت‌افزار"],["📚","کتاب"],["🎨","هنری"],["🧩","سرگرمی"],["🎁","هدیه"],["🎒","کیف"],["🖊️","اداری"],["⭐","برندها"]];
  return `${standardHead("beraito")}<main class="beraito"><h1 class="catalog-title">فروشگاه کاتالوگی و پیشنهادهای لحظه‌ای</h1><section class="container deal-hero">${media("🔥", "deal-main", "پیشنهاد لحظه‌ای")}<div class="deal-side">${media("🎯")} ${media("🎁")}</div></section><section class="section"><div class="container"><div class="section-head"><div><h2>دسته‌های سریع</h2><p>دسترسی فوری برای کاتالوگ بزرگ؛ تعداد و ترتیب از Builder قابل تنظیم است.</p></div><a href="#">مشاهده همه ←</a></div><div class="quick-grid">${quick.map(x=>`<div class="quick">${media(x[0])}<p>${x[1]}</p></div>`).join("")}</div></div></section>${serviceStrip()}<section class="section soft"><div class="container"><div class="section-head"><div><h2>پیشنهادهای امروز</h2><p>Renderer: square_centered_commerce · چگالی زیاد</p></div><a href="#">مشاهده همه ←</a></div><div class="product-grid">${cards("beraito")}</div></div></section><section class="section"><div class="container promo-grid">${["🎒","🎨","🧸","🖋️"].map(x=>media(x)).join("")}</div></section><section class="section soft"><div class="container"><div class="section-head"><h2>محصولات پرفروش</h2><a href="#">مشاهده همه ←</a></div><div class="product-grid">${cards("beraito")}</div></div></section></main>${footer("beraito")}`;
}

function cactusHome() {
  return `${standardHead("cactus")}<main class="cactus"><section class="hero-premium"><div class="hero-copy"><small>HERITAGE PREMIUM</small><h1>ساخته‌شده برای ماندن</h1><p>متن Campaign ساختاری و قابل ویرایش است. تصویر واقعی بعداً توسط فروشنده جایگزین این قاب می‌شود.</p><button class="cta">مشاهده کالکشن</button></div>${media("👜", "hero-product")}</section><section class="section"><div class="container"><div class="section-head"><div><h2>دسته‌های منتخب</h2><p>Portrait category row با شش دسته تصویری و فضای سفید زیاد.</p></div></div><div class="portrait-cats">${["👜","👞","🎒","👝","🧥","⌚"].map((x,i)=>`<div class="portrait-cat">${media(x)}<p>کالکشن ${i+1}</p></div>`).join("")}</div></div></section><section class="section soft"><div class="container"><div class="section-head"><div><h2>محصولات کمپین</h2><p>Renderer: premium_campaign · Overlay تخفیف و اقساط اختیاری.</p></div><a href="#">مشاهده همه ←</a></div><div class="product-grid">${cards("cactus")}</div></div></section><section class="section"><div class="container">${serviceStrip().replace('class="container service-strip"','class="service-strip"')}</div></section><section class="section"><div class="container"><div class="section-head"><h2>جدیدترین محصولات</h2></div><div class="product-grid">${cards("cactus")}</div></div></section></main>${footer("cactus")}`;
}

function deeyarHome() {
  return `${standardHead("deeyar")}<main class="deeyar"><section class="hero-editorial"><div class="hero-copy"><small>ARTISAN EDITORIAL</small><h1>هر محصول، یک قصه</h1><p>محصول، سازنده، منطقه و تاریخچه در یک روایت فروشگاهی پیوند می‌خورند.</p><button class="cta">کشف مجموعه</button></div>${media("🏺")}</section><section class="section"><div class="container"><div class="section-head"><div><h2>دسته‌های هنر ایرانی</h2><p>چهار بنر با عنوان Overlay؛ متن از تصویر جدا باقی می‌ماند.</p></div></div><div class="banner-grid">${["🏺","🧶","🪡","🧵"].map(x=>media(x)).join("")}</div></div></section><section class="section soft"><div class="container"><div class="section-head"><div><h2>تازه‌های کارگاه</h2><p>Renderer: artisan_story_card · Metadata سازنده اختیاری.</p></div><a href="#">همه محصولات ←</a></div><div class="product-grid">${cards("deeyar")}</div></div></section><section class="about-split">${media("👐")}<div class="about-copy"><small>داستان ما</small><h2>درباره سازندگان و مسیر خلق محصول</h2><p>این بخش یک Section مستقل، قابل جابه‌جایی و قابل خاموش‌کردن است. متن بلندتر، تصویر کارگاه و لینک ادامه داستان دارد.</p><button class="cta">ادامه داستان</button></div></section><section class="section"><div class="container"><div class="section-head"><div><h2>مجله و کارگاه‌ها</h2><p>Commerce و Storytelling در یک مسیر؛ Blog اجباری نیست.</p></div></div><div class="story-grid">${[["🧑‍🎨","گفت‌وگو با سازنده"],["🧶","از مواد اولیه تا محصول"],["🏡","چیدمان با هنر دست"]].map(x=>`<article class="story-card">${media(x[0])}<div><h3>${x[1]}</h3><p>خلاصه مقاله و دعوت به مطالعه</p></div></article>`).join("")}</div></div></section></main>${footer("deeyar")}`;
}

function ibolakHome() {
  return `${standardHead("ibolak")}<main class="ibolak"><div class="container story-rail">${["✨","👗","👕","👖","👟","👜","💄","🎁"].map((x,i)=>`<div class="story">${media(x)}<p>استوری ${i+1}</p></div>`).join("")}</div><section class="container hero-fashion"><div><small>MODERN FASHION</small><h1>استایل تازه، حرکت ساده</h1><p>Hero carousel با متن ساختاری، CTA و امکان اسلاید مستقل برای موبایل.</p><button class="cta">خرید کالکشن</button></div>${media("👗")}</section><section class="section"><div class="container"><div class="section-head"><div><h2>انتخاب بر اساس استایل</h2><p>Category tileهای عمودی و Editorial؛ عنوان فارسی و Label انگلیسی.</p></div></div><div class="category-tiles">${[["👗","DRESSES"],["👕","TOPS"],["👖","BOTTOMS"],["👟","SHOES"]].map(x=>`<article class="category-tile">${media(x[0])}<h3>${x[1]}</h3><p>دسته قابل‌ویرایش</p></article>`).join("")}</div></div></section><section class="section soft"><div class="container"><div class="section-head"><div><h2>جدیدترین استایل‌ها</h2><p>Renderer: fashion_portrait_gallery · تصویر 9:12 و Gallery چندتصویری.</p></div><a href="#">مشاهده همه ←</a></div><div class="product-grid">${cards("ibolak")}</div></div></section><section class="section"><div class="container"><div class="section-head"><h2>پیشنهادهای این هفته</h2></div><div class="product-grid">${cards("ibolak")}</div></div></section></main>${footer("ibolak")}`;
}

function ikalajamHome() {
  return `${standardHead("ikalajam")}<main class="ikalajam"><section class="hero-living"><div><small>NORDIC LIVING</small><h1>خانه‌ای آرام، انتخابی روشن</h1><p>Hero خنثی و Category-led؛ متن کوتاه، فضای سفید و CTA محدود.</p><button class="cta">مشاهده فضای نشیمن</button></div>${media("🛋️")}</section><section class="section">${serviceStrip()}</section><section class="section soft"><div class="container"><div class="section-head"><div><h2>تازه‌های خانه</h2><p>Renderer: catalog_second_image · Crossfade تصویر دوم و Action rail.</p></div><a href="#">مشاهده همه ←</a></div><div class="product-grid">${cards("ikalajam")}</div></div></section><section class="section"><div class="container banner-pair">${media("☕")} ${media("🕯️")}</div></section><section class="section"><div class="container"><div class="section-head"><h2>پرفروش‌های دکور</h2></div><div class="product-grid">${cards("ikalajam")}</div></div></section></main>${footer("ikalajam")}`;
}

function productPage(key) {
  const s = SPECS[key], product = PRODUCTS[key][0];
  const gallery = (key === "cactus" || key === "ibolak")
    ? `<div class="${key === "cactus" ? "premium-gallery" : "fashion-gallery"}"><div class="thumbs">${[product[0],"◫","◩","◧"].map(x=>media(x)).join("")}</div>${media(product[0],"gallery-main")}</div>`
    : `<div>${media(product[0],"gallery-main")}<div class="thumbs">${[product[0],"◫","◩","◧"].map(x=>media(x)).join("")}</div></div>`;
  const selector = key === "cactus" || key === "ibolak" ? `<div class="selector"><b>رنگ و سایز</b><div class="chips"><button class="chip">مشکی</button><button class="chip">قهوه‌ای</button><button class="chip">M</button><button class="chip">L</button></div></div>` : `<div class="selector"><b>گزینه محصول</b><div class="chips"><button class="chip">مدل ۱</button><button class="chip">مدل ۲</button></div></div>`;
  return `${standardHead(key,"product")}<main class="${key} ${key === "deeyar" ? "artisan-product" : ""}"><div class="container breadcrumb">خانه / دسته نمونه / ${product[1]}</div><section class="container product-detail">${gallery}<article class="product-panel"><span class="eyebrow">${s.family}</span><h1>${product[1]}</h1><p class="lead">توضیح نمونه محصول. محتوا از دیتای واقعی فروشگاه می‌آید و به برند مرجع وابسته نیست.</p><div class="price"><del>۱٬۴۹۰٬۰۰۰</del> ۱٬۱۹۰٬۰۰۰ تومان</div><div class="selectors">${selector}<div class="selector"><b>وضعیت</b><div class="chips"><span class="chip">موجود</span><span class="chip">ارسال ۲ روزه</span></div></div></div>${key === "ikalajam" ? `<div class="nordic-facts"><span>جنس<br><b>نمونه</b></span><span>ابعاد<br><b>متوسط</b></span><span>رنگ<br><b>طبیعی</b></span></div>` : ""}<div class="purchase-row"><button class="cta">افزودن به سبد خرید</button><input class="qty" aria-label="تعداد" value="۱"></div></article></section><section class="container detail-tabs"><article><h2>${key === "deeyar" ? "داستان محصول" : "توضیحات محصول"}</h2><p>${s.product[0]} ${s.product[1]}</p></article><article><h2>مشخصات و خدمات</h2><ul><li>داده‌ها از مدل محصول و Variant خوانده شوند.</li><li>تصویر انتخابی با Variant هماهنگ باشد.</li><li>CTA موبایل همیشه قابل لمس باشد.</li><li>محصولات مرتبط از renderer همین قالب استفاده کنند.</li></ul></article></section><section class="section soft"><div class="container"><div class="section-head"><h2>محصولات مرتبط</h2></div><div class="product-grid">${cards(key)}</div></div></section></main>${footer(key)}`;
}

function gallery() {
  return `<main class="gallery"><div class="container"><header class="gallery-intro"><div><span class="gallery-kicker">RastiSi · Lightweight Reference Kit</span><h1>پنج قالب، ده صفحه، بدون فایل سنگین</h1></div><p>ایموجی‌ها فقط جانشین تصویرند. تفاوت واقعی در ترکیب Header، Hero، Product Card، نسبت‌ها، چگالی، Motion، Mobile و صفحه محصول ثبت شده است.</p></header><section class="gallery-grid">${Object.entries(SPECS).map(([key,s])=>`<article class="gallery-card" style="--mini:${s.accent};--mini-bg:${s.miniBg}"><div class="miniature"><div class="emoji-line">${s.emojis}</div><div class="wire"><i></i><i></i><i></i><i></i></div></div><div class="gallery-body"><small>${s.number} · ${s.family}</small><h2>${s.name}</h2><p>${s.summary}</p><div class="gallery-links"><a href="${pathTo(`pages/${key}-home.html`)}">صفحه اصلی</a><a href="${pathTo(`pages/${key}-product.html`)}">صفحه محصول</a></div></div></article>`).join("")}</section></div></main>`;
}

function mount() {
  const page = document.body.dataset.page;
  if (page === "gallery") {
    document.getElementById("app").innerHTML = gallery();
    return;
  }
  const key = document.body.dataset.template;
  const home = {beraito:beraitoHome,cactus:cactusHome,deeyar:deeyarHome,ibolak:ibolakHome,ikalajam:ikalajamHome};
  const content = page === "home" ? home[key]() : productPage(key);
  document.getElementById("app").innerHTML = `${reviewBar(key,page)}${content}${specDrawer(key,page)}`;
  const drawer = document.querySelector("[data-spec-drawer]");
  document.querySelector("[data-spec-toggle]").addEventListener("click",()=>drawer.classList.add("open"));
  document.querySelector("[data-spec-close]").addEventListener("click",()=>drawer.classList.remove("open"));
}

mount();
