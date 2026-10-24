"""Settings-workspace layout — how a section's schema fields are arranged in the large settings workspace.

The Inspector body is schema-driven: every control already exists as a ``SettingsField`` (or a compound widget such as the
design block). This module only decides WHERE each existing field is shown — which primary tab (محتوا / طراحی / پیشرفته)
and which titled card inside it — from the field's *type* and *key*. It is generic engine metadata:

* it never branches on a section key or a Ready Template key, so every present and future section gets the same
  structure automatically;
* it never adds, drops, renames or re-validates a field — each input field lands in exactly one card, once;
* it is display metadata only (the mutation pipeline, schema validation and ``visible_when`` rules are untouched).

R4-10 — the Design tab is split into five SUB-SECTIONS (پس‌زمینه / رنگ‌ها و دکمه‌ها / کارت‌ها و جلوه‌ها / چیدمان و فاصله‌ها /
تصاویر و نمایش در دستگاه‌ها) so the merchant never scrolls one very long list. The split is the same generic metadata: a
card belongs to a sub-section by its id, and the single compound ``design`` field is shown as one *slice* per sub-section
from the section's own applicable properties (``design_block.serialize_registry_for_inspector``), so a control appears
only where the section really supports it. No schema, stored value or mutation changes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field as dc_field

TAB_CONTENT = "content"
TAB_DESIGN = "design"
TAB_ADVANCED = "advanced"
TAB_ORDER = (TAB_CONTENT, TAB_DESIGN, TAB_ADVANCED)
TAB_LABELS_FA = {TAB_CONTENT: "محتوا", TAB_DESIGN: "طراحی", TAB_ADVANCED: "پیشرفته"}

COLUMN_MAIN = "main"
COLUMN_SIDE = "side"

SUB_BACKGROUND = "background"
SUB_COLORS = "colors"
SUB_CARDS = "cards"
SUB_LAYOUT = "layout"
SUB_IMAGES = "images"
#: the Design tab's sub-sections, in the order the merchant sees them: (key, title, one-line hint)
DESIGN_SUBSECTIONS: tuple[tuple[str, str, str], ...] = (
    (SUB_BACKGROUND, "پس‌زمینه", "نوع پس‌زمینه، رنگ دلخواه، تصویر یا الگو و امتداد تا لبهٔ صفحه"),
    (SUB_COLORS, "رنگ‌ها و دکمه‌ها", "رنگ متن، عنوان، تأکید، قیمت و دکمه‌ها"),
    (SUB_CARDS, "کارت‌ها و جلوه‌ها", "رنگ سطح کارت‌ها، حاشیه، گردی گوشه‌ها و سایه"),
    (SUB_LAYOUT, "چیدمان و فاصله‌ها", "جایگاه و سبک عنوان، تراز، فاصله‌ها، ارتفاع، ستون‌ها"),
    (SUB_IMAGES, "تصاویر و نمایش در دستگاه‌ها", "نسبت و جاگیری تصویر، نمایش در دسکتاپ، تبلت و موبایل"),
)

#: card id -> (merchant-facing title, short hint shown under the title)
CARD_META: dict[str, tuple[str, str]] = {
    "text": ("متن و عنوان", "آنچه بازدیدکننده می‌خواند"),
    "items": ("آیتم‌ها و رسانه", "تصویرها، لینک‌ها و موارد این بخش"),
    "source": ("منبع و نمایش", "چه چیزی و چگونه نشان داده شود"),
    "background": ("پس‌زمینه", "رنگ یا تصویر پشت کل این بخش"),
    "style": ("ظاهر و استایل", "رنگ سطح کارت‌ها، حاشیه، سایه، فاصله و دکمه‌ها"),
    "colors": ("رنگ‌ها", "رنگ‌های معنایی این بخش"),
    "layout": ("چیدمان", "ستون‌ها، جایگاه عنوان و رفتار ردیف"),
    "campaign": ("پنل کمپین", "پنل تبلیغاتی کنار محصولات"),
    "spacing": ("فاصله‌ها", "فاصلهٔ بین کارت‌ها"),
    "typography": ("تایپوگرافی", "فونت و اندازهٔ نوشته‌ها"),
    "images": ("تصویر", "جای تصویر در این بخش"),
    "behavior": ("رفتار و حرکت", "پخش خودکار، فلش‌ها، نقطه‌ها و اسکرول"),
    "other": ("تنظیمات دیگر", ""),
    "manage": ("مدیریت بخش", "نمایش، قفل، جایگاه و حذف"),
}

#: ``(tab, column)`` per card; a card is only rendered when it holds at least one field.
CARD_PLACEMENT: dict[str, tuple[str, str]] = {
    "text": (TAB_CONTENT, COLUMN_MAIN),
    "items": (TAB_CONTENT, COLUMN_MAIN),
    "source": (TAB_CONTENT, COLUMN_SIDE),
    "background": (TAB_DESIGN, COLUMN_MAIN),
    "style": (TAB_DESIGN, COLUMN_MAIN),
    "colors": (TAB_DESIGN, COLUMN_MAIN),
    "layout": (TAB_DESIGN, COLUMN_SIDE),
    "campaign": (TAB_DESIGN, COLUMN_SIDE),
    "spacing": (TAB_DESIGN, COLUMN_SIDE),
    "typography": (TAB_DESIGN, COLUMN_SIDE),
    "images": (TAB_DESIGN, COLUMN_SIDE),
    "behavior": (TAB_ADVANCED, COLUMN_MAIN),
    "other": (TAB_ADVANCED, COLUMN_MAIN),
    "manage": (TAB_ADVANCED, COLUMN_SIDE),
}

#: Design-tab card id -> sub-section. ``style`` (the whole ``design`` field in ONE card) is only the fallback used when the
#: caller does not pass the section's applicable design groups; normally the field is shown as slices (below).
CARD_SUBSECTION: dict[str, str] = {
    "background": SUB_BACKGROUND,
    "colors": SUB_COLORS,
    "style": SUB_CARDS,
    "campaign": SUB_CARDS,
    "layout": SUB_LAYOUT,
    "spacing": SUB_LAYOUT,
    "typography": SUB_LAYOUT,
    "images": SUB_IMAGES,
}

#: design block property -> sub-section. Anything not listed follows its design GROUP (``_GROUP_SUBSECTION``), so a property
#: added to the registry later lands somewhere sensible without touching this module.
_PROP_SUBSECTION: dict[str, str] = {"surface_color": SUB_CARDS}
_GROUP_SUBSECTION: dict[str, str] = {
    "colors": SUB_COLORS, "actions": SUB_COLORS,
    "border": SUB_CARDS, "shadow": SUB_CARDS,
    "spacing": SUB_LAYOUT, "layout": SUB_LAYOUT,
    "image": SUB_IMAGES, "visibility": SUB_IMAGES,
}
#: a slice shows the original design groups; this renames the one group that is split across two sub-sections
_SLICE_GROUP_LABEL: dict[tuple[str, str], str] = {("colors", SUB_CARDS): "رنگ سطح کارت‌ها"}
#: the card that holds each design slice: (title, hint)
DESIGN_SLICE_META: dict[str, tuple[str, str]] = {
    SUB_COLORS: ("رنگ متن، قیمت و دکمه‌ها", "رنگ نوشته‌ها و دکمه‌های این بخش"),
    SUB_CARDS: ("کارت، حاشیه و سایه", "سطح کارت‌ها، حاشیه، گردی گوشه‌ها و سایه"),
    SUB_LAYOUT: ("ابعاد و فاصله‌ها", "فاصلهٔ داخلی و بیرونی، ارتفاع، تراز و ستون‌ها"),
    SUB_IMAGES: ("تصویر و نمایش در دستگاه‌ها", "نسبت و جاگیری تصویر، نمایش در دسکتاپ، تبلت و موبایل"),
}

#: Order of cards inside a column.
_CARD_ORDER = tuple(CARD_META)

_LAYOUT_KEY = re.compile(
    r"^(header_position|heading_style|desktop_layout|overflow_mode|text_position|layout_variant|layout_mode|"
    r"(desktop|tablet|mobile)_(columns|height)|"
    # V5 PDP controls (``pdp_settings``): gallery / thumbnails / info panel / price / quantity / option / CTA arrangement and the
    # description section's tab / panel presentation — all «چیدمان» choices, so they sit in the Design tab with the other layout controls
    r"(gallery|thumbs|info|price|qty|option|cta|tab|panel)_[a-z_]+)$"
)
_SPACING_KEY = re.compile(r"^(gap|row_gap|column_gap)$")
_BEHAVIOR_KEY = re.compile(
    r"^(carousel_.+|autoplay|interval_ms|show_arrows|show_dots|loop|transition|show_scrollbar)$"
)


@dataclass
class WorkspaceCard:
    key: str
    label: str
    hint: str
    fields: list = dc_field(default_factory=list)
    #: renders the section's inline media manager at the top of the card (it is not a ``SettingsField``)
    has_media_manager: bool = False
    #: renders the studio's section-management actions (visibility / lock / position / remove) in the card
    is_manage: bool = False
    #: Design-tab sub-section this card belongs to ("" outside the Design tab)
    subsection: str = ""
    #: for a design SLICE card: the design groups (subset of the section's applicable ones) it shows
    design_groups: list | None = None

    @property
    def field_count(self) -> int:
        return len(self.fields)


@dataclass
class WorkspaceSubsection:
    key: str
    label: str
    hint: str
    main: list = dc_field(default_factory=list)
    side: list = dc_field(default_factory=list)

    @property
    def cards(self) -> list:
        return [*self.main, *self.side]

    @property
    def columns(self) -> list:
        return [(COLUMN_MAIN, self.main), (COLUMN_SIDE, self.side)]

    @property
    def is_single_column(self) -> bool:
        return not self.side or not self.main


@dataclass
class WorkspaceTab:
    key: str
    label: str
    main: list = dc_field(default_factory=list)
    side: list = dc_field(default_factory=list)
    #: only the Design tab has sub-sections (R4-10); ``main``/``side`` still hold every card of the tab
    subsections: list = dc_field(default_factory=list)

    @property
    def cards(self) -> list:
        return [*self.main, *self.side]

    @property
    def columns(self) -> list:
        """``[(name, cards), ...]`` in reading order (main first) — what the template iterates."""
        return [(COLUMN_MAIN, self.main), (COLUMN_SIDE, self.side)]

    @property
    def is_single_column(self) -> bool:
        return not self.side or not self.main


def classify_field(field) -> str:
    """The card id a single ``SettingsField`` belongs to (generic: field type + key + schema group only)."""
    key = field.key
    ftype = field.field_type
    if key.startswith("campaign_"):
        return "campaign"
    if ftype == "background":
        return "background"
    if ftype == "design":
        return "style"
    if ftype == "color":
        return "colors"
    if ftype == "appearance_override":
        return "typography"
    if _SPACING_KEY.match(key):
        return "spacing"
    if key == "image_position":
        return "images"
    if _LAYOUT_KEY.match(key):
        return "layout"
    if field.group == "advanced":
        # the schema author already marked these "advanced": motion/behaviour keys get their own card
        return "behavior" if _BEHAVIOR_KEY.match(key) else "other"
    if ftype in ("text", "rich_text", "menu_picker"):
        return "text"
    if ftype in ("repeater", "media"):
        return "items"
    return "source"


def design_property_subsection(prop_key: str, group: str) -> str:
    """The Design sub-section one design-block property is shown in (explicit override, else its design group)."""
    return _PROP_SUBSECTION.get(prop_key) or _GROUP_SUBSECTION.get(group, SUB_LAYOUT)


def split_design_groups(design_groups) -> dict[str, list[dict]]:
    """``{sub-section: [design group, ...]}`` — the section's applicable design groups, partitioned by sub-section.

    Pure re-grouping of the SAME property dicts: nothing is added, dropped or altered, a group that straddles two
    sub-sections is simply listed in both with only its own properties, and the order inside each group is kept."""
    out: dict[str, list[dict]] = {}
    for group in design_groups or ():
        buckets: dict[str, list[dict]] = {}
        for prop in group.get("properties", ()):
            buckets.setdefault(design_property_subsection(prop["key"], group["group"]), []).append(prop)
        for sub, props in buckets.items():
            out.setdefault(sub, []).append({
                **group,
                "label": _SLICE_GROUP_LABEL.get((group["group"], sub), group["label"]),
                "properties": props,
            })
    return out


def build_workspace_tabs(
    fields, *, has_media_manager: bool = False, include_manage_card: bool = True, design_groups=None,
) -> list[WorkspaceTab]:
    """Arrange ``fields`` into the three primary tabs. Every field appears in at least one card, in schema order — exactly one
    card for every field except the compound ``design`` field, which is shown as one *slice* per Design sub-section.

    ``has_media_manager`` adds the section's inline media manager to the first Content card;
    ``include_manage_card`` adds the (field-less) section-management card to Advanced;
    ``design_groups`` (the section's applicable design groups) lets the ``design`` field be sliced by sub-section — without
    it the field stays ONE card (``style``)."""
    cards: dict[str, WorkspaceCard] = {}

    def card(card_id: str) -> WorkspaceCard:
        if card_id not in cards:
            label, hint = CARD_META[card_id]
            cards[card_id] = WorkspaceCard(key=card_id, label=label, hint=hint)
        return cards[card_id]

    slices = split_design_groups(design_groups)
    for schema_field in fields:
        card_id = classify_field(schema_field)
        if card_id == "style" and slices:
            for sub_key, _title, _hint in DESIGN_SUBSECTIONS:
                if sub_key not in slices:
                    continue
                label, hint = DESIGN_SLICE_META[sub_key]
                slice_id = f"style-{sub_key}"
                cards[slice_id] = WorkspaceCard(
                    key=slice_id, label=label, hint=hint, fields=[schema_field],
                    subsection=sub_key, design_groups=slices[sub_key],
                )
            continue
        card(card_id).fields.append(schema_field)
    if has_media_manager:
        card("items").has_media_manager = True
    if include_manage_card:
        card("manage").is_manage = True

    tabs = {key: WorkspaceTab(key=key, label=TAB_LABELS_FA[key]) for key in TAB_ORDER}
    subsections = {key: WorkspaceSubsection(key=key, label=title, hint=hint) for key, title, hint in DESIGN_SUBSECTIONS}
    # slices sit where the ``style`` card used to sit in the reading order
    order: list[str] = []
    for card_id in _CARD_ORDER:
        if card_id == "style":
            order.extend(key for key in cards if key.startswith("style-"))
        if card_id in cards:
            order.append(card_id)
    for card_id in order:
        item = cards[card_id]
        if card_id.startswith("style-"):
            tab_key, column = TAB_DESIGN, COLUMN_MAIN
        else:
            tab_key, column = CARD_PLACEMENT[card_id]
        getattr(tabs[tab_key], column).append(item)
        if tab_key == TAB_DESIGN:
            sub = item.subsection or CARD_SUBSECTION[card_id]
            item.subsection = sub
            getattr(subsections[sub], column).append(item)
    tabs[TAB_DESIGN].subsections = [sub for key, _t, _h in DESIGN_SUBSECTIONS if (sub := subsections[key]).cards]
    return [tabs[key] for key in TAB_ORDER]
