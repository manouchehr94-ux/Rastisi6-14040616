"""QA-only composition lab: builds complex layouts taken from the six reference sites — and one invented, completely different one — on a
throw-away Store using NOTHING but the generic R4 mutation path the Inspector uses (``container.add`` / ``container.resize`` /
``container.update_settings`` / ``section.update_settings`` / ``footer.update``). No recipe, no template key, no site CSS.

It is used by the opt-in capture (``SFB_REFERENCE_CAPTURE="Site:lab_<name>"``) to produce screenshots and by the lab tests; it never
ships a picture (pictures come from the local reference folder at run time and only in the isolated QA database)."""

from __future__ import annotations

from ..models import StorefrontContainer, StorefrontSection
from ..services import layout_service, r4_mutation_service

LABS = ("lab_tiles", "lab_hero_panels", "lab_advisors", "lab_seventh", "lab_pdp")


class Lab:
    def __init__(self, store, owner):
        self.store, self.owner = store, owner
        layout_service.get_or_create_layout(store)
        self.draft = layout_service.get_or_create_draft(store, user=owner)
        self.clear_home()

    def clear_home(self):
        """Start from an empty Home canvas — the same ``section.remove`` the Inspector's delete button sends."""
        from ..models import StorefrontPage

        for section in list(StorefrontSection.objects.filter(page__version=self.draft, page__page_type=StorefrontPage.PageType.HOME)):
            self.mutate({"type": "section.remove", "section_id": section.pk})

    # -- the Inspector's own entry point -------------------------------------------------------------------------------------
    def mutate(self, mutation):
        self.draft.refresh_from_db()
        return r4_mutation_service.apply_mutation(
            store=self.store, actor=self.owner, base_revision=self.draft.edit_revision, mutation=mutation,
        )

    def container(self, layout, cells, *, spans=None, **settings):
        self.mutate({"type": "container.add", "page_type": "home", "layout_key": layout, "cells": cells})
        container = StorefrontContainer.objects.filter(page__version=self.draft, page__page_type="home").order_by("-id").first()
        if spans:
            self.mutate({"type": "container.resize", "container_id": container.pk, "spans": list(spans)})
        if settings:
            self.mutate({"type": "container.update_settings", "container_id": container.pk, "patch": settings})
        return container

    def section(self, key, **patch):
        """Add a standalone row (own full-width Container) and apply ``patch``."""
        self.mutate({"type": "section.add", "section_key": key, "page_type": "home"})
        section = StorefrontSection.objects.filter(page__version=self.draft, page__page_type="home", section_key=key).order_by("-id").first()
        if patch:
            self.patch(section, patch)
        return section

    def blocks(self, container, key=None):
        qs = StorefrontSection.objects.filter(cell__container=container).order_by("cell__order", "cell_order")
        return list(qs.filter(section_key=key) if key else qs)

    def patch(self, section, patch):
        self.mutate({"type": "section.update_settings", "section_id": section.pk, "patch": patch})

    def footer(self, **patch):
        self.mutate({"type": "footer.update", "patch": patch})

    def publish(self):
        layout_service.publish(self.store)


def build(name: str, store, owner, *, picture=None, publish: bool = True):
    """``picture(section)`` (optional) attaches a QA picture row to a ``linked_image`` Section. ``publish=False`` leaves the result in the Draft."""
    lab = Lab(store, owner)
    attach = picture or (lambda section: None)

    if name == "lab_tiles":
        # Khanehshokolati: four alternating tiles — text tile, photo, text tile, photo — of unequal widths.
        tiles = lab.container("quarters", [["rich_text"], ["linked_image"], ["rich_text"], ["linked_image"]],
                              spans=(3, 3, 3, 3), gap=18, height_mode="equal", vertical_align="center")
        for text in lab.blocks(tiles, "rich_text"):
            lab.patch(text, {"body_html": "<h3>عنوان کاشی</h3><p><a href=\"/\">لیست محصولات</a></p>",
                             "design": {"min_height": 300, "valign": "center", "align": "center", "radius": 22},
                             "background": {"mode": "color", "color": "#F5EBC3"}})
        for photo in lab.blocks(tiles, "linked_image"):
            lab.patch(photo, {"design": {"image_ratio": "square", "radius": 22}})
            attach(photo)
        # the same row with a different recipe of widths, to show the widths are just data
        wide = lab.container("quarters", [["linked_image"], ["rich_text"], ["linked_image"], ["rich_text"]], spans=(5, 2, 3, 2), gap=12)
        for photo in lab.blocks(wide, "linked_image"):
            lab.patch(photo, {"design": {"image_ratio": "photo", "radius": 12}})
            attach(photo)
        for text in lab.blocks(wide, "rich_text"):
            lab.patch(text, {"body_html": "<p>متن کوتاه</p>", "design": {"min_height": 200, "valign": "center", "align": "center"},
                             "background": {"mode": "color", "color": "#FCE588"}})

    elif name == "lab_hero_panels":
        # Zhimunplus: text + CTA column with four gradient panels under it, the mascot picture on the other side.
        row = lab.container("third_right", [["rich_text", "multi_banner"], ["linked_image"]], spans=(7, 5), gap=24, vertical_align="center")
        title = lab.blocks(row, "rich_text")[0]
        lab.patch(title, {"body_html": "<h2>عنوان بزرگ بخش</h2><p>توضیح کوتاه زیر عنوان</p>", "design": {"align": "start"}})
        panels = lab.blocks(row, "multi_banner")[0]
        lab.patch(panels, {"layout_variant": "panel-4", "item_limit": 4, "design": {"gap": 12, "mobile_layout": "slider2"}})
        photo = lab.blocks(row, "linked_image")[0]
        lab.patch(photo, {"design": {"image_fit": "contain", "valign": "center"}})
        attach(photo)

    elif name == "lab_advisors":
        # AsalBanoo consultants: four portrait cards on a desktop, ONE swipeable card at a time on a phone.
        lab.section("multi_banner", layout_variant="people-4", item_limit=4,
                    design={"image_ratio": "portrait", "gap": 14, "mobile_layout": "slider"})
        lab.section("multi_banner", layout_variant="trio-round", item_limit=3, design={"image_ratio": "panel", "mobile_layout": "stack"})

    elif name == "lab_seventh":
        # A seventh, invented layout: left rail + big slider, three portrait photos, a 6-column strip of tiles, footer re-arranged.
        rail = lab.container("quarter_left", [["rich_text"], ["hero_banner"]], spans=(3, 9), gap=16, mobile_order="reverse")
        lab.patch(lab.blocks(rail, "rich_text")[0], {"body_html": "<h3>ویژه</h3><p>فهرست کوتاه</p>",
                                                       "design": {"min_height": 320, "valign": "center"},
                                                       "background": {"mode": "color", "color": "#E8E1FF"}})
        lab.patch(lab.blocks(rail, "hero_banner")[0], {"hero_style": "split_open", "image_side": "start", "split_ratio": "image_wide"})
        photos = lab.container("thirds", [["linked_image"], ["linked_image"], ["linked_image"]], gap=14, mobile_mode="slider")
        for photo in lab.blocks(photos):
            lab.patch(photo, {"design": {"image_ratio": "portrait", "radius": 18}})
            attach(photo)
        lab.section("multi_banner", layout_variant="mini-4", item_limit=6,
                    design={"image_ratio": "square", "gap": 8, "radius": 14, "mobile_layout": "slider2"})
        lab.footer(footer_variant="marketplace_dense",
                   geometry={"order_contact": 1, "order_about": 4, "column_count": 3, "column_gap": 40, "pad_y": 56, "text_size": 15})
    elif name == "lab_pdp":
        # Product page: gallery on the far side and wider info column, price/trust first, the buy panel as an outlined card.
        main = StorefrontSection.objects.filter(page__version=lab.draft, page__page_type="product_detail", section_key="product_main").first()
        lab.patch(main, {"gallery_position": "end", "gallery_split": "info_wide", "thumbs_position": "side", "gallery_frame": "flush",
                         "info_panel": "outlined_tone",
                         "info_order": [{"key": k} for k in ("price", "trust", "options", "actions", "specs")]})
    else:
        raise ValueError(name)
    if publish:
        lab.publish()
    return lab
