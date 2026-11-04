"""Picture guidance for the Inspector's ``media`` fields — one generic registry, no per-template branch.

A section that wants size / ratio / safe-area advice for its picture slots registers a ``media_guide_spec()`` here; every other section's
picture field still gets the shared picker (thumbnail, filename, upload, remove) with the neutral, always-true advice."""

from __future__ import annotations

from . import hero_stage

#: section_key -> callable returning the JSON-serialisable guide spec (see ``hero_stage.media_guide_spec``)
_SPECS = {
    hero_stage.SECTION_KEY: hero_stage.media_guide_spec,
}

#: shown for any picture field without its own spec
GENERIC_ADVICE = {
    "recommended": "تصویر افقی با کیفیت و حداقل عرض ۱۲۰۰ پیکسل",
    "limits": "فرمت‌های JPG، PNG و WebP — حداکثر ۵ مگابایت",
}


def spec_for_section(section_key: str) -> dict | None:
    builder = _SPECS.get(section_key)
    return builder() if builder else None
