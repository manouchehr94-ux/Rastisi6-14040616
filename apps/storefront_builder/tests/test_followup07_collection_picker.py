"""FOLLOWUP-07 — the «از کالکشن» source tab is an accessible radio-card list (title / count / separate campaign link), explains
that the source is live, capped by the section's item limit and saved to the draft only; empty/zero-visible states are explicit.
Persistence (pick -> stored reference -> reload) and the no-auto-publish rule are exercised here and, in a real browser
at 1440/390 with keyboard selection, in the follow-up evidence."""

from pathlib import Path

from django.urls import reverse

from apps.catalog.services import collection_service

from .test_rs01_collection_source import CollectionSourceBase

JS = (Path(__file__).resolve().parents[1] / "static/storefront_builder/r4_editor.js").read_text(encoding="utf-8")


class CollectionPickerMarkupTests(CollectionSourceBase):
    def _panel(self):
        html = self.client.get(self._picker_url(kind="product")).content.decode()
        start = html.index('data-r4-picker-panel="collection"')
        return html[start:html.index("</section>", start)]

    def test_radio_group_with_one_card_per_collection_and_a_separate_campaign_link(self):
        panel = self._panel()
        self.assertIn('role="radiogroup"', panel)
        self.assertEqual(panel.count('role="radio"'), 1)
        card = panel[panel.index('class="r4-coll-card"'):]
        card = card[:card.index("</div>")]
        self.assertIn('data-r4-picker-collection="%d"' % self.coll.pk, card)
        self.assertIn("3 کالای قابل نمایش", card)
        self.assertIn(reverse("dashboard:collection-campaign", args=[self.coll.pk]), card)
        self.assertIn('class="r4-coll-campaign"', card)
        self.assertNotIn("<a", card[:card.index('class="r4-coll-campaign"')].split("</button>")[0])   # the link is NOT inside the choice

    def test_notes_explain_live_source_item_limit_and_draft_only(self):
        panel = self._panel()
        self.assertIn("منبع زنده", panel)
        self.assertIn("تعداد نمایش", panel)
        self.assertIn("فقط در پیش‌نویس", panel)

    def test_zero_visible_collection_is_flagged_not_hidden(self):
        empty = self._make_collection(name="کالکشن خالی", slug="f07-empty")
        panel = self._panel()
        self.assertIn("کالکشن خالی", panel)
        self.assertIn("هیچ کالای قابل نمایشی ندارد", panel)
        self.assertIn("r4-coll-meta--empty", panel)

    def test_no_collections_shows_the_empty_state(self):
        from apps.catalog.models import MerchantCollection

        MerchantCollection.objects.filter(store=self.store).update(is_active=False)
        self.assertIn("هنوز کالکشن فعالی ساخته نشده است", self._panel())


class CollectionPickerScriptTests(CollectionSourceBase):
    def test_keyboard_radio_behaviour_and_aria_checked_are_wired(self):
        for needle in ("aria-checked", "'ArrowDown'", "'ArrowUp'", "'Home'", "'End'", "choices[next].focus()"):
            self.assertIn(needle, JS)


class CollectionPickerPersistenceTests(CollectionSourceBase):
    def test_pick_is_saved_in_the_draft_only_and_survives_a_fresh_read(self):
        published_before = self.layout.published_version_id
        resp = self._pick(self.coll.pk)
        self.assertEqual(resp.status_code, 200, resp.content)
        self.layout.refresh_from_db()
        self.assertEqual(self.layout.published_version_id, published_before)         # nothing was published
        self.product_section.refresh_from_db()
        self.assertEqual(self.product_section.settings["source_id"], self.coll.pk)
        draft_settings = type(self.product_section).objects.get(pk=self.product_section.pk).settings
        self.assertEqual((draft_settings["data_source"], draft_settings["source_id"]), ("collection", self.coll.pk))

    def test_respects_the_section_item_limit_and_live_membership(self):
        from apps.storefront_builder.services import section_data_service

        for i in range(3, 8):
            collection_service.add_product(self.coll, self._make_product(name=f"کالای {i}", slug=f"f07-p{i}", sku=f"F07-{i}"))
        shown = section_data_service.products_in_collection(self.store, self.coll, 4)
        self.assertEqual(len(shown), 4)                                                # capped by item_limit
        extra = self._make_product(name="تازه", slug="f07-new", sku="F07-NEW")
        collection_service.add_product(self.coll, extra)
        self.assertEqual(len(section_data_service.products_in_collection(self.store, self.coll, 50)), 9)   # live: new member is seen
