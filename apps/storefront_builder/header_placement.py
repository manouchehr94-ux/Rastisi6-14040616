"""Header placement and Header Recipes — the reusable, schema-driven way to move a «professional» header between templates.

A professional header (the four Hero-Stage Ready Templates) is NOT a separate renderer. It is two independent, already-registered facts:

* the header MODEL — a ``header_variant`` of ``global_region_registry`` (+ the show/sticky toggles), Store-global, rendered by the registered
  header renderer wherever it is drawn;
* the header PLACEMENT — the ``header_mode`` of the page's first top-level ``hero_stage`` (``independent`` = the shell draws it above the page,
  ``merged`` = inside the stage over the shared background, ``overlay`` = floating over the picture). The decision "is the header drawn inside
  the stage?" is ``render_service.header_embedded_for`` — the ONE function Preview, Draft preview and the live page share; this module asks
  the very same function (fed with lightweight items) and never re-implements it.

So a seller can take any header model and any placement independently, and a **Header Recipe** is only the pair (model, placement) read off a
Ready Template of the registry — nothing names a template, a Store or a brand, and a new Hero-Stage template appears here automatically.

Honesty rule: a placement other than ``independent`` needs the home page to open with a visible Hero Stage. When it does not, the placement is
reported as unavailable with a stable reason (never faked, never a half-rendered header, never a second header), and the model is still applied.
"""

from __future__ import annotations

from . import hero_stage

PAGE_TYPE = "home"

PLACEMENTS = (
    ("independent", "بالای صفحه (مستقل)"),
    ("merged", "داخل بوم هیرو"),
    ("overlay", "شناور روی تصویر"),
)
PLACEMENT_KEYS = tuple(key for key, _ in PLACEMENTS)

#: stable reason codes → the sentence the seller reads
REASONS = {
    "no_stage": "بالای صفحهٔ اصلی «بوم هدر و هیرو» نیست؛ هدر فقط به‌صورت مستقل (بالای صفحه) نمایش داده می‌شود. برای هدر یکپارچه، بخش «بوم هدر و هیرو» را به بالای صفحهٔ اصلی بیاورید.",
    "stage_hidden": "بوم هدر و هیرو در بعضی دستگاه‌ها پنهان است؛ برای اینکه هدر (و سبد خرید) همیشه در دسترس بماند، هدر یکپارچه فعال نمی‌شود.",
    "stage_locked": "بوم هدر و هیرو قفل است؛ ابتدا قفل آن را باز کنید.",
}


def _stage_items(draft):
    """The home page's active sections as the lightweight ``{"section", "context"}`` items ``header_embedded_for`` reads — the same filter
    ``build_page_render_items`` uses, without resolving products or media."""
    from .services import render_service

    page = draft.get_page(PAGE_TYPE)
    sections = list(page.sections.filter(is_active=True).order_by("order", "id"))
    items = [{"section": s, "context": {"settings": s.settings or {}}} for s in sections]
    use_container_layout = page.containers.exists()
    containers = render_service.build_container_render_items(page, items) if use_container_layout else None
    return render_service, items, use_container_layout, containers


def placement_state(draft) -> dict:
    """What the Studio and the mutations need to know about the header placement of this Draft.

    ``stage`` — the Hero Stage that opens the home page (or ``None``); ``mode`` — the placement the page really renders today;
    ``available`` — whether ``merged`` / ``overlay`` can be offered; ``reason`` — why not (a key of ``REASONS``)."""
    render_service, items, use_container_layout, containers = _stage_items(draft)
    first = render_service._first_top_level_item(items, use_container_layout, containers)
    section = first.get("section") if first else None
    if section is None or section.section_key != hero_stage.SECTION_KEY:
        return {"stage": None, "mode": "independent", "available": False, "reason": "no_stage"}
    settings = section.settings or {}
    responsive = settings.get("responsive") or {}
    mode = hero_stage.header_mode_of(settings)
    state = {"stage": section, "mode": mode, "available": True, "reason": ""}
    if any(responsive.get(flag) for flag in ("hide_on_desktop", "hide_on_tablet", "hide_on_mobile")):
        state.update(available=False, reason="stage_hidden")
    elif section.is_locked:
        state.update(available=False, reason="stage_locked")
    # the production decision is the authority on what is drawn: a mode that does not embed is "independent"
    embedded = render_service.header_embedded_for(items, use_container_layout=use_container_layout, render_containers=containers)
    state["rendered_mode"] = mode if embedded else "independent"
    return state


def describe(draft) -> dict:
    """The JSON-safe projection the Header Inspector renders (no model instances)."""
    state = placement_state(draft)
    return {
        "available": state["available"],
        "mode": state.get("rendered_mode", "independent"),
        "reason": state["reason"],
        "reason_text": REASONS.get(state["reason"], ""),
        "choices": [{"key": key, "label": label} for key, label in PLACEMENTS],
    }


def list_recipes() -> list[dict]:
    """The Header Recipes the registry offers: for every Ready Template a seller may select whose home page opens with a Hero Stage that draws
    the header inside itself, the pair (header model, placement) it uses. Pure registry data."""
    from . import layout_preset_registry
    from .services import r4_mutation_service

    recipes = []
    for preset in layout_preset_registry.list_selectable_templates():
        stage = r4_mutation_service.template_hero_stage_entry(preset)
        patch = r4_mutation_service.template_header_patch(preset)
        variant = patch.get("header_variant")
        if stage is None or not variant:
            continue
        mode = hero_stage.header_mode_of(stage.settings)
        if mode == "independent":
            continue
        recipes.append({
            "key": preset.key,
            "label": (preset.label_fa or preset.key).split(" (")[0].strip(),
            "variant": variant,
            "placement": mode,
        })
    return recipes


def get_recipe(key):
    return next((recipe for recipe in list_recipes() if recipe["key"] == key), None)
