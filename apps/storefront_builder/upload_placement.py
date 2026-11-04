"""V5 — the REAL place a picture will occupy, read from the Draft layout (read-only; never writes, never creates a Draft).

``upload_frames`` resolves *which kind of frame* a slot is shown in (template card style, hero ratio …). For a picture that lives directly in a
Section of a Container Cell the frame is also decided by WHERE it sits: which Container preset, which Cell, how the merchant dragged the column
and height dividers, the Section's own width / height / fit / focal settings, the store's content width and the phone layout. This module
turns exactly those stored facts into numbers — the same constants the storefront CSS uses (``.wrap`` = content width − 36px padding, a 12-column
grid with the Container's gap, ``--cell-span``, ``stack_split``, ``width_pct``, ``min_height``) — and reports how sure it is:

* ``exact``    — every input is known (a manual height, or the neighbours' real pictures);
* ``approx``   — the height depends on something not yet known (a neighbour Cell without a picture, a drag split, equal-height rows):
                 the value is a stated assumption / range and is never presented as an exact size;
* ``free``     — the Section keeps the picture's own ratio (no manual height), so only the width is fixed and any ratio fits without cropping.

Reference screens: a 1440px desktop and a 390px phone (the numbers scale with the viewport; the guide says so).
Nothing here touches a file, a setting, a Section or a Layout."""

from __future__ import annotations

from math import ceil

from . import design_block
from .services import container_service

REF_DESKTOP_VW = 1440
REF_MOBILE_VW = 390
PHONE_MAX_VW = 680            # ≤ this width the «mobile» picture is the one shown, and .wrap keeps 18px of page margin
STACK_MAX_VW = 1000           # ≤ this width an «stack» Container puts its Cells under each other
WRAP_PADDING = 36             # .wrap{padding:0 18px}
PHONE_MIN_HEIGHT_SHARE = 0.8  # a manual height never forces more than 80vw of room on a phone (storefront_builder.css)
DPR = 2                       # recommended file = 2× the displayed width (retina) …
MAX_RECOMMENDED_WIDTH = 2400  # … but never an unnecessarily heavy file
#: with nothing known about the neighbours of the big Cell, the two small Cells are assumed square — said out loud, never as a measurement
ASSUMED_SMALL_RATIO = 1.0

_CELL_NAMES_STACKED = ("خانهٔ بزرگ", "خانهٔ کوچک بالا", "خانهٔ کوچک پایین")


def _design(section) -> dict:
    raw = (section.settings or {}).get("design") if isinstance(section.settings, dict) else None
    return raw if isinstance(raw, dict) else {}


def _int(value, default=0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def content_width(version, page) -> int:
    """The store's ``--sfb-content-width`` for this page — the identical resolution the storefront context processor performs."""
    from . import appearance_registry
    from .services.appearance_authority_service import effective_page_appearance_config

    config = effective_page_appearance_config(store_appearance_config=version.effective_appearance_config(), page=page)
    template = appearance_registry.get_template(config.get("template_slug")) or appearance_registry.get_template("modern")
    return _int(config.get("content_width") or getattr(template, "content_width", 0), 1200)


def inner_width(content: int, viewport: int) -> float:
    """Width of the area a Container fills: ``.wrap`` is min(content width, viewport − page margin), less its 18px side padding."""
    margin = 28 if viewport > PHONE_MAX_VW else 18
    return float(min(content, viewport - margin) - WRAP_PADDING)


def cell_width(span: int, inner: float, gap: int) -> float:
    column = (inner - 11 * gap) / 12
    return span * column + (span - 1) * gap


def _natural_ratio(section):
    """height/width of the Section's own desktop picture (a linked image), read from the stored file; ``None`` when unknown."""
    from apps.content.models import PromotionalBanner

    banner = PromotionalBanner.objects.filter(section=section, is_active=True).order_by("display_order", "id").first()
    if banner is None:
        return None
    for field in ((banner.desktop_asset.image if banner.desktop_asset_id else None), banner.desktop_image):
        try:
            if field:
                width, height = field.width, field.height
                if width and height:
                    return height / width
        except Exception:  # a missing / unreadable file simply means «unknown» — the guide is advisory
            continue
    return None


def _sibling_height(cell, width: float):
    """Rendered height of the single Section in ``cell`` when it is a linked image whose picture is known; else ``None``."""
    blocks = container_service.get_cell_blocks(cell)
    blocks = [b for b in blocks if b.is_active]
    if len(blocks) != 1 or blocks[0].section_key != "linked_image":
        return None
    block = blocks[0]
    ratio = _natural_ratio(block)
    if ratio is None:
        return None
    design = _design(block)
    w = width * (_int(design.get("width_pct"), 100) / 100 if _int(design.get("width_pct"), 100) < 100 else 1)
    return max(w * ratio, float(_int(design.get("min_height"))))


def _stacked_heights(cells, widths, target_index, split, gap):
    """Frame height of the target Cell in a «big + two small» Container for a picture that FILLS its frame.

    Returns ``(height, kind)``: ``"free"`` — the frame is as tall as its own picture (any ratio fits, ``height`` is ``None``);
    ``"siblings"`` — computed from the neighbours' real pictures; ``"assumed"`` — a stated assumption (neighbour without a known picture, or a
    dragged height split that redistributes the rows)."""
    others = {i: _sibling_height(cells[i], widths[i]) for i in range(len(cells)) if i != target_index}
    if target_index == 0:                       # the big Cell spans both rows: as tall as the two small Cells together
        small = [others.get(1), others.get(2)]
        if None not in small:
            return small[0] + gap + small[1], ("siblings" if split is None else "assumed")
        return widths[1] * ASSUMED_SMALL_RATIO + gap + widths[2] * ASSUMED_SMALL_RATIO, "assumed"
    if split is not None:                       # a dragged divider shares the column height in %: each small row is that share of the column
        small = [others.get(1), others.get(2)]
        small = [small[k] if small[k] is not None else widths[k + 1] * ASSUMED_SMALL_RATIO for k in (0, 1)]
        column = max(others.get(0) or 0.0, small[0] + gap + small[1])
        share = split / 100 if target_index == 1 else 1 - split / 100
        return max(0.0, (column - gap) * share), "assumed"
    if target_index == 1:
        return None, "free"                     # the top small Cell is an ``auto`` row: exactly as tall as its own picture
    big, top = others.get(0), others.get(1)     # the bottom small Cell is the ``1fr`` row: it takes what the big Cell leaves
    if big is not None and top is not None:
        return big - gap - top, "siblings"
    return None, "free"


def resolve_placement(section, version=None):
    """Where ``section`` sits and the frame its picture gets (desktop + phone). ``None`` for a Section outside every Cell (legacy rows)."""
    cell = getattr(section, "cell", None)
    if cell is None:
        return None
    container = cell.container
    page = container.page
    version = version or page.version
    settings = container_service.effective_container_settings(container.settings)
    gap = int(settings["gap"])
    cells = list(container.cells.order_by("order", "id"))
    if cell.pk not in {c.pk for c in cells}:
        return None
    index = [c.pk for c in cells].index(cell.pk)
    stacked = container.layout_key in container_service.STACKED_LAYOUT_COLUMNS and len(cells) == 3
    blocks = [b for b in container_service.get_cell_blocks(cell) if b.is_active]
    design = _design(section)
    pct = _int(design.get("width_pct"), 100)
    pct = pct if 0 < pct < 100 else 100
    manual_h = _int(design.get("min_height"))
    content = content_width(version, page)
    split = settings.get("stack_split")

    if stacked:
        name = _CELL_NAMES_STACKED[index]
    elif len(cells) == 1:
        name = "خانهٔ تمام‌عرض"
    else:
        name = f"خانهٔ {index + 1} از {len(cells)}"
    if len(blocks) > 1:
        ids = [b.pk for b in blocks]
        name += f" (بخش {ids.index(section.pk) + 1 if section.pk in ids else 1} از {len(blocks)} در همین خانه)"

    def side(viewport: int, phone: bool) -> dict:
        inner = inner_width(content, viewport)
        stack_mode = settings["mobile_mode"] == "stack" and viewport <= STACK_MAX_VW
        spans = [int(c.span) for c in cells]
        widths = [inner if stack_mode else cell_width(s, inner, gap) for s in spans]
        cell_w = widths[index]
        section_w = cell_w * pct / 100
        out = {"viewport": viewport, "inner": inner, "cell_w": cell_w, "section_w": section_w, "stack_mode": stack_mode,
               "h": None, "kind": "free", "exact": False}
        # a manual height is a floor on the Section (``min-height: var(--d-minh)``) EXCEPT inside the stacked «big + two small» Cells: their own
        # rule (``… > .rcontainer-cell > .rsec { min-height: 0 }``, more specific) wins there, so the height is decided by the rows instead.
        # Pinned to the stylesheet by a test, so the day that rule changes this stops being claimed.
        manual_applies = bool(manual_h) and not stacked
        out["manual_ignored"] = bool(manual_h) and stacked
        height_floor = float(manual_h) if manual_applies else 0.0
        if phone and height_floor:
            height_floor = min(height_floor, PHONE_MIN_HEIGHT_SHARE * viewport)
        if height_floor:
            out.update(h=height_floor, kind="manual", exact=True)             # a manual height is a floor the frame fills: exact
        elif len(blocks) > 1:
            out.update(kind="shared")                                        # several Sections share this Cell: each is as tall as its own picture
        elif stacked and not stack_mode:
            h, kind = _stacked_heights(cells, widths, index, split, gap)
            if kind != "free":
                out.update(h=h, kind=kind, exact=(kind == "siblings" and split is None))
        elif settings["height_mode"] == "equal" and len(cells) > 1 and not stack_mode:
            out.update(kind="equal")                                          # taller siblings stretch this frame: depends on them
        return out

    desktop = side(REF_DESKTOP_VW, False)
    phone = side(REF_MOBILE_VW, True)
    # in a stacked cell the frame height also depends on a drag split only on desktop; a phone stacks the Cells at their own height
    return {
        "name": name, "layout_key": container.layout_key, "layout_label": container_service.LAYOUT_PRESET_LABELS_FA.get(container.layout_key, ""),
        "stacked": stacked, "cell_index": index, "cell_count": len(cells), "span": int(cell.span), "content_width": content, "gap": gap,
        "width_pct": pct, "split": split, "desktop": desktop, "phone": phone,
        "fit": design.get("image_fit") if design.get("image_fit") in ("contain", "cover") else "contain",
        "pos": design.get("image_position") if design.get("image_position") in ("top", "bottom", "left", "right", "center") else "center",
        "fit_capable": "image_fit" in design_block.applicable_properties(section.section_key),
        "pos_capable": "image_position" in design_block.applicable_properties(section.section_key),
    }


def recommended_file(width: float, ratio) -> dict:
    """File size for a frame ``width`` px wide: 2× for sharp retina screens, capped; the minimum is the displayed size (1×)."""
    rec_w = min(MAX_RECOMMENDED_WIDTH, int(ceil(width * DPR / 10.0) * 10))
    min_w = int(width + 0.5)
    if ratio:
        rec_h = int(rec_w / ratio + 0.5)
        if rec_h > MAX_RECOMMENDED_WIDTH:     # a very tall frame: scale the pair down so the file never needs to be larger than the cap on either side
            rec_w, rec_h = int(rec_w * MAX_RECOMMENDED_WIDTH / rec_h), MAX_RECOMMENDED_WIDTH
        return {"rec": (rec_w, rec_h), "min": (min_w, int(min_w / ratio + 0.5))}
    return {"rec": (rec_w, 0), "min": (min_w, 0)}
