"""Settings-workspace layout — how a section's schema fields are arranged in the large settings workspace.

The Inspector body is schema-driven: every control already exists as a ``SettingsField`` (or a compound widget such as the
design block). This module only decides WHERE each existing field is shown — which primary tab (محتوا / طراحی / پیشرفته)
and which titled card inside it — from the field's *type* and *key*. It is generic engine metadata:

* it never branches on a section key or a Ready Template key, so every present and future section gets the same
  structure automatically;
* it never adds, drops, renames or re-validates a field — each input field lands in exactly one card, once;
* it is display metadata only (the mutation pipeline, schema validation and ``visible_when`` rules are untouched).
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

#: card id -> (merchant-facing title, short hint shown under the title)
CARD_META: dict[str, tuple[str, str]] = {
    "text": ("متن و عنوان", "آنچه بازدیدکننده می‌خواند"),
    "items": ("آیتم‌ها و رسانه", "تصویرها، لینک‌ها و موارد این بخش"),
    "source": ("منبع و نمایش", "چه چیزی و چگونه نشان داده شود"),
    "background": ("پس‌زمینه", "رنگ، الگو یا تصویر پشت این بخش"),
    "style": ("ظاهر و استایل", "رنگ، حاشیه، سایه، فاصله و دکمه‌ها"),
    "colors": ("رنگ‌ها", "رنگ‌های معنایی این بخش"),
    "layout": ("چیدمان", "ستون‌ها، جایگاه عنوان و رفتار ردیف"),
    "campaign": ("پنل کمپین", "پنل تبلیغاتی کنار محصولات"),
    "spacing": ("فاصله‌ها", "فاصلهٔ بین کارت‌ها"),
    "typography": ("تایپوگرافی", "فونت و اندازهٔ نوشته‌ها"),
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
    "behavior": (TAB_ADVANCED, COLUMN_MAIN),
    "other": (TAB_ADVANCED, COLUMN_MAIN),
    "manage": (TAB_ADVANCED, COLUMN_SIDE),
}

#: Order of cards inside a column.
_CARD_ORDER = tuple(CARD_META)

_LAYOUT_KEY = re.compile(
    r"^(header_position|heading_style|desktop_layout|overflow_mode|text_position|layout_variant|image_position|"
    r"(desktop|tablet|mobile)_(columns|height))$"
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

    @property
    def field_count(self) -> int:
        return len(self.fields)


@dataclass
class WorkspaceTab:
    key: str
    label: str
    main: list = dc_field(default_factory=list)
    side: list = dc_field(default_factory=list)

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


def build_workspace_tabs(fields, *, has_media_manager: bool = False, include_manage_card: bool = True) -> list[WorkspaceTab]:
    """Arrange ``fields`` into the three primary tabs. Every field appears in exactly one card, in schema order.

    ``has_media_manager`` adds the section's inline media manager to the first Content card;
    ``include_manage_card`` adds the (field-less) section-management card to Advanced."""
    cards: dict[str, WorkspaceCard] = {}

    def card(card_id: str) -> WorkspaceCard:
        if card_id not in cards:
            label, hint = CARD_META[card_id]
            cards[card_id] = WorkspaceCard(key=card_id, label=label, hint=hint)
        return cards[card_id]

    for schema_field in fields:
        card(classify_field(schema_field)).fields.append(schema_field)
    if has_media_manager:
        card("items").has_media_manager = True
    if include_manage_card:
        card("manage").is_manage = True

    tabs = {key: WorkspaceTab(key=key, label=TAB_LABELS_FA[key]) for key in TAB_ORDER}
    for card_id in _CARD_ORDER:
        if card_id not in cards:
            continue
        tab_key, column = CARD_PLACEMENT[card_id]
        getattr(tabs[tab_key], column).append(cards[card_id])
    return [tabs[key] for key in TAB_ORDER]
