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


def _backdrop_luminances(backdrops) -> list[float]:
    return [_luminance_rgb(*flatten(b)) for b in backdrops]


def _feasible_luminance_intervals(lums: list[float], min_ratio: float) -> list[tuple[float, float]]:
    """Foreground luminances L in [0, 1] with WCAG ratio >= ``min_ratio`` on EVERY backdrop.

    The ratio depends only on luminance and is V-shaped around each backdrop's own luminance, so per backdrop the
    allowed set is ``[0, dark]`` plus ``[light, 1]``; the answer is the intersection (a short list of intervals).
    """
    intervals = [(0.0, 1.0)]
    for lb in lums:
        dark = (lb + 0.05) / min_ratio - 0.05
        light = min_ratio * (lb + 0.05) - 0.05
        allowed = []
        if dark >= 0.0:
            allowed.append((0.0, min(dark, 1.0)))
        if light <= 1.0:
            allowed.append((max(light, 0.0), 1.0))
        intervals = [
            (max(a0, b0), min(a1, b1))
            for a0, a1 in intervals for b0, b1 in allowed
            if max(a0, b0) <= min(a1, b1)
        ]
    return intervals


def _t_for_luminance(start: str, target: str, wanted: float) -> float:
    """Mix amount t in [0, 1] (0 = ``start``, 1 = ``target`` end-point) whose luminance is ``wanted``.
    Luminance is monotone along the path, so bisection is exact; 30 halvings is far below 8-bit resolution."""
    l0, l1 = relative_luminance(start), relative_luminance(target)
    if l0 == l1:
        return 0.0
    lo, hi = 0.0, 1.0
    increasing = l1 > l0
    for _ in range(30):
        mid = (lo + hi) / 2.0
        value = relative_luminance(mix_hex(target, start, mid))
        if (value < wanted) == increasing:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def ensure_contrast(fg, backdrops, min_ratio: float = AA_NORMAL_TEXT) -> str:
    """Smallest hue-preserving change to ``fg`` so it reaches ``min_ratio`` on EVERY backdrop.

    Hue is preserved by mixing ``fg`` toward black or white — never an RGB-average brightness guess; every
    candidate is verified with the WCAG formula on the final 8-bit colour. A colour that already passes is returned
    unchanged (merchant identity untouched).

    With several backdrops the passing set need not touch an end-point (red on black+white passes only in the
    mid-luminance band 0.175-0.183 and neither pure black nor pure white passes), so the search does not assume the
    end-points are feasible. The set of passing luminances is computed analytically, mapped onto each mix path
    (luminance is monotone along it) and the smallest movement wins. If ``min_ratio`` is impossible on all
    backdrops at once, the candidate with the best worst-case ratio (maximin) is returned instead of an arbitrary
    end-point. Cost is O(backdrops^2) luminance maths plus a few bisections — no per-pixel/brute-force loops.
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

    lums = _backdrop_luminances(backdrops)
    l_start = relative_luminance(start)
    paths = []
    for end in ("#000000", "#FFFFFF"):
        l_end = relative_luminance(end)
        paths.append((end, min(l_start, l_end), max(l_start, l_end)))

    best = None  # (movement t, colour) among colours that pass
    for end, lo_l, hi_l in paths:
        for a, b in _feasible_luminance_intervals(lums, min_ratio):
            a, b = max(a, lo_l), min(b, hi_l)
            if a > b:
                continue
            ta, tb = sorted((_t_for_luminance(start, end, a), _t_for_luminance(start, end, b)))
            # first try the entry edge with a few fine steps (8-bit rounding), then sweep the whole window
            steps = [ta + i / 510.0 for i in range(24) if ta + i / 510.0 <= tb] + [
                ta + (tb - ta) * i / 32.0 for i in range(33)
            ]
            for t in steps:
                candidate = mix_hex(end, start, t)
                if worst(candidate) >= min_ratio:
                    if best is None or t < best[0]:
                        best = (t, candidate)
                    break
    if best is not None:
        return best[1].upper()

    # Impossible target: maximise the worst-case ratio. worst(L) is a min of V-shapes, so its maximum is at an
    # end of the reachable range, at the start, or where two backdrops' ratios cross (geometric mean of their
    # (L + 0.05) values).
    pool = [l_start, 0.0, 1.0]
    for i, la in enumerate(lums):
        for lb in lums[i + 1:]:
            pool.append(((la + 0.05) * (lb + 0.05)) ** 0.5 - 0.05)
    choice = (worst(start), 0.0, start)
    for end, lo_l, hi_l in paths:
        for wanted in pool:
            wanted = max(lo_l, min(hi_l, wanted))
            t = _t_for_luminance(start, end, wanted)
            for dt in (-1 / 255.0, 0.0, 1 / 255.0):
                candidate = mix_hex(end, start, max(0.0, min(1.0, t + dt)))
                score = worst(candidate)
                if score > choice[0] + 1e-9 or (abs(score - choice[0]) <= 1e-9 and t < choice[1]):
                    choice = (score, t, candidate)
    return choice[2].upper()


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
