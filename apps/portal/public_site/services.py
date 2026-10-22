"""Resolve public-site overrides, tokens, the design switch and the theme CSS.

Every read is defensive: if the settings table is missing (code deployed before
``migrate``) or unreadable, the shipped defaults are used and the site keeps
rendering. One query per request for overrides, one for photo overrides.
"""

import re
from urllib.parse import urlsplit

from django.conf import settings
from django.db import DatabaseError
from django.templatetags.static import static

from apps.core.utils import to_fa_digits
from apps.portal.models import PublicSitePhoto, PublicSiteSetting

from . import registry

EMPTY_MARK = "-"   # an override of just "-" means "show nothing" (otherwise empty = default)

_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
_FONT_NAME_RE = re.compile(r"^[A-Za-z0-9؀-ۿ‌ _.\-]{1,60}$")
_TOKEN_RE = re.compile(r"\{(trial|support_phone|support_email|support_email_link|days)\}")
_RADIUS_RE = re.compile(r"^(?:[0-9]|[1-3][0-9]|40)px$")
_CACHE_ATTR = "_public_site_cache"
_URL_PREFIXES = ("https://", "http://", "mailto:", "tel:", "/")


# ---------------------------------------------------------------------------
# Overrides
# ---------------------------------------------------------------------------
def _load(request):
    cache = getattr(request, _CACHE_ATTR, None) if request is not None else None
    if cache is not None:
        return cache
    try:
        overrides = {row.key: row.value for row in PublicSiteSetting.objects.all()}
    except DatabaseError:
        overrides = {}
    try:
        photos = {p.slot: p for p in PublicSitePhoto.objects.all()}
    except DatabaseError:
        photos = {}
    cache = {"overrides": overrides, "photos": photos, "tokens": None}
    if request is not None:
        try:
            setattr(request, _CACHE_ATTR, cache)
        except AttributeError:
            pass
    return cache


def get_overrides(request=None) -> dict:
    return _load(request)["overrides"]


def invalidate(request=None):
    if request is not None and hasattr(request, _CACHE_ATTR):
        delattr(request, _CACHE_ATTR)


# ---------------------------------------------------------------------------
# Design switch (rollback)
# ---------------------------------------------------------------------------
def active_design(request=None) -> str:
    """``legacy`` or ``v2``. Order: emergency env/settings force → the owner's
    switch in Platform Admin → ``PUBLIC_SITE_DEFAULT_DESIGN`` (``v2``)."""
    forced = getattr(settings, "PUBLIC_SITE_FORCE_DESIGN", "")
    if forced in (registry.DESIGN_V2, registry.DESIGN_LEGACY):
        return forced
    chosen = get_overrides(request).get(registry.SWITCH_KEY, "")
    if chosen in (registry.DESIGN_V2, registry.DESIGN_LEGACY):
        return chosen
    default = getattr(settings, "PUBLIC_SITE_DEFAULT_DESIGN", registry.DESIGN_V2)
    return default if default in (registry.DESIGN_V2, registry.DESIGN_LEGACY) else registry.DESIGN_V2


# ---------------------------------------------------------------------------
# Tokens and values
# ---------------------------------------------------------------------------
def _tokens(request):
    cache = _load(request)
    if cache["tokens"] is None:
        trial, phone, email = 30, "", ""
        try:
            from apps.portal.services.platform_config_service import get_platform_configuration

            config = get_platform_configuration()
            trial = config.default_trial_days
            phone = config.support_contact_phone or ""
            email = config.support_contact_email or ""
        except Exception:  # configuration must never take the marketing site down
            pass
        cache["tokens"] = {
            "trial": to_fa_digits(trial),
            "support_phone": phone,
            "support_email": email,
            "support_email_link": f"mailto:{email}" if email else "",
        }
    return cache["tokens"]


def apply_tokens(text: str, request=None, **extra) -> str:
    if not text or "{" not in text:
        return text
    values = dict(_tokens(request))
    for name, value in extra.items():
        values[name] = to_fa_digits(value)
    return _TOKEN_RE.sub(lambda m: str(values.get(m.group(1), "")), text)


def raw_value(key: str, request=None) -> str:
    """Override if present, else the registry default (tokens NOT applied)."""
    field = registry.get_field(key)
    if field is None:
        raise KeyError(f"unknown public-site key: {key}")
    override = get_overrides(request).get(key)
    if override is None or override == "":
        return field.default
    if field.kind in (registry.KIND_TEXT, registry.KIND_TEXTAREA, registry.KIND_URL) and override == EMPTY_MARK:
        return ""
    return override


def value(key: str, request=None, **extra) -> str:
    field = registry.get_field(key)
    text = raw_value(key, request)
    if field is not None and field.kind in (registry.KIND_BOOL, registry.KIND_COLOR, registry.KIND_CHOICE, registry.KIND_PHOTO):
        return text
    text = apply_tokens(text, request, **extra)
    if field is not None and field.kind == registry.KIND_URL and text and not text.startswith(_URL_PREFIXES):
        return ""   # defence in depth: never render e.g. a javascript: link even if the table was edited by hand
    return text


def truthy(key: str, request=None) -> bool:
    return raw_value(key, request) == "1"


# ---------------------------------------------------------------------------
# Photos
# ---------------------------------------------------------------------------
def photo(slot: str, request=None) -> dict:
    current = _load(request)["photos"].get(slot)
    if current is not None and current.image:
        url = current.image.url
        if not urlsplit(url).scheme and not url.startswith("/"):
            url = "/" + url
        return {"url": url, "alt": current.alt_text}
    if slot == "logo":
        # The platform's final uploaded logo (Platform Configuration) beats the bundled mark.
        try:
            from apps.portal.services.platform_config_service import get_platform_configuration

            config_logo = get_platform_configuration().logo
            if config_logo:
                return {"url": config_logo.url, "alt": ""}
        except Exception:
            pass
    fallback = "extra" if slot.startswith("extra") else slot   # spare slots show a neutral placeholder until used
    return {"url": static(f"portal/images/public/{fallback}.webp"), "alt": ""}


def photo_urls(request=None) -> dict:
    return {slot: photo(slot, request)["url"] for slot, _ in registry.PHOTO_SLOTS}


def photo_alts(request=None) -> dict:
    return {slot: photo(slot, request)["alt"] for slot, _ in registry.PHOTO_SLOTS}


# ---------------------------------------------------------------------------
# Lists
# ---------------------------------------------------------------------------
def list_items(prefix: str, request=None) -> list:
    spec = registry.LISTS[prefix]
    rows = []
    for i in range(1, spec.count + 1):
        if truthy(f"{prefix}.{i}.hide", request):
            continue
        data = {name: value(f"{prefix}.{i}.{name}", request) for name in spec.names}
        if not data.get(spec.primary):
            continue
        for name, kind in spec.kinds.items():
            if kind == registry.KIND_PHOTO:
                picked = photo(data[name] or "stilllife", request)
                data[f"{name}_url"] = picked["url"]
                data[f"{name}_alt"] = picked["alt"]
            elif kind == registry.KIND_BOOL:
                data[name] = data[name] == "1"
        if spec.sub:
            sub_name, sub_count, sub_names, sub_primary, sub_kinds = spec.sub
            sub_rows = []
            for j in range(1, sub_count + 1):
                sub_data = {n: value(f"{prefix}.{i}.{sub_name}{j}.{n}", request) for n in sub_names}
                if sub_data.get(sub_primary):
                    for n, kind in sub_kinds.items():
                        if kind == registry.KIND_PHOTO:
                            picked = photo(sub_data[n] or "stilllife", request)
                            sub_data[f"{n}_url"], sub_data[f"{n}_alt"] = picked["url"], picked["alt"]
                    sub_rows.append(sub_data)
            data["items"] = sub_rows
        data["i"] = i
        data["pos"] = len(rows) + 1
        rows.append(data)
    return rows


# ---------------------------------------------------------------------------
# Validation (used by the Platform Admin editor and, defensively, at render)
# ---------------------------------------------------------------------------
def is_valid_color(text: str) -> bool:
    return bool(_COLOR_RE.match(text or ""))


def clean_https_url(text: str) -> str | None:
    text = (text or "").strip()
    if not text or len(text) > 300 or re.search(r"""[\s"'<>\\`]""", text):
        return None
    parts = urlsplit(text)
    if parts.scheme != "https" or not parts.netloc:
        return None
    return text


def validate(field: registry.Field, raw: str):
    """-> (stored_value or None meaning 'remove override', error or None)."""
    raw = (raw or "").strip()
    if field.kind == registry.KIND_BOOL:
        stored = "1" if raw in ("1", "on", "true") else "0"
        effective_default = "1" if field.default == "1" else "0"
        return (None if stored == effective_default else stored), None
    if raw == "":
        return None, None
    if raw == field.default:
        return None, None
    if field.kind == registry.KIND_COLOR:
        if not is_valid_color(raw):
            return None, "کد رنگ باید مثل ‎#0c4a3c‎ باشد."
        return raw.lower(), None
    if field.kind == registry.KIND_CHOICE:
        if raw not in {c[0] for c in field.choices}:
            return None, "گزینهٔ نامعتبر."
        return raw, None
    if field.kind == registry.KIND_PHOTO:
        if raw not in {c[0] for c in field.choices}:
            return None, "جایگاه تصویر نامعتبر است."
        return raw, None
    if field.kind == registry.KIND_URL:
        if field.key == "font.stylesheet":
            cleaned = clean_https_url(raw)
            return (cleaned, None) if cleaned else (None, "فقط آدرس https معتبر پذیرفته می‌شود.")
        if raw == EMPTY_MARK or raw.startswith(("https://", "http://", "mailto:", "tel:", "/")):
            return raw, None
        return None, "آدرس باید با https:// یا mailto: شروع شود."
    if field.key.endswith(".radius") and field.key.startswith("demo."):
        if not _RADIUS_RE.match(raw):
            return None, "مثلاً 3px یا 16px (حداکثر ۴۰)."
        return raw, None
    if field.key == "font.base_size":
        if not raw.isdigit() or not 14 <= int(raw) <= 20:
            return None, "عددی بین ۱۴ تا ۲۰ وارد کنید."
        return raw, None
    if field.key in ("font.custom_text", "font.custom_display"):
        if raw != EMPTY_MARK and not _FONT_NAME_RE.match(raw):
            return None, "نام فونت فقط شامل حروف، عدد و فاصله باشد."
        return raw, None
    if len(raw) > (4000 if field.kind == registry.KIND_TEXTAREA else 400):
        return None, "متن بیش از حد طولانی است."
    return raw, None


# ---------------------------------------------------------------------------
# Theme CSS
# ---------------------------------------------------------------------------
def _font_stack(kind: str, request) -> str | None:
    preset_key = value(f"font.{kind}", request)
    preset_default = registry.FIELDS[f"font.{kind}"].default
    custom = (get_overrides(request).get(f"font.custom_{kind}") or "").strip()
    if custom == EMPTY_MARK or not _FONT_NAME_RE.match(custom):
        custom = ""
    stack = registry.FONT_PRESETS.get(preset_key, registry.FONT_PRESETS[preset_default])[1]
    is_default_preset = preset_key == preset_default or preset_key not in registry.FONT_PRESETS
    if is_default_preset and not custom:
        return None   # leave the stylesheet default untouched
    if custom:
        stack = f"'{custom}',{stack}"
    return stack


def font_stylesheet_url(request=None) -> str | None:
    return clean_https_url(get_overrides(request).get("font.stylesheet", ""))


def _color_decls(scheme: str, overrides: dict) -> str:
    decls = []
    for name in registry.COLOR_TOKEN_NAMES:
        val = (overrides.get(f"color.{scheme}.{name}") or "").strip()
        if is_valid_color(val):
            decls.append(f"--{name}:{val}")
    return ";".join(decls)


def theme_css(request=None) -> str:
    """Only the tokens the owner changed — empty string when nothing was customised."""
    overrides = get_overrides(request)
    light = [d for d in (_color_decls("light", overrides),) if d]
    dark = _color_decls("dark", overrides)
    for kind, var in (("text", "--text"), ("display", "--display")):
        stack = _font_stack(kind, request)
        if stack:
            light.append(f"{var}:{stack}")
    parts = []
    if light:
        parts.append(":root{" + ";".join(light) + "}")
    if dark:
        parts.append('@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){' + dark + "}}")
        parts.append(':root[data-theme="dark"]{' + dark + "}")
    size = (overrides.get("font.base_size") or "").strip()
    if size.isdigit() and 14 <= int(size) <= 20:
        parts.append(f"body{{font-size:{int(size)}px}}")
    return "".join(parts)


def _color_or(text: str, fallback: str) -> str:
    return text if is_valid_color(text) else fallback


def demo_payload(request=None) -> dict:
    """Data the landing demo (switchable sample store) needs, with photo URLs resolved.
    Everything comes from the editable ``demo`` list; values are re-validated here because
    the JS writes them into CSS custom properties."""
    themes = []
    for row in list_items("demo", request):
        radius = row["radius"] if _RADIUS_RE.match(row["radius"] or "") else "3px"
        themes.append({
            "tag": row["tag"], "name": row["name"], "url": row["url"], "title": row["title"], "sub": row["sub"],
            "hero": row["hero"], "layout": "editorial" if row["layout"] == "editorial" else "",
            "v": {
                "--s-bg": _color_or(row["bg"], "#fbfaf7"), "--s-ink": _color_or(row["ink"], "#1c1c1c"),
                "--s-acc": _color_or(row["acc"], "#1c1c1c"), "--s-soft": _color_or(row["soft"], "#efece6"),
                "--s-r": radius,
            },
            "p": [[p["img"], p["name"], p["price"]] for p in row.get("items", [])],
        })
    return {"IMG": photo_urls(request), "ALT": photo_alts(request), "THEMES": themes}


def ready_template_rows(request=None) -> list:
    """The platform's real Ready Templates (one card each, latest version) as public-page rows.
    Read-only; new templates appear automatically. Owner overrides: name/desc/cat/hide/home."""
    from apps.storefront_builder.services import ready_template_card_service

    cards = ready_template_card_service.build_ready_template_cards(
        None, current_template_key=None, current_template_version=None,
    )
    rows = []
    for card in cards:
        key = card["preset"].key
        if truthy(f"rt.{key}.hide", request):
            continue
        rows.append({
            "key": key,
            "name": value(f"rt.{key}.name", request) or card["preset"].label_fa,
            "desc": value(f"rt.{key}.desc", request),
            "cat": value(f"rt.{key}.cat", request),
            "home": truthy(f"rt.{key}.home", request),
            "thumbnail_kind": card["thumbnail_kind"], "thumbnail_url": card["thumbnail_url"],
            "thumbnail_svg": card["thumbnail_svg"], "palette": card["palette_swatch"],
        })
    return rows
