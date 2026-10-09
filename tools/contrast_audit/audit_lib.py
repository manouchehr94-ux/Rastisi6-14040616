"""Verdict logic for the runtime contrast audit.

The in-page probe (``probe.js``) returns raw colours and paint layers; every
number below is computed with ``apps.core.color_utils`` — the same module the
storefront theme pipeline uses — so there is exactly one WCAG implementation.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from apps.core.color_utils import (  # noqa: E402
    AA_NON_TEXT,
    DISABLED_TEXT_TARGET,
    composite,
    flatten,
    ratio_between,
    required_ratio,
    to_hex,
)

IMAGE_EXTREMES = ((0.0, 0.0, 0.0, 1.0), (255.0, 255.0, 255.0, 1.0))
EPSILON = 1e-6


def _key(rgba):
    return tuple(round(v) for v in rgba[:3])


def backdrop_candidates(layers):
    """Every opaque backdrop the text could sit on, given its paint layers.

    Solid layers collapse to exactly one backdrop. A gradient contributes one
    candidate per colour stop (conservative: the text may sit anywhere along
    it). An image/video layer is "unknown pixels", bounded by pure black and
    pure white — so a scrim only passes if it is dark/light *enough* for any
    possible image, which is what makes the result deterministic.
    """
    backs = [(255.0, 255.0, 255.0, 1.0)]
    has_image = has_gradient = False
    for layer in reversed(layers):  # bottom -> top
        kind = layer["t"]
        if kind == "i":
            has_image = True
            backs = list(IMAGE_EXTREMES)
        elif kind == "g":
            has_gradient = True
            nxt = {}
            for stop in layer["s"]:
                for back in backs:
                    c = composite(stop, back)
                    nxt[_key(c)] = c
            backs = list(nxt.values())
        else:
            backs = [composite(layer["c"], b) for b in backs]
    kinds = "image" if has_image else "gradient" if has_gradient else "solid"
    return backs, kinds


@dataclass
class Verdict:
    ratio: float
    threshold: float
    passed: bool
    category: str  # solid | gradient | image-protected | image-unprotected
    bg_hex: str
    fg_hex: str
    kind: str = "text"  # text | placeholder | value | focus
    flags: list = field(default_factory=list)


def evaluate_item(item) -> Verdict | None:
    fg = tuple(item["fg"])
    flags = list(item.get("flags", []))
    size, weight = item.get("size", 16.0), item.get("weight", 400)
    threshold = required_ratio(size, weight)
    if "disabled" in flags:
        threshold = min(threshold, DISABLED_TEXT_TARGET)
    if item.get("iconOnly"):  # glyph with no letters/digits (arrows, +, bullets): a UI component, 3:1
        threshold = min(threshold, AA_NON_TEXT)

    worst = None
    category = "solid"
    for layers in item["points"]:
        backs, kind = backdrop_candidates(layers)
        if kind == "image":
            category = "image-protected" if len(layers) > 1 else "image-unprotected"
        elif kind == "gradient" and category == "solid":
            category = "gradient"
        for back in backs:
            ratio = ratio_between(fg, back)
            if worst is None or ratio < worst[0]:
                worst = (ratio, back)
    if worst is None:
        return None
    ratio, back = worst
    passed = ratio + EPSILON >= threshold
    if category.startswith("image") and category == "image-protected" and not passed:
        category = "image-unprotected"
    flat_fg = flatten(fg, back)
    return Verdict(
        ratio=ratio, threshold=threshold, passed=passed, category=category,
        bg_hex=to_hex(back), fg_hex=to_hex(flat_fg),
        kind=item.get("control") or "text", flags=flags,
    )


def _backdrop_hex(layers):
    backs, _kind = backdrop_candidates(layers)
    return backs[0] if backs else (255.0, 255.0, 255.0, 1.0)


def evaluate_focus(focused, rest):
    """(passed, detail) — is a keyboard focus indicator perceivable (>= 3:1)?

    Accepts any one of: a visible outline, a changed border colour or a new
    box-shadow ring, each of which must itself reach 3:1 against the control's
    backdrop. A control whose focus state is visually identical to rest fails.
    """
    backdrop = _backdrop_hex(focused["backdrop"]) if focused.get("backdrop") else (255, 255, 255, 1.0)
    # an outline is painted over what surrounds the control, not over the control itself
    outside = [_backdrop_hex(layers) for layers in focused.get("outside", [])] or [backdrop]
    reasons = []
    if (focused["outlineStyle"] not in ("none", "hidden") and focused["outlineWidth"] >= 1
            and focused["outlineColor"][3] > 0.05):
        ratio = min(ratio_between(focused["outlineColor"], b) for b in outside)
        reasons.append(("outline", ratio))
        # two-tone ring: a contrasting shadow ring fills the gap between control and outline, so the
        # outline is read against that ring on any surroundings.
        if focused["outlineOffset"] >= 1 and focused["boxShadow"] != "none" and focused["shadowColours"]:
            two_tone = max(ratio_between(focused["outlineColor"], c) for c in focused["shadowColours"])
            reasons.append(("two-tone outline", two_tone))
    if (focused["borderColor"] != rest["borderColor"] and focused["borderWidth"] > 0):
        from apps.core.color_utils import parse_css_color

        try:
            ratio = ratio_between(parse_css_color(focused["borderColor"]), backdrop)
            reasons.append(("border", ratio))
        except ValueError:
            pass
    if focused["boxShadow"] != rest["boxShadow"] and focused["shadowColours"]:
        ratio = max(ratio_between(c, backdrop) for c in focused["shadowColours"])
        reasons.append(("ring", ratio))
    if focused["background"] != rest["background"]:
        from apps.core.color_utils import parse_css_color

        try:
            ratio = ratio_between(parse_css_color(focused["background"]), parse_css_color(rest["background"]))
            reasons.append(("background-shift", ratio))
        except ValueError:
            pass
    if focused["textDecoration"] != rest["textDecoration"] and "underline" in focused["textDecoration"]:
        reasons.append(("underline", AA_NON_TEXT))
    if not reasons:
        return False, "no visible change between rest and focus"
    best = max(reasons, key=lambda r: r[1])
    return best[1] + EPSILON >= AA_NON_TEXT, f"{best[0]} {best[1]:.2f}:1"
