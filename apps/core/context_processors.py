from apps.content.models import SocialLink
from apps.core.color_utils import darken_hex, foreground_for, mix_hex, safe_hex
from apps.core.models import ShopSettings, ShopSettingsNotProvisionedError
from apps.stores.resolution import StoreResolutionError


def _versioned_appearance(request):
    """نسخه‌ای که فیلدهایِ *ساختاریِ* هومپیجِ Template (content_width،
    grid_density، hero_style، card_shadow، card_hover) باید از آن خوانده
    شوند — این‌ها فقط وقتی از نسخه می‌آیند که
    ``request.storefront_appearance_version`` صریحاً ست شده باشد (یعنی
    واقعاً همان صفحه‌ی Builder-aware در حالِ رندر است: Preview یا خودِ
    صفحه‌ی اصلیِ عمومی)؛ در غیرِ این صورت None برمی‌گردد و base.html از
    پیش‌فرض‌هایِ سخت‌کدشده (معادلِ قالبِ «modern») استفاده می‌کند.

    این قصداً از توکن‌هایِ *سراسریِ* هویت (رنگ/فونت/گردی/دکمه/حرکت/اندازه‌متن
    — نگاه کنید به ``_global_identity_version``) جدا مانده: چیدمانِ
    ساختاریِ صفحه‌ی اصلی (عرضِ محتوا، تعدادِ ستون، سبکِ هیرو) معنایی برایِ
    پرداخت/جزئیاتِ کالا ندارد و اعمالِ اجباریِ آن می‌تواند چیدمانِ آن
    صفحات را بشکند — طبقِ تصمیمِ معماریِ صریح (بخشِ «هویتِ طراحیِ سراسری
    در برابرِ ساختارِ صفحه‌ی اصلی» در گزارشِ نهایی)."""
    version = getattr(request, "storefront_appearance_version", None)
    if version is None:
        return None

    from apps.storefront_builder import appearance_registry
    from apps.storefront_builder.services.appearance_authority_service import (
        effective_page_appearance_config,
    )

    config = version.effective_appearance_config()
    # Phase 4 (Task 3C) — the Page Appearance tier: merges this page's own
    # sparse structural override (content_width/grid_density/card_shadow/
    # card_hover/hero_style — see layout_service.PAGE_APPEARANCE_KEYS) on
    # top of the Store-global config resolved above. ``storefront_appearance_page``
    # is set by the exact same call (``build_universal_storefront_context``)
    # that sets ``storefront_appearance_version`` just above, so Preview and
    # Public always resolve this identically. Absent (non-Builder-aware
    # request) simply skips the merge — zero behavior change for any page
    # that never reaches the Builder-aware code path.
    page = getattr(request, "storefront_appearance_page", None)
    if page is not None:
        config = effective_page_appearance_config(store_appearance_config=config, page=page)
    template = appearance_registry.get_template(config["template_slug"]) or appearance_registry.get_template("modern")
    return {"template": template, "config": config}


def _global_identity_version(request, store_id):
    """نسخه‌ای که توکن‌های *سراسریِ* هویتِ فروشگاه (رنگ‌ها، فونت، گردی،
    سبکِ دکمه، سبکِ حرکت، اندازه‌ی متن) باید از آن خوانده شوند — برخلافِ
    ``_versioned_appearance`` (فقط ساختارِ صفحه‌ی اصلی)، این‌ها هویتِ
    *کلِ* فروشگاه‌اند: مشتری نباید در جزئیاتِ کالا یا پرداخت برندِ
    متفاوتی با صفحه‌ی اصلی ببیند، حتی وقتی آن صفحه هنوز چیدمانِ
    ساختاریِ Builder را ندارد (تصمیمِ معماریِ صریح — بخشِ ۲۲ بازبینیِ
    نهایی: «مشتری نباید هنگامِ دیدنِ جزئیاتِ کالا برندِ متفاوتی با
    صفحه‌ی اصلی ببیند»).

    اگر ``request.storefront_appearance_version`` صریحاً ست شده باشد
    (Preview یا خودِ صفحه‌ی اصلیِ عمومی)، همان استفاده می‌شود. وگرنه، اگر
    همین Store (بر اساسِ ``store_id`` — **نه** ``request.store``، که در
    صفحاتِ storefront غیرِ Builder-aware همیشه None است؛ ویوهای این
    صفحات Store را محلی resolve می‌کنند، نه از میان‌افزار — دقیقاً همان
    دلیلی که ``shop_settings`` پایین‌تر برایِ SOCIAL_LINKS_* از
    ``shop.store_id`` استفاده می‌کند، نه ``request.store``) یک نسخه‌ی
    *منتشرشده* دارد (هرگز Draft — یک صفحه‌ی غیرِ Builder-aware هرگز نباید
    محتوایِ منتشرنشده ببیند)، همان نسخه برمی‌گردد؛ در غیرِ این صورت None
    (یعنی ``ShopSettings`` زنده، دقیقاً رفتارِ قبلی)."""
    version = getattr(request, "storefront_appearance_version", None)
    if version is not None:
        return version

    if store_id is None:
        return None

    # Phase 1B: کوئریِ «آیا این Store یک Storefront V2 منتشرشده دارد؟»
    # اکنون در یک نقطه‌ی مرکزیِ واحد نوشته شده — نگاه کنید به
    # ``apps.storefront_builder.services.page_resolution_service``. پیش از
    # این فاز، همین شرط (``uses_visual_storefront_layout=True AND
    # published_version__isnull=False``) اینجا هم مستقلاً تکرار شده بود.
    from apps.storefront_builder.services.page_resolution_service import (
        get_published_layout_for_store_id,
    )

    layout = get_published_layout_for_store_id(store_id)
    return layout.published_version if layout is not None else None


def _versioned_colors(request, store_id):
    """رنگ‌های نهایی از ``_global_identity_version`` حل می‌شوند — نگاه
    کنید به مستنداتِ آن برای این‌که چرا این دیگر محدود به
    Builder-aware نیست. هر Store بدونِ نسخه‌ی منتشرشده دقیقاً مثلِ قبل
    رفتار می‌کند — رنگِ زنده‌ی ``ShopSettings``."""
    version = _global_identity_version(request, store_id)
    if version is None:
        return None

    from apps.storefront_builder import appearance_registry

    colors = appearance_registry.resolve_colors(version.effective_appearance_config())
    return colors


def shop_settings(request):
    """هویت و تنظیمات فروشگاهِ Store جاری — از همان رکورد ShopSettings که پنل مدیریت › تنظیمات ویرایش می‌کند.

    Store از ``request.store`` (که middleware مرحله‌ی تحلیل میزبان تنظیم
    کرده) خوانده می‌شود. اگر هنوز میزبان درخواست به هیچ Store‌ای resolve
    نشده باشد (``request.store is None``)، ``ShopSettings.load()`` بدون
    آرگومان به حالت سازگاریِ موقت (تک‌فروشگاهی Akhlaghi) برمی‌گردد و در غیر
    آن صورت fail-closed می‌شود — هرگز تنظیمات یک Store دیگر را برنمی‌گرداند.

    یک Host ناشناخته/غیرمجاز (نه در ``STORES_DEVELOPMENT_HOST_ALLOWLIST``، نه
    ``StoreDomain`` تأییدشده) وقتی بیش از یک Store در دیتابیس وجود دارد، به
    ``StoreResolutionError`` می‌رسد — این context processor روی **هر**
    template (از جمله صفحه‌ی خطای ۴۰۴ خودِ Django) اجرا می‌شود، پس این حالت
    باید امن مدیریت شود، نه این‌که رندر صفحه‌ی خطا را خودش با یک ۵۰۰ جدید
    خراب کند. یک دیکشنری خالی برمی‌گرداند — تمپلیت‌ها با فیلتر ``|default``
    از قبل برای نبود این متغیرها آماده‌اند.

    توکن‌هایِ *سراسریِ* هویت (رنگ‌ها، فونت، گردی، سبکِ دکمه، سبکِ حرکت،
    اندازه‌ی متن، رفتارِ تصویر) ممکن است به‌جایِ ``ShopSettings`` زنده، از
    نسخه‌ی منتشرشده‌ی سازنده بصری بیایند — حتی در صفحاتِ غیرِ
    Builder-aware (پرداخت، جزئیاتِ کالا)، تا برندِ فروشگاه در کلِ سایت
    یکدست بماند؛ نگاه کنید به ``_global_identity_version``. ساختارِ
    *صفحه‌ی اصلی* (عرضِ محتوا/تعدادِ ستون/سبکِ هیرو/تراکم) برخلافِ آن،
    عمداً محدود به صفحاتِ Builder-aware می‌ماند — نگاه کنید به
    ``_versioned_appearance``.
    """
    try:
        shop = ShopSettings.load(store=getattr(request, "store", None))
    except (StoreResolutionError, ShopSettingsNotProvisionedError):
        return {}

    versioned = _versioned_colors(request, shop.store_id)
    if versioned is not None:
        primary = safe_hex(versioned.get("primary"), "#6D28D9")
        accent = safe_hex(versioned.get("accent"), "#FF4D77")
        secondary = safe_hex(versioned.get("secondary"), "#7C3AED")
        background = safe_hex(versioned.get("background"), "#F7F5FC")
        surface = safe_hex(versioned.get("surface"), "#FFFFFF")
        text = safe_hex(versioned.get("text"), "#241C3A")
        muted = safe_hex(versioned.get("muted"), "#8B86A3")
        border = safe_hex(versioned.get("border"), mix_hex(text, surface, 0.12))
    else:
        primary = safe_hex(shop.primary_color, "#6D28D9")
        accent = safe_hex(shop.accent_color, "#FF4D77")
        secondary = safe_hex(shop.secondary_color, "#7C3AED")
        background = safe_hex(shop.background_color, "#F7F5FC")
        surface = safe_hex(shop.surface_color, "#FFFFFF")
        text = safe_hex(shop.text_color, "#241C3A")
        muted = safe_hex(shop.muted_text_color, "#8B86A3")
        border = mix_hex(text, surface, 0.12)

    from apps.storefront_builder import appearance_registry as _appearance_registry

    _default_template = _appearance_registry.get_template("modern")

    # توکن‌هایِ سراسریِ هویت (رنگ از قبل بالا حل شد؛ اینجا فونت/گردی/
    # دکمه/حرکت/اندازه‌متن/رفتارِ تصویر) — از هر Storeیی که نسخه‌ی
    # منتشرشده دارد می‌آیند، نه فقط صفحاتِ Builder-aware؛ نگاه کنید به
    # ``_global_identity_version``.
    global_version = _global_identity_version(request, shop.store_id)
    if global_version is not None:
        global_config = global_version.effective_appearance_config()
        global_template = (
            _appearance_registry.get_template(global_config["template_slug"]) or _default_template
        )
        shop_font = global_config["font"]
        shop_radius = global_config["radius"]
        shop_button_radius = global_config["button_radius"]
        shop_button_style = global_config.get("button_style") or global_template.button_style
        shop_motion = global_config["motion"]
        shop_type_scale = global_config.get("type_scale") or global_template.type_scale
        shop_image_fit = global_config.get("image_fit", "cover")
        shop_image_hover = global_config.get("image_hover", "zoom")
        shop_card_image_crossfade = global_config.get("card_image_crossfade", False)
        shop_card_image_zoom = global_config.get("card_image_zoom", True)
    else:
        shop_font = _default_template.font
        shop_radius = _default_template.radius
        shop_button_radius = _default_template.button_radius
        shop_button_style = _default_template.button_style
        shop_motion = _default_template.motion
        shop_type_scale = _default_template.type_scale
        shop_image_fit = "cover"
        shop_image_hover = "zoom"
        shop_card_image_crossfade = False
        shop_card_image_zoom = True

    # ساختارِ *صفحه‌ی اصلی* (عرضِ محتوا/تعدادِ ستون/سبکِ هیرو/سایه و
    # هاورِ کارت/تراکم) — عمداً محدود به صفحاتِ Builder-aware می‌ماند؛
    # نگاه کنید به ``_versioned_appearance``.
    appearance = _versioned_appearance(request)
    if appearance is not None:
        template = appearance["template"]
        config = appearance["config"]
        shop_template_slug = template.slug
        shop_density = config["density"]
        # Phase 8 P0-7 — این ۵ فیلد اکنون مستقیماً در appearance_config
        # قابلِ‌override‌اند (پنلِ «تنظیماتِ بیشتر»)؛ غیابشان (فروشگاهی
        # که این پنلِ جدید را هرگز لمس نکرده) یعنی هم‌چنان از Templateِ
        # ذخیره‌شده بیایند — دقیقاً همان رفتارِ قبل از این چکپوینت،
        # بدونِ نیاز به Migration.
        shop_content_width = config.get("content_width") or template.content_width
        shop_grid_density = config.get("grid_density") or template.grid_density
        shop_card_shadow = config.get("card_shadow") or template.card_shadow
        shop_card_hover = config.get("card_hover") or template.card_hover
        shop_hero_style = config.get("hero_style") or template.hero_style
    else:
        shop_template_slug = "modern"
        shop_density = _default_template.density
        shop_content_width = _default_template.content_width
        shop_grid_density = _default_template.grid_density
        shop_card_shadow = _default_template.card_shadow
        shop_card_hover = _default_template.card_hover
        shop_hero_style = _default_template.hero_style

    typography = _appearance_registry.resolve_typography(shop_type_scale)

    tone_config = (
        global_config
        if global_version is not None
        else {
            "palette_slug": None,
            "color_overrides": {
                "primary": primary, "secondary": secondary, "accent": accent,
                "background": background, "surface": surface, "text": text,
                "muted": muted, "border": border,
            },
        }
    )
    section_tones = _appearance_registry.resolve_section_tones(tone_config)
    theme_roles = _appearance_registry.resolve_theme_roles(tone_config)

    # Phase 3.10 — Storefront -> Merchant Admin shortcut.
    #
    # This is intentionally limited to the actual Store homepage and the
    # Builder's HOME preview. The link is not an authorization mechanism:
    # /admin-portal/ keeps its existing authentication/authorization gates.
    # We only compute the correct per-Store host here, preserving a local
    # non-default port such as :8000.
    #
    # Final storefront polish pass — merchant QA: a real, live "پنل مدیریت"
    # button was rendering in the PUBLIC shopper-facing header on
    # ``catalog:home`` for ANY anonymous visitor (this flag was never
    # staff/auth-gated — only page-gated). A public storefront must never
    # expose an admin-panel control. The Builder's own HOME preview
    # (``dashboard:storefront-builder-preview``) is a separate, authenticated
    # merchant-admin surface, not the public storefront, so it keeps the
    # shortcut unchanged; only the real public homepage loses it.
    resolver_match = getattr(request, "resolver_match", None)
    view_name = getattr(resolver_match, "view_name", "") if resolver_match else ""
    is_builder_preview_home = (
        view_name == "dashboard:storefront-builder-preview"
        and request.GET.get("page", "home") == "home"
    )
    is_home_surface = view_name == "catalog:home" or is_builder_preview_home
    shop_admin_url = ""
    if is_home_surface:
        from django.conf import settings as django_settings
        from apps.stores.hostnames import build_cross_host_url
        from apps.stores.models import Store

        store = getattr(request, "store", None)
        if store is None or getattr(store, "pk", None) != shop.store_id:
            store = (
                Store.objects.only("id", "admin_subdomain")
                .filter(pk=shop.store_id)
                .first()
            )
        if store is not None and store.admin_subdomain:
            admin_hostname = (
                f"{store.admin_subdomain}.{django_settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"
            )
            shop_admin_url = build_cross_host_url(
                request,
                hostname=admin_hostname,
                path="/admin-portal/",
            )

    from apps.stores.services.enamad_verification_service import (
        store_enamad_badge_for_request,
        store_enamad_verification_meta_for_request,
    )

    enamad_verification_meta = store_enamad_verification_meta_for_request(
        request, store_id=shop.store_id
    )
    # Merchant eNamad badge is storefront-only. Avoid the custom-domain
    # verification lookup on admin pages, where the badge is never rendered.
    enamad_badge = None
    if not getattr(request, "path", "").startswith("/admin-portal/"):
        enamad_badge = store_enamad_badge_for_request(
            request, store_id=shop.store_id
        )

    return {
        "SHOP_NAME": shop.name,
        "SHOP_TAGLINE": shop.tagline,
        "SHOP_CONTACT_PHONE": shop.contact_phone,
        "SHOP_CONTACT_EMAIL": shop.contact_email,
        "SHOP_CONTACT_ADDRESS": shop.contact_address,
        "SHOP_DESCRIPTION": shop.description,
        "SHOP_FREE_SHIPPING_THRESHOLD": shop.free_shipping_threshold,
        "SHOP_TAX_PERCENT": shop.tax_percent,
        # هویت بصری
        "SHOP_LOGO": shop.logo if shop.logo else None,
        "SHOP_FAVICON": shop.favicon if shop.favicon else None,
        "SHOP_PRIMARY_COLOR": primary,
        "SHOP_ACCENT_COLOR": accent,
        "SHOP_SECONDARY_COLOR": secondary,
        "SHOP_BACKGROUND_COLOR": background,
        "SHOP_SURFACE_COLOR": surface,
        "SHOP_TEXT_COLOR": text,
        "SHOP_MUTED_TEXT_COLOR": muted,
        "SHOP_PRIMARY_FG": foreground_for(primary),
        "SHOP_ACCENT_FG": foreground_for(accent),
        "SHOP_SECONDARY_FG": foreground_for(secondary),
        "SHOP_PRIMARY_HOVER": darken_hex(primary),
        "SHOP_BORDER_COLOR": border,
        "SHOP_PALETTE_TONE_1": section_tones[0],
        "SHOP_PALETTE_TONE_2": section_tones[1],
        "SHOP_PALETTE_TONE_3": section_tones[2],
        "SHOP_PALETTE_TONE_4": section_tones[3],
        "SHOP_PALETTE_TONE_5": section_tones[4],
        "SHOP_THEME_HEADER_BG": theme_roles["header_bg"],
        "SHOP_THEME_HEADER_TEXT": theme_roles["header_text"],
        "SHOP_THEME_NAV_BG": theme_roles["nav_bg"],
        "SHOP_THEME_NAV_TEXT": theme_roles["nav_text"],
        "SHOP_THEME_CARD_BG": theme_roles["card_bg"],
        "SHOP_THEME_FOOTER_BG": theme_roles["footer_bg"],
        "SHOP_THEME_FOOTER_TEXT": theme_roles["footer_text"],
        "SHOP_THEME_PRICE": theme_roles["price"],
        "SHOW_ADMIN_SHORTCUT": bool(is_builder_preview_home and shop_admin_url),
        "SHOP_ADMIN_URL": shop_admin_url,
        "SHOP_ENAMAD_VERIFICATION_META_NAME": (
            enamad_verification_meta.name if enamad_verification_meta else ""
        ),
        "SHOP_ENAMAD_VERIFICATION_META_CONTENT": (
            enamad_verification_meta.content if enamad_verification_meta else ""
        ),
        "SHOP_ENAMAD_BADGE_PROFILE_URL": enamad_badge.profile_url if enamad_badge else "",
        "SHOP_ENAMAD_BADGE_LOGO_URL": enamad_badge.logo_url if enamad_badge else "",
        # ساختارِ ظاهر (Template) — فقط برایِ مسیرهایِ Builder-aware از
        # نسخه می‌آید؛ نگاه کنید به ``_versioned_appearance``.
        "SHOP_TEMPLATE_SLUG": shop_template_slug,
        "SHOP_FONT": shop_font,
        "SHOP_RADIUS": shop_radius,
        "SHOP_BUTTON_RADIUS": shop_button_radius,
        "SHOP_BUTTON_STYLE": shop_button_style,
        "SHOP_DENSITY": shop_density,
        "SHOP_MOTION": shop_motion,
        "SHOP_CONTENT_WIDTH": shop_content_width,
        "SHOP_GRID_DENSITY": shop_grid_density,
        "SHOP_CARD_SHADOW": shop_card_shadow,
        "SHOP_CARD_HOVER": shop_card_hover,
        "SHOP_HERO_STYLE": shop_hero_style,
        "SHOP_IMAGE_FIT": shop_image_fit,
        "SHOP_IMAGE_HOVER": shop_image_hover,
        "SHOP_CARD_IMAGE_CROSSFADE": "1" if shop_card_image_crossfade else "",
        "SHOP_CARD_IMAGE_ZOOM": "1" if shop_card_image_zoom else "",
        # سلسله‌مراتبِ تایپوگرافی — پنج نقشِ معنادار، نه اندازه‌یِ دلخواه؛
        # نگاه کنید به ``appearance_registry.TYPE_SCALE_SIZES``.
        "SHOP_TYPE_SCALE": shop_type_scale,
        "SHOP_HEADING_SIZE": typography["heading"],
        "SHOP_BODY_SIZE": typography["body"],
        "SHOP_PRODUCT_NAME_SIZE": typography["product_name"],
        "SHOP_PRICE_SIZE": typography["price"],
        "SHOP_MUTED_TEXT_SIZE": typography["muted"],
        # شبکه‌های اجتماعی — store_id (نه shop.store) تا از یک query اضافی برای واکشی خودِ Store پرهیز شود
        "SOCIAL_LINKS_FOOTER": SocialLink.objects.filter(
            is_active=True, show_in_footer=True, store_id=shop.store_id,
        ).order_by("display_order", "id"),
        "SOCIAL_LINKS_HEADER": SocialLink.objects.filter(
            is_active=True, show_in_header=True, store_id=shop.store_id,
        ).order_by("display_order", "id"),
    }
