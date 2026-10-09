"""Canonical colour + WCAG contrast helpers.

This is the ONE place that knows how to parse a CSS colour, composite alpha,
compute WCAG 2.x relative luminance / contrast ratio and derive accessible
colours. The storefront theme pipeline (``apps.core.context_processors``,
``apps.storefront_builder.accessible_colors``), the unit tests and the runtime
browser audit (``tools/contrast_audit``) all call into it so a threshold or
formula can never drift between "what the product renders" and "what the audit
checks".
"""

import re

HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")

#: WCAG 2.2 AA minimums (SC 1.4.3 text, SC 1.4.11 non-text).
AA_NORMAL_TEXT = 4.5
AA_LARGE_TEXT = 3.0
AA_NON_TEXT = 3.0
#: Product rule: disabled-but-meant-to-stay-readable text targets at least 3:1
#: even though WCAG exempts inactive controls.
DISABLED_TEXT_TARGET = 3.0


def is_valid_hex(value: str) -> bool:
    return bool(value) and bool(HEX_COLOR_RE.match(value))


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    hex_color = hex_color.lstrip("#")
    return int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)


def _rgb_to_hex(r: float, g: float, b: float) -> str:
    def clamp(c):
        return max(0, min(255, round(c)))

    return f"#{clamp(r):02X}{clamp(g):02X}{clamp(b):02X}"


def relative_luminance(color) -> float:
    """روشنایی نسبی رنگ (WCAG 2.x، آستانهٔ sRGB ‎0.04045‎). هر رنگِ CSS
    (hex/rgb()/rgba()) را می‌پذیرد؛ آلفا نادیده گرفته می‌شود — برای رنگِ
    نیمه‌شفاف از ``ratio_between``/``flatten`` استفاده کنید."""
    r, g, b, _a = parse_css_color(color)
    return _luminance_rgb(r, g, b)


def contrast_ratio(hex_a: str, hex_b: str) -> float:
    """نسبت کنتراست WCAG بین دو رنگِ *کاملاً مات* (از ۱ تا ۲۱)."""
    lum_a, lum_b = relative_luminance(hex_a), relative_luminance(hex_b)
    lighter, darker = max(lum_a, lum_b), min(lum_a, lum_b)
    return (lighter + 0.05) / (darker + 0.05)


def foreground_for(bg_hex: str) -> str:
    """رنگ پیش‌زمینه‌ی امن (سفید یا سیاه) بر اساس روشنایی پس‌زمینه."""
    try:
        return best_foreground(bg_hex)
    except (ValueError, IndexError):
        return "#FFFFFF"


def mix_hex(hex_a: str, hex_b: str, ratio: float) -> str:
    """ترکیب خطی دو رنگ در فضای RGB؛ ratio سهم hex_a است (بین ۰ و ۱)."""
    ratio = max(0.0, min(1.0, ratio))
    ra, ga, ba = _hex_to_rgb(hex_a)
    rb, gb, bb = _hex_to_rgb(hex_b)
    return _rgb_to_hex(
        ra * ratio + rb * (1 - ratio),
        ga * ratio + gb * (1 - ratio),
        ba * ratio + bb * (1 - ratio),
    )


def darken_hex(hex_color: str, amount: float = 0.12) -> str:
    """تیره‌کردن رنگ با ترکیب با سیاه — برای حالت hover دکمه‌های اصلی."""
    return mix_hex("#000000", hex_color, amount)


def safe_hex(value: str, default: str) -> str:
    """بازگشت رنگ هگز معتبر یا مقدار پیش‌فرض — هرگز مقدار خام نامعتبر به CSS نمی‌رسد."""
    return value if is_valid_hex(value) else default


# ---------------------------------------------------------------------------
# CSS colour parsing + alpha compositing
# ---------------------------------------------------------------------------
# An "RGBA" in this module is ``(r, g, b, a)`` with r/g/b in 0..255 (floats
# allowed after compositing) and a in 0..1.

_NAMED_COLORS = {
    "black": (0, 0, 0, 1.0),
    "white": (255, 255, 255, 1.0),
    "transparent": (0, 0, 0, 0.0),
}
_FUNC_RE = re.compile(r"^(rgba?|color)\(\s*(.*?)\s*\)$", re.IGNORECASE)


def _channel(token: str, scale: float) -> float:
    token = token.strip()
    if token.endswith("%"):
        return float(token[:-1]) / 100.0 * scale
    return float(token)


def parse_css_color(value) -> tuple[float, float, float, float]:
    """Parse ``#rgb``/``#rgba``/``#rrggbb``/``#rrggbbaa``, ``rgb()``/``rgba()``
    (legacy comma and modern space/slash syntax, ``%`` allowed),
    ``color(srgb r g b / a)`` and the keywords black/white/transparent.

    Also accepts an already-parsed 3/4-tuple. Raises ``ValueError`` for
    anything it cannot resolve to a concrete sRGB colour (``var()``,
    ``color-mix()``, ``currentColor`` … must be resolved by the browser first —
    the runtime audit asks the browser for computed values).
    """
    if isinstance(value, (tuple, list)):
        if len(value) == 3:
            return (float(value[0]), float(value[1]), float(value[2]), 1.0)
        if len(value) == 4:
            return (float(value[0]), float(value[1]), float(value[2]), float(value[3]))
        raise ValueError(f"unsupported colour tuple: {value!r}")
    text = str(value).strip().lower()
    if text in _NAMED_COLORS:
        r, g, b, a = _NAMED_COLORS[text]
        return (float(r), float(g), float(b), a)
    if text.startswith("#"):
        digits = text[1:]
        if not re.fullmatch(r"[0-9a-f]+", digits) or len(digits) not in (3, 4, 6, 8):
            raise ValueError(f"unsupported hex colour: {value!r}")
        if len(digits) in (3, 4):
            digits = "".join(ch * 2 for ch in digits)
        r, g, b = (int(digits[i:i + 2], 16) for i in (0, 2, 4))
        a = int(digits[6:8], 16) / 255.0 if len(digits) == 8 else 1.0
        return (float(r), float(g), float(b), a)
    match = _FUNC_RE.match(text)
    if match:
        kind, body = match.group(1), match.group(2)
        alpha = 1.0
        if "/" in body:
            body, alpha_token = body.split("/", 1)
            alpha = _channel(alpha_token, 1.0)
        parts = [p for p in re.split(r"[\s,]+", body.strip()) if p]
        if kind == "color":
            if not parts or parts[0] != "srgb" or len(parts) < 4:
                raise ValueError(f"unsupported color() space: {value!r}")
            r, g, b = (_channel(p, 1.0) * 255.0 for p in parts[1:4])
            if len(parts) >= 5:
                alpha = _channel(parts[4], 1.0)
        else:
            if len(parts) not in (3, 4):
                raise ValueError(f"unsupported rgb() arity: {value!r}")
            r, g, b = (_channel(p, 255.0) for p in parts[:3])
            if len(parts) == 4:
                alpha = _channel(parts[3], 1.0)
        return (r, g, b, max(0.0, min(1.0, alpha)))
    raise ValueError(f"unsupported CSS colour: {value!r}")


def composite(fg, bg) -> tuple[float, float, float, float]:
    """Source-over: ``fg`` (may carry alpha) painted on ``bg`` (may carry alpha)."""
    fr, fgr, fb, fa = parse_css_color(fg)
    br, bgr, bb, ba = parse_css_color(bg)
    out_a = fa + ba * (1.0 - fa)
    if out_a <= 0.0:
        return (0.0, 0.0, 0.0, 0.0)
    def mix(f, b):
        return (f * fa + b * ba * (1.0 - fa)) / out_a
    return (mix(fr, br), mix(fgr, bgr), mix(fb, bb), out_a)


def flatten(color, backdrop="#FFFFFF") -> tuple[float, float, float]:
    """Resolve a (possibly translucent) colour to opaque RGB over ``backdrop``."""
    r, g, b, _a = composite(color, composite(backdrop, "#FFFFFF"))
    return (r, g, b)


def to_hex(color) -> str:
    r, g, b, _a = parse_css_color(color)
    return _rgb_to_hex(r, g, b)


def _luminance_rgb(r: float, g: float, b: float) -> float:
    def linearize(c):
        c = max(0.0, min(255.0, c)) / 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * linearize(r) + 0.7152 * linearize(g) + 0.0722 * linearize(b)


def ratio_between(fg, bg, backdrop="#FFFFFF") -> float:
    """WCAG contrast of ``fg`` on ``bg`` where either may be translucent.

    ``bg`` is first flattened over ``backdrop`` (the page canvas by default),
    then ``fg`` is composited over that flattened background — exactly what
    the eye sees for translucent text on a translucent panel.
    """
    flat_bg = flatten(bg, backdrop)
    flat_fg = flatten(fg, flat_bg)
    lum_fg = _luminance_rgb(*flat_fg)
    lum_bg = _luminance_rgb(*flat_bg)
    lighter, darker = max(lum_fg, lum_bg), min(lum_fg, lum_bg)
    return (lighter + 0.05) / (darker + 0.05)


def required_ratio(font_px: float = 16.0, font_weight: int = 400) -> float:
    """WCAG "large text": >= 24px, or >= 18.66px (14pt) when bold (>= 700)."""
    if font_px >= 24.0 or (font_px >= 18.66 and font_weight >= 700):
        return AA_LARGE_TEXT
    return AA_NORMAL_TEXT


# ---------------------------------------------------------------------------
# Accessible colour derivation
# ---------------------------------------------------------------------------

def best_foreground(bg, candidates=("#FFFFFF", "#000000")) -> str:
    """The candidate with the highest WCAG contrast on ``bg`` (ties keep order)."""
    best, best_ratio = None, -1.0
    for candidate in candidates:
        ratio = ratio_between(candidate, bg)
        if ratio > best_ratio + 1e-9:
            best, best_ratio = candidate, ratio
    return best


def ensure_contrast(fg, backdrops, min_ratio: float = AA_NORMAL_TEXT) -> str:
    """Smallest change to ``fg`` so it reaches ``min_ratio`` on EVERY backdrop.

    Hue is preserved by mixing ``fg`` toward black or white (whichever direction
    can satisfy all backdrops with the least movement) — never a RGB-average
    brightness guess; every step is measured with WCAG luminance. A colour that
    already passes is returned unchanged (merchant identity untouched). If
    ``min_ratio`` cannot be met even by pure black/white the closest achievable
    colour (pure black or white) is returned.
    """
    if isinstance(backdrops, (str, tuple, list)) and not (
        isinstance(backdrops, (tuple, list)) and backdrops and isinstance(backdrops[0], (str, tuple, list))
    ):
        backdrops = [backdrops]
    backdrops = list(backdrops)
    start = to_hex(fg)

    def worst(color):
        return min(ratio_between(color, b) for b in backdrops)

    if worst(start) >= min_ratio:
        return start.upper()

    best_choice, best_t = None, None
    for target in ("#000000", "#FFFFFF"):
        if worst(target) < min_ratio:
            continue
        lo, hi = 0.0, 1.0
        for _ in range(24):
            mid = (lo + hi) / 2.0
            if worst(mix_hex(target, start, mid)) >= min_ratio:
                hi = mid
            else:
                lo = mid
        if best_t is None or hi < best_t:
            best_choice, best_t = mix_hex(target, start, hi), hi
    if best_choice is None:
        black, white = worst("#000000"), worst("#FFFFFF")
        return "#000000" if black >= white else "#FFFFFF"
    # mix_hex rounds to 8-bit; nudge one more step if rounding fell below the bar
    candidate = best_choice
    target = "#000000" if worst("#000000") >= worst("#FFFFFF") else "#FFFFFF"
    for _ in range(8):
        if worst(candidate) >= min_ratio:
            break
        candidate = mix_hex(target, candidate, 0.04)
    return candidate.upper()


def state_pair(bg, *, toward: str = "#000000", amount: float = 0.12,
               min_ratio: float = AA_NORMAL_TEXT) -> tuple[str, str]:
    """(state_background, state_foreground) for hover/active of a filled control.

    The background is nudged by ``amount`` toward ``toward`` and the foreground
    is re-derived for THAT background, so a state change can never leave an
    inherited foreground on an incompatible background. If the nudge would make
    the best of black/white fall under ``min_ratio`` (mid-tones near the
    black/white crossover), the nudge is reduced until it does not.
    """
    start = to_hex(bg)
    for step in range(12):
        shade = mix_hex(toward, start, amount * (1.0 - step / 12.0))
        fg = best_foreground(shade)
        if ratio_between(fg, shade) >= min_ratio:
            return shade.upper(), fg
    return start.upper(), best_foreground(start)
