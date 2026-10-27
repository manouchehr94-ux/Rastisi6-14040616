"""Site Appearance Registry — الگویِ دقیقاً مشابهِ ``section_registry.py``:
یک دیکشنریِ ثابتِ پایتونی، پلتفرم‌محور، نسخه‌بندی‌نشده در دیتابیس. انتخابِ
مرچنت (کدام Template/Palette فعال است) در ``StorefrontLayoutVersion.appearance_config``
ذخیره می‌شود (Store-owned، Draft/Publish-aware)؛ خودِ تعریفِ هر Template/Palette
اینجا Store-agnostic و مشترکِ کلِ پلتفرم است — دقیقاً همان تفکیکِ مسئولیتی
که ``SECTION_REGISTRY`` بینِ «کدام نوع section وجود دارد» (اینجا) و
«کدام نمونه در این صفحه است» (دیتابیس) دارد.

چرا یک دیکشنریِ کد به‌جایِ یک مدلِ دیتابیسی: Templateها/Paletteها محتوایِ
طراحی‌شده و مرورشده‌ی خودِ تیمِ پلتفرم‌اند (نه چیزی که مرچنت بسازد) — دقیقاً
مثلِ SECTION_REGISTRY، نسخه‌بندی/بازبینیِ آن‌ها با Code Review و git history
اتفاق می‌افتد، نه با یک migration/admin UI جداگانه. اضافه‌کردنِ Templateی
جدید یعنی یک ورودیِ جدید اینجا (تک‌تکِ فروشگاه‌ها بدونِ migration بلافاصله
می‌توانند آن را انتخاب کنند).

COLOR RESOLUTION CONTRACT — the ONE token-resolution authority
==============================================================
Every colour the storefront paints resolves through this module (``resolve_colors`` → ``resolve_theme_roles`` →
``resolve_section_tones``; accessible *usage* colours are then derived from the result in ``accessible_colors``), for Preview and
Published alike. Precedence, lowest → highest, per property category:

  1. Engine / component defaults ........ ``DEFAULT_COLORS`` and the CSS fallbacks in ``tokens.css`` (a Store with no palette).
  2. Ready Template baseline ............ the template's recipe writes ``palette_slug`` (+ any overrides) into the Draft's
                                          ``appearance_config`` and snapshots it; it is a *starting configuration*, never a layer
                                          that is re-applied on top of later choices ("reset to baseline" restores it on request).
  3. Selected palette ................... ``PaletteDefinition.colors`` (8 base colours), ``theme_roles`` (region roles) and
                                          ``section_tones``; a role the palette does not define is derived from the final base colours.
  4. Merchant global overrides .......... ``appearance_config.color_overrides`` (base colours) and ``theme_overrides`` (region roles).
                                          Base-colour overrides REACH every role that is derived from, or is identical to, that base
                                          colour in the palette (so overriding ``surface`` repaints header / nav / card surfaces);
                                          a role the palette makes deliberately different keeps the palette value until the merchant
                                          sets that role itself (``theme_overrides`` always wins over everything below it).
  5. Explicit section / component ....... ``StorefrontSection.settings`` (Background, internal card Surface, ink, campaign panel,
                                          borders) — stored on the section, so a global palette change never rewrites them; they sit
                                          above every global layer for that section only.

Switching the palette changes the INHERITED colours (layer 3) only: the merchant's explicit global overrides (layer 4) and every
layer-5 value survive by default. The one thing a palette switch does drop is colours that were never a merchant choice — values
a Ready Template installed and the merchant did not modify, and bootstrap carry-over. Origin is decided PER PROPERTY by comparing each
stored value with the template baseline snapshot (``override_origins``), for base colours and region colours alike, so changing one
template colour makes only that colour the merchant's.
Clearing ONE override (``appearance.update`` with a ``null`` value) returns just that property to the layer below it; clearing ALL
global overrides is the explicit, labelled action ``appearance.update`` ``clear_global_color_overrides`` — never a side effect. A store-specific custom palette is exactly ``palette_slug`` + ``color_overrides`` /
``theme_overrides`` on that Store's own Draft/Published version: it never mutates ``PALETTE_REGISTRY`` and is invisible to other Stores."""

from __future__ import annotations

import dataclasses

DENSITY_CHOICES = ("compact", "normal", "relaxed")
MOTION_CHOICES = ("none", "subtle", "dynamic")
BUTTON_STYLE_CHOICES = ("filled", "soft", "outline")
TYPE_SCALE_CHOICES = ("compact", "normal", "large")

#: رفتارِ تصویرِ کارتِ محصول — کنترلِ مستقیمِ تاجر، مستقل از Template؛
#: پیش‌فرض‌ها دقیقاً معادلِ رفتارِ سخت‌کدشده‌یِ قبل از این چکپوینت
#: هستند (``object-fit:cover``، بزرگ‌نماییِ ملایم روی hover).
IMAGE_FIT_CHOICES = ("cover", "contain")
IMAGE_HOVER_CHOICES = ("none", "zoom")

#: Phase 8 P0-7 — این ۵ فیلدِ ساختاری قبلاً فقط از طریقِ انتخابِ یک
#: Templateِ کامل قابلِ‌تغییر بودند (نگاه کنید به TemplateDefinition
#: پایین). حالا مستقیماً در پنلِ «تنظیماتِ بیشتر» به‌عنوانِ کنترل‌هایِ
#: مستقل در دسترس‌اند — این‌ها فقط enum بستهٔ مجازِ همان مقادیری هستند
#: که Templateهایِ موجود از قبل استفاده می‌کنند، نه محدوده‌ی جدیدی.
SITE_CONTENT_WIDTH_CHOICES = (1100, 1200, 1320, 1500, 1800)

#: V5 — style of every section heading (``.sec-head``), a SPARSE structural key (absent == ``default``, the historical heading).
#: One CSS rule-set keyed on ``html[data-sfb-heading]`` serves every section that renders ``.sec-head``; no per-section markup.
SITE_HEADING_STYLE_CHOICES = ("default", "centered", "centered_rule", "underline", "plain")
SITE_GRID_DENSITY_CHOICES = (3, 4, 5, 6)
SITE_CARD_SHADOW_CHOICES = ("none", "soft", "strong")
SITE_CARD_HOVER_CHOICES = ("none", "lift", "zoom")
SITE_HERO_STYLE_CHOICES = ("wide", "tall", "split")

#: فونت‌هایِ مجاز — مجموعه‌ی کوچک و کیوریت‌شده، هرکدام واقعاً برایِ
#: فارسی/RTL مناسب (نه هر فونتِ دلخواه؛ طبقِ الزامِ صریحِ کار: «مرچنت فونت
#: را با نام انتخاب کند، نه CSS خام آپلود کند»).
FONT_CHOICES = ("Vazirmatn", "Estedad", "Noto Sans Arabic", "Lalezar", "Tahoma", "Arial", "Georgia")

#: مقیاسِ سلسله‌مراتبِ تایپوگرافی — پنج نقشِ معنادار (نه اندازه‌یِ دلخواه
#: در هر جای CSS): عنوانِ بخش، متنِ عادی، نامِ محصول، قیمت، متنِ کم‌رنگ.
#: ``normal`` دقیقاً همانِ مقادیرِ سخت‌کدشده‌یِ قبل از این چکپوینت است
#: (``.sec-head h2``=19px، ``body``=14px، ``.pcard .name``=13px،
#: ``.pcard .price .now``=15px، متنِ کم‌رنگ=11px) — یعنی انتخابِ آن هیچ
#: فروشگاهی را تغییر نمی‌دهد.
TYPE_SCALE_SIZES = {
    "compact": {"heading": 17, "body": 13, "product_name": 12, "price": 14, "muted": 10},
    "normal": {"heading": 19, "body": 14, "product_name": 13, "price": 15, "muted": 11},
    "large": {"heading": 22, "body": 15, "product_name": 14, "price": 17, "muted": 12},
}


def resolve_typography(type_scale: str) -> dict:
    return TYPE_SCALE_SIZES.get(type_scale) or TYPE_SCALE_SIZES["normal"]


@dataclasses.dataclass(frozen=True)
class PaletteDefinition:
    slug: str
    name_fa: str
    group_fa: str
    colors: dict[str, str]  # هشت رنگ پایه و قابل‌ویرایش
    # نقش‌های منطقه‌ایِ کل سایت. پالت‌های قدیمی لازم نیست این‌ها را داشته
    # باشند؛ resolve_theme_roles از هشت رنگ پایه مقادیر امن مشتق می‌کند.
    theme_roles: dict[str, str] | None = None
    # پنج رنگ قوی برای ریل‌های رنگی/سطوح تبلیغاتی.
    section_tones: tuple[str, str, str, str, str] | None = None


@dataclasses.dataclass(frozen=True)
class TemplateDefinition:
    slug: str
    name_fa: str
    group_fa: str
    description_fa: str
    #: مقادیرِ پیشنهادیِ Templateهای appearance — مرچنت می‌تواند این‌ها را
    #: در appearance_config.color_overrides/font/... دستی override کند؛
    #: این‌ها فقط پیش‌فرضِ اعمال‌شده هنگامِ انتخابِ Template‌اند، نه یک
    #: محدودیتِ اجباری.
    font: str
    radius: int
    button_radius: int
    button_style: str
    density: str
    motion: str
    #: مقیاسِ پیش‌فرضِ تایپوگرافیِ این Template — دقیقاً مثلِ density/motion:
    #: فقط پیش‌فرضِ اعمال‌شده هنگامِ انتخابِ Template است، مرچنت می‌تواند
    #: در appearance_config.type_scale دستی override کند.
    type_scale: str
    #: فیلدهایِ *ساختاریِ* واقعی — این‌ها هستند که Template را از یک
    #: «Paletteِ دیگر» متمایز می‌کنند (طبقِ الزامِ صریحِ کار: «Template
    #: صرفاً رنگ نیست»). هر کدام مستقیماً یک CSS custom property می‌شود
    #: (``--sfb-content-width`` و...) که در تمپلیت‌هایِ CSS موجود
    #: (``home.css``/``product_card.css``) مصرف می‌شود — نه فورکِ کاملِ
    #: تمپلیت به‌ازای هر Template.
    content_width: int  # px — عرضِ حداکثرِ محتوا (.wrap)
    grid_density: int  # تعدادِ ستونِ پیش‌فرضِ گریدِ محصول در دسکتاپ
    card_shadow: str  # "none" | "soft" | "strong"
    card_hover: str  # "none" | "lift" | "zoom"
    hero_style: str  # "wide" | "tall" | "split"
    #: نمونه‌رنگ‌هایِ گالری (برایِ mini-preview) — لزوماً همان پالتِ فعلیِ
    #: مرچنت نیست؛ فقط برایِ نمایشِ کارتِ گالری.
    swatch: list[str]


# ---------------------------------------------------------------- پالت‌ها

PALETTE_REGISTRY: dict[str, PaletteDefinition] = {}
TEMPLATE_REGISTRY: dict[str, TemplateDefinition] = {}


def register_palette(definition: PaletteDefinition) -> None:
    PALETTE_REGISTRY[definition.slug] = definition


def register_template(definition: TemplateDefinition) -> None:
    TEMPLATE_REGISTRY[definition.slug] = definition


def get_palette(slug: str) -> PaletteDefinition | None:
    return PALETTE_REGISTRY.get(slug)


def get_template(slug: str) -> TemplateDefinition | None:
    return TEMPLATE_REGISTRY.get(slug)


def list_palettes() -> list[PaletteDefinition]:
    return list(PALETTE_REGISTRY.values())


def list_templates() -> list[TemplateDefinition]:
    return list(TEMPLATE_REGISTRY.values())


#: پایه‌یِ رنگ وقتی ``palette_slug`` انتخاب نشده (None) — دقیقاً همان
#: مقادیرِ پیش‌فرضِ فعلیِ ``ShopSettings`` (بخشِ «هویت بصری»،
#: ``apps/core/models.py``) به‌علاوه‌یِ ``border``ی معادلِ فرمولِ derived
#: فعلی (``mix_hex(text, surface, 0.12)`` با این دو رنگ) — یعنی
#: فروشگاهی که هنوز هیچ Palette انتخاب نکرده، دقیقاً همان چیزی را
#: می‌بیند که امروز می‌بیند.
DEFAULT_COLORS = {
    "primary": "#6D28D9", "secondary": "#7C3AED", "accent": "#FF4D77",
    "background": "#F7F5FC", "surface": "#FFFFFF", "text": "#241C3A",
    "muted": "#8B86A3", "border": "#ECE8F6",
}


def resolve_colors(appearance_config: dict) -> dict:
    """رنگ‌هایِ نهاییِ اثرگذار: پالتِ پایه + overrideهایِ دستی مرچنت."""
    palette_slug = appearance_config.get("palette_slug")
    palette = get_palette(palette_slug) if palette_slug else None
    base = dict(palette.colors) if palette is not None else dict(DEFAULT_COLORS)
    overrides = appearance_config.get("color_overrides") or {}
    return {**base, **overrides}


THEME_ROLE_KEYS = (
    "header_bg", "header_text",
    "nav_bg", "nav_text",
    "card_bg",
    "footer_bg", "footer_text",
    "price",
)

#: The base colour each region role is derived from when the palette does not define the role (and the colour a palette role
#: "follows" when it is identical to it). Single source for both the derivation and the merchant-override propagation below.
ROLE_BASE_COLOR = {
    "header_bg": "surface", "header_text": "text",
    "nav_bg": "surface", "nav_text": "text",
    "card_bg": "surface",
    "footer_bg": "text", "footer_text": "surface",
    "price": "accent",
}


def _same_hex(a, b) -> bool:
    return isinstance(a, str) and isinstance(b, str) and a.strip().upper() == b.strip().upper()


def _palette_of(appearance_config: dict):
    slug = appearance_config.get("palette_slug")
    return get_palette(slug) if slug else None


def _palette_base_colors(appearance_config: dict) -> dict:
    palette = _palette_of(appearance_config)
    return dict(palette.colors) if palette is not None else dict(DEFAULT_COLORS)


def _derived_roles(colors: dict) -> dict[str, str]:
    return {role: colors[base] for role, base in ROLE_BASE_COLOR.items()}


def _palette_roles(appearance_config: dict) -> dict[str, str]:
    """Region roles at precedence layers 3+4a: derived from the final base colours, replaced by the palette's explicit roles —
    except a palette role that is just its own base colour keeps FOLLOWING that base colour when the merchant overrode it."""
    colors = resolve_colors(appearance_config)
    palette = _palette_of(appearance_config)
    roles = _derived_roles(colors)
    if palette is not None and palette.theme_roles:
        base = _palette_base_colors(appearance_config)
        overrides = appearance_config.get("color_overrides") or {}
        for role, value in palette.theme_roles.items():
            base_key = ROLE_BASE_COLOR.get(role)
            if base_key in overrides and _same_hex(value, base.get(base_key)):
                continue  # the palette never meant this role to differ from its base colour
            roles[role] = value
    return roles


def resolve_theme_roles(appearance_config: dict) -> dict[str, str]:
    """رنگ‌های ناحیه‌ایِ کل فروشگاه — لایه‌های ۳ و ۴ از «COLOR RESOLUTION CONTRACT» بالا.

    نقش‌های پایه از رنگ‌های نهاییِ پالت (بعد از overrideهای مرچنت) مشتق می‌شوند؛ پالت‌های «تم کامل» می‌توانند نقش‌ها را دقیق‌تر
    تعریف کنند؛ در آخر ``theme_overrides`` مرچنت بالاتر از همه می‌نشیند. هیچ CSS/Store-specific branch لازم نیست."""
    overrides = appearance_config.get("theme_overrides") or {}
    return {**_palette_roles(appearance_config), **overrides}


def resolve_section_tones(appearance_config: dict) -> tuple[str, str, str, str, str]:
    """پنج tone سراسری برایِ ردیف‌ها/سطوح رنگی.

    toneها فقط به ``primary``/``secondary``/``accent`` وابسته‌اند: اگر Palette toneهای کیوریت‌شده داشته باشد و مرچنت هیچ‌کدام از این
    سه رنگ را override نکرده باشد، همان‌ها استفاده می‌شوند (override کردنِ ``surface`` یا ``text`` toneهای کیوریت‌شده را از بین
    نمی‌برد). در غیر این صورت toneها از رنگ‌های نهاییِ همان فروشگاه مشتق می‌شوند؛ بنابراین شخصی‌سازیِ دستی هم قابل‌پیش‌بینی است.
    """
    palette = _palette_of(appearance_config)
    overrides = appearance_config.get("color_overrides") or {}
    if palette is not None and palette.section_tones and not (set(overrides) & {"primary", "secondary", "accent"}):
        return palette.section_tones

    from apps.core.color_utils import mix_hex

    colors = resolve_colors(appearance_config)
    return (
        colors["accent"],
        colors["primary"],
        colors["secondary"],
        mix_hex(colors["primary"], colors["accent"], 0.45),
        mix_hex(colors["secondary"], colors["accent"], 0.45),
    )


OVERRIDE_GROUPS = ("color_overrides", "theme_overrides")


def override_origins(appearance_config: dict, baseline_snapshot: dict | None = None) -> dict[str, dict[str, str]]:
    """Per-PROPERTY origin of every stored global override: ``{group: {key: "template" | "carry_over" | "merchant"}}``.

    ``color_overrides_customized`` is ONE boolean and cannot say which colours the merchant touched, so the origin of each stored
    value comes from comparing it with the Ready Template baseline snapshot recorded at install (``template_baseline_snapshot
    ["appearance"]``): a value identical to what the template installed for that key is ``template``; anything else is the
    merchant's — except a base colour that is not in the baseline while the merchant has never customised base colours, which is
    ``carry_over`` (bootstrap mirror of the Store's legacy colours: never a deliberate choice). No new stored state."""
    installed = (baseline_snapshot or {}).get("appearance") or {}
    customized = bool(appearance_config.get("color_overrides_customized"))
    origins: dict[str, dict[str, str]] = {}
    for group in OVERRIDE_GROUPS:
        stored = appearance_config.get(group) or {}
        template_values = installed.get(group) or {}
        origins[group] = {}
        for key, value in stored.items():
            if key in template_values and _same_hex(value, template_values[key]):
                origins[group][key] = "template"
            elif group == "color_overrides" and not customized:
                origins[group][key] = "carry_over"
            else:
                origins[group][key] = "merchant"
    return origins


def merchant_overrides(appearance_config: dict, baseline_snapshot: dict | None = None) -> dict[str, dict[str, str]]:
    """The overrides that are the MERCHANT'S (the ones a palette switch or a template switch must keep)."""
    origins = override_origins(appearance_config, baseline_snapshot)
    return {
        group: {k: v for k, v in (appearance_config.get(group) or {}).items() if origins[group].get(k) == "merchant"}
        for group in OVERRIDE_GROUPS
    }


def resolve_color_provenance(appearance_config: dict, baseline_snapshot: dict | None = None) -> dict:
    """Where every global colour comes from — for the Studio's "inherited vs overridden" display and per-property reset.

    ``colors`` (8 base colours) and ``roles`` (8 region roles), each ``{key: {"value", "default", "source", "stored"}}`` where
    ``default`` is what the property resolves to WITHOUT its stored override (the value a reset returns it to), ``stored`` says an
    override is stored for it, and ``source`` is ``"override"`` (the merchant's own), ``"template"`` (installed by the Ready Template
    and not modified), ``"carry_over"`` (legacy Store colour mirror), ``"palette"`` (selected palette defines it) or ``"default"`` /
    ``"derived"`` (engine default / derived from the base colours). The origin of each stored value is per property
    (``override_origins``)."""
    palette = _palette_of(appearance_config)
    base = _palette_base_colors(appearance_config)
    color_overrides = appearance_config.get("color_overrides") or {}
    theme_overrides = appearance_config.get("theme_overrides") or {}
    origins = override_origins(appearance_config, baseline_snapshot)
    source_of = {"merchant": "override", "template": "template", "carry_over": "carry_over"}

    colors = {}
    for key, default in base.items():
        stored = key in color_overrides  # a stored override is explicit even if it now equals the palette's
        colors[key] = {
            "value": color_overrides[key] if stored else default,
            "default": default,
            "stored": stored,
            "source": source_of[origins["color_overrides"][key]] if stored else ("palette" if palette is not None else "default"),
        }

    no_role_override = {**appearance_config, "theme_overrides": {}}
    inherited = resolve_theme_roles(no_role_override)
    explicit = (
        {role for role, value in (palette.theme_roles or {}).items() if _same_hex(value, inherited.get(role))}
        if palette is not None else set()
    )  # roles the palette really defines (a role following an overridden base colour is "derived")
    roles = {}
    for role in THEME_ROLE_KEYS:
        stored = role in theme_overrides
        roles[role] = {
            "value": theme_overrides[role] if stored else inherited[role],
            "default": inherited[role],
            "stored": stored,
            "source": source_of[origins["theme_overrides"][role]] if stored else ("palette" if role in explicit else "derived"),
        }
    return {"colors": colors, "roles": roles}


# ---------------------------------------------------------------- تم‌های کامل
#
# این‌ها «صرفاً سه رنگ برند» نیستند: هر تم پس‌زمینه‌ی صفحه، سطح کارت،
# هدر/منو، فوتر، قیمت و پنج tone ریل‌های رنگی را با هم تعریف می‌کند.
# مرچنت بعد از انتخاب همچنان می‌تواند هر نقش را جداگانه override کند.
_FULL_SITE_THEME_DATA = [
    {
        "slug": "theme-midnight-electric", "name": "شب الکتریکی", "group": "تم کامل",
        "colors": {
            "primary": "#315CFF", "secondary": "#7C3AED", "accent": "#22D3EE",
            "background": "#060A16", "surface": "#111827", "text": "#F8FAFC",
            "muted": "#94A3B8", "border": "#263247",
        },
        "roles": {
            "header_bg": "#070B18", "header_text": "#F8FAFC",
            "nav_bg": "#0B1120", "nav_text": "#E2E8F0",
            "card_bg": "#111827", "footer_bg": "#050814",
            "footer_text": "#CBD5E1", "price": "#A3E635",
        },
        "tones": ("#315CFF", "#7C3AED", "#0891B2", "#4F46E5", "#0F766E"),
    },
    {
        "slug": "theme-black-gold", "name": "مشکی طلایی", "group": "تم کامل",
        "colors": {
            "primary": "#D4AF37", "secondary": "#8F6B16", "accent": "#F59E0B",
            "background": "#070707", "surface": "#151515", "text": "#FFE76A",
            "muted": "#C6B86A", "border": "#3A3218",
        },
        "roles": {
            "header_bg": "#050505", "header_text": "#FFE76A",
            "nav_bg": "#0D0D0D", "nav_text": "#F5E6A8",
            "card_bg": "#171717", "footer_bg": "#030303",
            "footer_text": "#E8D98D", "price": "#FFD54A",
        },
        "tones": ("#D4AF37", "#8F6B16", "#B7791F", "#6B4F13", "#A16207"),
    },
    {
        "slug": "theme-navy-lime", "name": "سرمه‌ای لیمویی", "group": "تم کامل",
        "colors": {
            "primary": "#84CC16", "secondary": "#2563EB", "accent": "#A3E635",
            "background": "#07111F", "surface": "#0F1B2D", "text": "#F1F5F9",
            "muted": "#9FB0C4", "border": "#20334C",
        },
        "roles": {
            "header_bg": "#06101D", "header_text": "#F8FAFC",
            "nav_bg": "#0A1626", "nav_text": "#DCE7F3",
            "card_bg": "#101F32", "footer_bg": "#040C16",
            "footer_text": "#D5E2EF", "price": "#BEF264",
        },
        "tones": ("#65A30D", "#2563EB", "#0EA5E9", "#4D7C0F", "#1D4ED8"),
    },
    {
        "slug": "theme-graphite-orange", "name": "زغالی نارنجی", "group": "تم کامل",
        "colors": {
            "primary": "#F97316", "secondary": "#EA580C", "accent": "#FBBF24",
            "background": "#111315", "surface": "#1D2024", "text": "#F8FAFC",
            "muted": "#A8ADB4", "border": "#33383F",
        },
        "roles": {
            "header_bg": "#0D0F11", "header_text": "#FFFFFF",
            "nav_bg": "#171A1E", "nav_text": "#F3F4F6",
            "card_bg": "#20242A", "footer_bg": "#090B0D",
            "footer_text": "#D7DBE0", "price": "#FDBA74",
        },
        "tones": ("#F97316", "#C2410C", "#F59E0B", "#9A3412", "#EA580C"),
    },
    {
        "slug": "theme-purple-neon", "name": "بنفش نئونی", "group": "تم کامل",
        "colors": {
            "primary": "#8B5CF6", "secondary": "#D946EF", "accent": "#22D3EE",
            "background": "#0D0718", "surface": "#1A102B", "text": "#FAF5FF",
            "muted": "#B9A7CF", "border": "#382654",
        },
        "roles": {
            "header_bg": "#090412", "header_text": "#FAF5FF",
            "nav_bg": "#140B22", "nav_text": "#F3E8FF",
            "card_bg": "#1C1230", "footer_bg": "#07030E",
            "footer_text": "#E9D5FF", "price": "#67E8F9",
        },
        "tones": ("#8B5CF6", "#D946EF", "#0891B2", "#7E22CE", "#C026D3"),
    },
    {
        "slug": "theme-crimson-charcoal", "name": "زرشکی زغالی", "group": "تم کامل",
        "colors": {
            "primary": "#E11D48", "secondary": "#9F1239", "accent": "#FB7185",
            "background": "#120A0D", "surface": "#211217", "text": "#FFF1F2",
            "muted": "#C7A7B0", "border": "#46232E",
        },
        "roles": {
            "header_bg": "#0E0709", "header_text": "#FFF1F2",
            "nav_bg": "#190D11", "nav_text": "#FFE4E6",
            "card_bg": "#24151A", "footer_bg": "#0A0507",
            "footer_text": "#FBCFE8", "price": "#FDA4AF",
        },
        "tones": ("#E11D48", "#BE123C", "#9F1239", "#F43F5E", "#881337"),
    },
    {
        "slug": "theme-forest-cream", "name": "جنگل و کرم", "group": "تم کامل",
        "colors": {
            "primary": "#2F855A", "secondary": "#4D7C0F", "accent": "#D69E2E",
            "background": "#F3F0E6", "surface": "#FFFDF7", "text": "#17352B",
            "muted": "#6B7B71", "border": "#D8D5C9",
        },
        "roles": {
            "header_bg": "#17352B", "header_text": "#FFF8E7",
            "nav_bg": "#23483A", "nav_text": "#FFF8E7",
            "card_bg": "#FFFDF7", "footer_bg": "#112A21",
            "footer_text": "#F5EEDB", "price": "#B7791F",
        },
        "tones": ("#2F855A", "#4D7C0F", "#B7791F", "#276749", "#657A33"),
    },
    {
        "slug": "theme-cobalt-snow", "name": "کبالت و سفید", "group": "تم کامل",
        "colors": {
            "primary": "#1D4ED8", "secondary": "#2563EB", "accent": "#E11D48",
            "background": "#EEF4FF", "surface": "#FFFFFF", "text": "#10213D",
            "muted": "#60708A", "border": "#C9D7EE",
        },
        "roles": {
            "header_bg": "#0F2A5F", "header_text": "#FFFFFF",
            "nav_bg": "#163B82", "nav_text": "#F8FAFC",
            "card_bg": "#FFFFFF", "footer_bg": "#0B1F46",
            "footer_text": "#E5EEFF", "price": "#DC2626",
        },
        "tones": ("#1D4ED8", "#2563EB", "#0EA5E9", "#4338CA", "#0369A1"),
    },
    {
        "slug": "theme-terracotta-cream", "name": "تراکوتا و کرم", "group": "تم کامل",
        "colors": {
            "primary": "#B4533A", "secondary": "#D97757", "accent": "#D59A2A",
            "background": "#F8EEE5", "surface": "#FFF9F3", "text": "#3C241C",
            "muted": "#856A60", "border": "#E3CFC1",
        },
        "roles": {
            "header_bg": "#6F3225", "header_text": "#FFF8F0",
            "nav_bg": "#8B4433", "nav_text": "#FFF8F0",
            "card_bg": "#FFF9F3", "footer_bg": "#4B241B",
            "footer_text": "#F7E7DC", "price": "#A63D24",
        },
        "tones": ("#B4533A", "#D97757", "#D59A2A", "#8C3F2E", "#C26A47"),
    },
    {
        "slug": "theme-sakura-ink", "name": "ساکورا و جوهر", "group": "تم کامل",
        "colors": {
            "primary": "#DB2777", "secondary": "#7C3AED", "accent": "#F472B6",
            "background": "#FFF1F6", "surface": "#FFFFFF", "text": "#2D1930",
            "muted": "#8D6B83", "border": "#F0CBDD",
        },
        "roles": {
            "header_bg": "#2D1930", "header_text": "#FFF1F6",
            "nav_bg": "#44213E", "nav_text": "#FFF1F6",
            "card_bg": "#FFFFFF", "footer_bg": "#241225",
            "footer_text": "#FCE7F3", "price": "#BE185D",
        },
        "tones": ("#DB2777", "#7C3AED", "#F472B6", "#A21CAF", "#BE185D"),
    },
    {
        "slug": "theme-ice-cyan", "name": "یخی فیروزه‌ای", "group": "تم کامل",
        "colors": {
            "primary": "#0891B2", "secondary": "#0EA5E9", "accent": "#14B8A6",
            "background": "#ECFEFF", "surface": "#FFFFFF", "text": "#12323A",
            "muted": "#62838A", "border": "#BDE7EC",
        },
        "roles": {
            "header_bg": "#0E7490", "header_text": "#ECFEFF",
            "nav_bg": "#0891B2", "nav_text": "#F0FDFA",
            "card_bg": "#FFFFFF", "footer_bg": "#164E63",
            "footer_text": "#CFFAFE", "price": "#0F766E",
        },
        "tones": ("#0891B2", "#0EA5E9", "#14B8A6", "#0E7490", "#0369A1"),
    },
    {
        "slug": "theme-chocolate-mint", "name": "شکلاتی نعنایی", "group": "تم کامل",
        "colors": {
            "primary": "#7C4A2D", "secondary": "#2A9D8F", "accent": "#E9C46A",
            "background": "#F5EFE8", "surface": "#FFFDF9", "text": "#33251F",
            "muted": "#7D6B61", "border": "#DED2C8",
        },
        "roles": {
            "header_bg": "#3D2B24", "header_text": "#FFF8EC",
            "nav_bg": "#594034", "nav_text": "#FFF8EC",
            "card_bg": "#FFFDF9", "footer_bg": "#2B1D18",
            "footer_text": "#F4E8D7", "price": "#C17B16",
        },
        "tones": ("#7C4A2D", "#2A9D8F", "#C17B16", "#5F3622", "#238276"),
    },
]

for _theme in _FULL_SITE_THEME_DATA:
    register_palette(PaletteDefinition(
        slug=_theme["slug"],
        name_fa=_theme["name"],
        group_fa=_theme["group"],
        colors=_theme["colors"],
        theme_roles=_theme["roles"],
        section_tones=_theme["tones"],
    ))
del _theme

# ---------------------------------------------------------------- پالت‌های آماده

#: هر ۸ کلید حاضر است — دقیقاً همان audit شده‌یِ ``APPEARANCE_COLOR_KEYS``
#: (``models.py``)؛ گروه‌بندی (``group_fa``) فقط برایِ فیلترِ گالری است،
#: هیچ اثرِ رفتاری ندارد.
_PALETTE_DATA = [
    ("violet-pop", "بنفش مدرن", "مدرن", "#6C3DF0", "#F34F74", "#FFB020", "#FFFFFF", "#F7F7FB", "#1F2430", "#747B8A", "#E5E7EF"),
    ("digired", "قرمز فروشگاهی", "پرفروش", "#E82C4C", "#FF6B6B", "#FFB300", "#FFFFFF", "#F7F7F8", "#202124", "#71717A", "#E5E7EB"),
    ("ocean", "آبی حرفه‌ای", "سرد", "#1769E0", "#00A8E8", "#FFB703", "#F8FBFF", "#FFFFFF", "#14213D", "#667085", "#DDE7F2"),
    ("forest", "سبز طبیعی", "طبیعی", "#167A5B", "#62A87C", "#D99B2B", "#FAFCF8", "#FFFFFF", "#17352B", "#6C7B73", "#DDE8E1"),
    ("luxury-black", "مشکی لوکس", "لوکس", "#171717", "#C9A227", "#C9A227", "#F8F6F1", "#FFFFFF", "#111111", "#777064", "#DED8CC"),
    ("rose", "رز بوتیک", "گرم", "#B84A6B", "#E9A6B8", "#C58B48", "#FFF8FA", "#FFFFFF", "#3A2630", "#8E747E", "#F0DCE3"),
    ("terracotta", "تراکوتا", "گرم", "#B55239", "#E69A75", "#D3A13B", "#FFF9F5", "#FFFFFF", "#3B2923", "#8A6F64", "#EEDFD8"),
    ("amber", "کهربایی", "گرم", "#C47A00", "#F1B83B", "#DC4C3F", "#FFFBF2", "#FFFFFF", "#33260D", "#7F7257", "#EEE3C7"),
    ("mint", "نعنایی", "طبیعی", "#128C7E", "#5ED6C5", "#FF8A5B", "#F3FCFA", "#FFFFFF", "#143B37", "#66817D", "#D7EBE7"),
    ("olive", "زیتونی", "طبیعی", "#657A33", "#A8B96B", "#D09A32", "#FBFCF5", "#FFFFFF", "#2D3420", "#78806A", "#E4E8D7"),
    ("navy", "سرمه‌ای", "سرد", "#1D3557", "#457B9D", "#E9A23B", "#F7FAFC", "#FFFFFF", "#142033", "#677486", "#DCE3EA"),
    ("cyan", "فیروزه‌ای", "سرد", "#007C91", "#36C2D0", "#FF8D4D", "#F3FBFC", "#FFFFFF", "#15363C", "#668087", "#D6E9EC"),
    ("lavender", "یاسی آرام", "نرم", "#7565D6", "#C4B5FD", "#EE8A9A", "#FAF9FF", "#FFFFFF", "#292540", "#7E7896", "#E7E3F3"),
    ("peach", "هلویی نرم", "نرم", "#D86F52", "#F7B89C", "#B89442", "#FFF9F6", "#FFFFFF", "#402A24", "#8B756E", "#F0DED6"),
    ("sage", "سیج مینیمال", "نرم", "#6E8572", "#AFC0B1", "#C38B5F", "#F8FAF7", "#FFFFFF", "#28332A", "#778079", "#E0E6E0"),
    ("mono", "سیاه و سفید", "مینیمال", "#111111", "#525252", "#111111", "#FFFFFF", "#FAFAFA", "#111111", "#737373", "#E5E5E5"),
    ("slate", "خاکستری حرفه‌ای", "مینیمال", "#334155", "#64748B", "#2563EB", "#F8FAFC", "#FFFFFF", "#0F172A", "#64748B", "#E2E8F0"),
    ("royal", "آبی سلطنتی", "لوکس", "#273C75", "#7186C7", "#D4AF37", "#F8F9FD", "#FFFFFF", "#17213B", "#6E7690", "#DEE2EE"),
    ("plum", "آلویی", "لوکس", "#6D315F", "#A76591", "#C29B55", "#FFF8FD", "#FFFFFF", "#35222F", "#806A79", "#ECDCE7"),
    ("sunset", "غروب", "شاد", "#F05A47", "#8B5CF6", "#F4B740", "#FFF9F4", "#FFFFFF", "#312529", "#817175", "#F0DFDA"),
    # Part 2C precision pass — background was "#FFF7FB" (a faint pink/lavender
    # tint), which read on-screen as a visible pink cast across the whole
    # page; the ibolak reference page background is overwhelmingly plain
    # white, with pink reserved for discount/promo accents only.
    ("magenta-pop", "صورتی نئونی", "شاد", "#F4B21A", "#241947", "#FF1177", "#FFFFFF", "#FFFFFF", "#241522", "#7C6B78", "#F5DCE9"),
]

for _slug, _name, _group, _primary, _secondary, _accent, _background, _surface, _text, _muted, _border in _PALETTE_DATA:
    register_palette(PaletteDefinition(
        slug=_slug, name_fa=_name, group_fa=_group,
        colors={
            "primary": _primary, "secondary": _secondary, "accent": _accent,
            "background": _background, "surface": _surface, "text": _text,
            "muted": _muted, "border": _border,
        },
    ))
del _slug, _name, _group, _primary, _secondary, _accent, _background, _surface, _text, _muted, _border

# laleRokh-inspired beauty retail palette.  This remains a normal, reusable
# merchant-selectable palette: warm_boutique opts into it, but neither the
# renderer nor the palette knows any Ready Template key.  Magenta carries
# brand/price emphasis while green is reserved for honest commerce actions.
register_palette(PaletteDefinition(
    slug="beauty-magenta",
    name_fa="ارغوانی زیبایی",
    group_fa="زیبایی",
    colors={
        "primary": "#8A007A", "secondary": "#C90A8B", "accent": "#63CF70",
        "background": "#FFFFFF", "surface": "#FFFFFF", "text": "#26212A",
        "muted": "#77717B", "border": "#E8E3E9",
    },
    section_tones=("#C90A8B", "#8A007A", "#63CF70", "#F7D6E9", "#F2EAF6"),
))

# پالتِ صفحه‌ی مرجع: هویتِ اصلی ساده/فروشگاهی است، ولی برای ردیف‌های
# کاتالوگی پنج tone قوی و هماهنگ دارد. این یک Palette عمومی است و هر
# فروشگاهی می‌تواند با یک کلیک آن را انتخاب کند.
# shokolati-inspired specialty retail palette.  Generic merchant-selectable
# presentation only: pale cool page field, chocolate chrome, warm caramel
# commerce accent, and dark footer roles.
register_palette(PaletteDefinition(
    slug="chocolate-ice",
    name_fa="شکلاتی یخی",
    group_fa="خانه و سبک زندگی",
    colors={
        "primary": "#7B4518", "secondary": "#A56A32", "accent": "#DDAE58",
        "background": "#F7F1E8", "surface": "#FFFDF9", "text": "#2C211A",
        "muted": "#77685E", "border": "#E6D9CC",
    },
    theme_roles={
        "header_bg": "#7B4518", "header_text": "#FFFFFF",
        "nav_bg": "#FFFDF9", "nav_text": "#3C2B1D",
        "card_bg": "#FFFDF9", "footer_bg": "#070707",
        "footer_text": "#F5F1EC", "price": "#6F3F18",
    },
    section_tones=("#7B4518", "#A56A32", "#E7D1B7", "#F0E3D4", "#070707"),
))

# Beraito-inspired dense-marketplace palette.  This is intentionally a
# distinct merchant-selectable U10 palette rather than reusing the internal
# pre-U10 ``catalog-colorful`` palette.  It keeps the same semantic rail
# roles (red / green / amber / violet / blue) while owning an independent
# storefront identity and remaining fully generic.
register_palette(PaletteDefinition(
    slug="marketplace-spectrum",
    name_fa="بازارگاه طیفی",
    group_fa="پرفروش",
    colors={
        "primary": "#158A52", "secondary": "#156FA8", "accent": "#E13D58",
        "background": "#F5F6F8", "surface": "#FFFFFF", "text": "#262A30",
        "muted": "#727982", "border": "#DEE2E7",
    },
    theme_roles={
        "header_bg": "#FFFFFF", "header_text": "#262A30",
        "nav_bg": "#FFFFFF", "nav_text": "#262A30",
        "card_bg": "#FFFFFF", "footer_bg": "#464B53",
        "footer_text": "#F7F8FA", "price": "#158A52",
    },
    section_tones=("#EC3B50", "#19AD60", "#C77A13", "#49309A", "#156FA8"),
))

# Atelier/editorial commerce palette — warm ivory fields, restrained gold
# accents and near-black typography.  It is a generic merchant-selectable
# palette: no renderer knows which Ready Template chooses it.
register_palette(PaletteDefinition(
    slug="atelier-ivory",
    name_fa="عاجی آتلیه",
    group_fa="لوکس",
    colors={
        "primary": "#986515", "secondary": "#29231E", "accent": "#D3A51F",
        "background": "#FFFDF9", "surface": "#FFFFFF", "text": "#201B17",
        "muted": "#736B63", "border": "#E7DED2",
    },
    theme_roles={
        "header_bg": "#FFFFFF", "header_text": "#201B17",
        "nav_bg": "#FFFFFF", "nav_text": "#201B17",
        "card_bg": "#FFFFFF", "footer_bg": "#FFFFFF",
        "footer_text": "#201B17", "price": "#7A4D05",
    },
    section_tones=("#F1DFC1", "#D7A720", "#B47A20", "#EEE4D6", "#201B17"),
))

register_palette(PaletteDefinition(
    slug="catalog-colorful",
    name_fa="کاتالوگ رنگی",
    group_fa="پرفروش",
    colors={
        "primary": "#16A34A", "secondary": "#056CAE", "accent": "#F43F5E",
        "background": "#F4F5F7", "surface": "#FFFFFF", "text": "#282B30",
        "muted": "#747982", "border": "#E0E3E8",
    },
    theme_roles={
        "header_bg": "#FFFFFF", "header_text": "#282B30",
        "nav_bg": "#FFFFFF", "nav_text": "#282B30",
        "card_bg": "#FFFFFF", "footer_bg": "#4A4A52",
        "footer_text": "#F5F5F6", "price": "#16A34A",
    },
    section_tones=("#F53247", "#16B95F", "#C56B00", "#352196", "#056CAE"),
))


# Curated release palette pack: 38 existing palettes + 26 reviewed additions = 64.
# The pack is template-agnostic; every palette remains selectable with every template.
from .palette_pack_64 import CURATED_PALETTE_PACK_64_ADDITIONS

for _palette in CURATED_PALETTE_PACK_64_ADDITIONS:
    register_palette(PaletteDefinition(
        slug=_palette["slug"],
        name_fa=_palette["name_fa"],
        group_fa=_palette["group_fa"],
        colors=_palette["colors"],
        theme_roles=_palette["theme_roles"],
    ))
del _palette


# ---------------------------------------------------------------- ۱۰ قالبِ واقعی
#
# «قالب صرفاً رنگ نیست» — طبقِ الزامِ صریحِ کار. تفاوتِ واقعیِ این ۱۰ قالب
# در ترکیبِ ``content_width``/``grid_density``/``card_shadow``/``card_hover``/
# ``hero_style``/``density``/``motion``/``radius``/``button_style``/``font``
# است، نه صرفاً رنگ — این‌ها به CSS custom property تبدیل می‌شوند
# (``apps/core/static/css/tokens.css``) و در CSSِ *موجود*
# (``home.css``/``product_card.css``/``layout.css``) مصرف می‌شوند؛ هیچ
# فورکِ کاملِ تمپلیت‌هایِ Django به‌ازای هر Template ساخته نشده — دقیقاً
# همان معماریِ توصیه‌شده‌یِ گزارشِ ممیزی («shared renderer + design tokens
# + closed visual variants»، نه N×M فورک).
#
# ``modern`` قالبِ پیش‌فرض/پایه است — دقیقاً معادلِ ظاهرِ فعلیِ سایت پیش از
# این چکپوینت (تا انتخابِ آن هیچ فروشگاهی را تغییر ندهد).
register_template(TemplateDefinition(
    slug="modern", name_fa="فروشگاه مدرن", group_fa="فروشگاهی",
    description_fa="هدر تمیز، کارت‌های شناور و چیدمان متعادل — قالب پیش‌فرض.",
    font="Vazirmatn", radius=18, button_radius=12, button_style="filled",
    density="normal", motion="subtle", type_scale="normal", content_width=1200, grid_density=4,
    card_shadow="soft", card_hover="lift", hero_style="wide",
    swatch=["#6D28D9", "#FF4D77", "#FFFFFF"],
))

register_template(TemplateDefinition(
    slug="marketplace", name_fa="مارکت‌پلیس", group_fa="فروشگاهی",
    description_fa="متراکم، محصول‌محور و مناسب فروشگاه‌های بزرگ با تعداد کالای زیاد.",
    font="Vazirmatn", radius=10, button_radius=8, button_style="filled",
    density="compact", motion="subtle", type_scale="compact", content_width=1320, grid_density=6,
    card_shadow="none", card_hover="none", hero_style="wide",
    swatch=["#E52B50", "#F3F4F6", "#FFFFFF"],
))

register_template(TemplateDefinition(
    slug="minimal", name_fa="مینیمال", group_fa="مینیمال",
    description_fa="فضای سفید زیاد، خطوط ظریف و تمرکز روی محتوا — بدون حرکت اضافه.",
    font="Arial", radius=8, button_radius=6, button_style="outline",
    density="relaxed", motion="none", type_scale="normal", content_width=1100, grid_density=3,
    card_shadow="none", card_hover="none", hero_style="tall",
    swatch=["#111111", "#FFFFFF", "#F6F6F6"],
))

register_template(TemplateDefinition(
    slug="boutique", name_fa="بوتیک", group_fa="مد و زیبایی",
    description_fa="چیدمان نرم و تصویری با کارت‌های لطیف — مناسب مد و زیبایی.",
    font="Tahoma", radius=24, button_radius=22, button_style="soft",
    density="relaxed", motion="subtle", type_scale="large", content_width=1150, grid_density=3,
    card_shadow="soft", card_hover="zoom", hero_style="tall",
    swatch=["#8A5A44", "#E8D6C8", "#FFF9F5"],
))

register_template(TemplateDefinition(
    slug="luxury", name_fa="لوکس", group_fa="مد و زیبایی",
    description_fa="تایپوگرافی سنگین، گوشه‌های تیز و حرکت آرام کارت‌ها.",
    font="Georgia", radius=4, button_radius=4, button_style="outline",
    density="relaxed", motion="subtle", type_scale="large", content_width=1200, grid_density=4,
    card_shadow="none", card_hover="lift", hero_style="wide",
    swatch=["#171717", "#C9A227", "#F6F0E6"],
))

register_template(TemplateDefinition(
    slug="tech", name_fa="تکنولوژی", group_fa="دیجیتال",
    description_fa="کنتراست بالا، سایه‌های قوی و کارت‌های واکنش‌گرا با حرکت پویا.",
    font="Tahoma", radius=14, button_radius=10, button_style="filled",
    density="normal", motion="dynamic", type_scale="normal", content_width=1280, grid_density=5,
    card_shadow="strong", card_hover="zoom", hero_style="wide",
    swatch=["#1267FF", "#00C2FF", "#0B1020"],
))

register_template(TemplateDefinition(
    slug="editorial", name_fa="مجله‌ای", group_fa="محتوا",
    description_fa="عنوان‌های بزرگ، ریتم تحریریه و تصاویر شاخص — بدون حرکت اضافه.",
    font="Georgia", radius=2, button_radius=2, button_style="outline",
    density="relaxed", motion="none", type_scale="large", content_width=1100, grid_density=3,
    card_shadow="none", card_hover="none", hero_style="tall",
    swatch=["#A11D33", "#FAF7F2", "#1E1E1E"],
))

register_template(TemplateDefinition(
    slug="compact", name_fa="فشرده حرفه‌ای", group_fa="فروشگاهی",
    description_fa="نمایش محصولات بیشتر در هر اسکرول و هدر کم‌ارتفاع.",
    font="Vazirmatn", radius=6, button_radius=6, button_style="filled",
    density="compact", motion="subtle", type_scale="compact", content_width=1320, grid_density=6,
    card_shadow="none", card_hover="lift", hero_style="wide",
    swatch=["#0A6C55", "#EAF5F1", "#FFFFFF"],
))

register_template(TemplateDefinition(
    slug="playful", name_fa="شاد و پویا", group_fa="خانواده",
    description_fa="گوشه‌های گرد، حرکت نرم و رنگ‌های زنده — مناسب فروشگاه خانواده/کودک.",
    font="Vazirmatn", radius=28, button_radius=24, button_style="soft",
    density="normal", motion="dynamic", type_scale="normal", content_width=1200, grid_density=4,
    card_shadow="soft", card_hover="zoom", hero_style="wide",
    swatch=["#7C3AED", "#FF6B6B", "#FFF8DE"],
))

register_template(TemplateDefinition(
    slug="glass", name_fa="شیشه‌ای", group_fa="مدرن",
    description_fa="سطوح نیمه‌شفاف، سایه نرم و عمق بصری بیشتر.",
    font="Vazirmatn", radius=22, button_radius=16, button_style="soft",
    density="normal", motion="subtle", type_scale="normal", content_width=1200, grid_density=4,
    card_shadow="strong", card_hover="lift", hero_style="wide",
    swatch=["#4F46E5", "#06B6D4", "#EEF2FF"],
))
