"""V5 Groups — what the SAME renderer shows for a nested composition: the Draft preview, the published page, Undo / Redo, the per-Group look,
and the guarantee that an ordinary row keeps its exact markup."""

import re

from apps.storefront_builder.models import StorefrontCell, StorefrontContainer

from .test_v5_groups_service import _GroupBase


class GroupRenderTests(_GroupBase):
    def build_nested(self):
        row = self.row()
        self.mutate({"type": "cell.split", "cell_id": self.cells(row)[0].pk, "axis": "horizontal", "count": 2})
        left = self.cells(row)[0]
        self.put(left, "rich_text")
        self.mutate({"type": "cell.split", "cell_id": left.pk, "axis": "vertical", "count": 2})
        return row, self.nested(left)

    def test_a_nested_group_renders_as_a_group_inside_its_parent_cell_in_preview_and_published(self):
        row, group = self.build_nested()
        html = self.home_preview()
        self.assertIn(f'data-container-id="{group.pk}"', html)
        self.assertIn('data-axis="vertical"', html)
        self.assertEqual(len(re.findall(r'--cell-span:6', html[html.index('rcontainer--nested'):])) >= 2, True)
        # the nested rcontainer sits INSIDE a cell of the parent row
        self.assertRegex(html, rf'(?s)data-cell-id="{self.cells(row)[0].pk}"[^>]*>(?:(?!data-cell-id=).)*?rcontainer--nested')
        self.publish_and_probe(lambda page: "rcontainer--nested" in page and 'data-axis="vertical"' in page)

    def test_group_presentation_is_rendered_on_a_frame_and_survives_undo_redo(self):
        row, group = self.build_nested()
        self.mutate({"type": "container.update_settings", "container_id": group.pk, "patch": {
            "title": "پیشنهاد ویژه", "description": "فقط این هفته", "style": {"radius": 20, "pad": 24, "text_align": "center"},
            "background_mode": "gradient", "background_color": "#112233", "background_color2": "#445566",
        }})
        html = self.home_preview()
        self.assertIn('class="rgroup-title">پیشنهاد ویژه</h2>', html)
        self.assertIn("فقط این هفته", html)
        self.assertRegex(html, r'data-g="[^"]*radius[^"]*"')
        self.assertIn("linear-gradient(135deg", html)
        self.undo_redo_round_trip(lambda page: "پیشنهاد ویژه" in page)

    def test_title_can_be_hidden_without_losing_it(self):
        row, group = self.build_nested()
        self.mutate({"type": "container.update_settings", "container_id": group.pk, "patch": {"title": "پنهان", "title_visible": False}})
        self.assertNotIn("rgroup-title", self.home_preview())
        group.refresh_from_db()
        self.assertEqual(group.settings.get("title"), "پنهان")

    def test_per_device_hide_is_dimmed_in_the_builder_but_hidden_when_published(self):
        row, group = self.build_nested()
        self.mutate({"type": "container.update_settings", "container_id": group.pk, "patch": {"style": {"hide_mobile": "hidden"}}})
        self.assertRegex(self.home_preview(), r'class="rgroup sfb-builder-group[^"]*"[^>]*data-hide-m="1"')
        self.publish_and_probe(lambda page: 'data-hide-m="1"' in page)

    def test_an_ordinary_row_has_no_group_frame_and_no_group_markup(self):
        row = self.build_container("thirds", [["rich_text"], ["rich_text"], ["rich_text"]])
        html = self.home_preview()
        markup = re.sub(r"<style.*?</style>|<script.*?</script>", "", html, flags=re.S)
        self.assertNotIn('class="rgroup', markup)
        self.assertNotIn("rcontainer--nested", markup)
        self.assertNotIn('data-axis="vertical"', markup)
        self.assertIn(f'data-container-id="{row.pk}"', markup)

    def test_the_container_fragment_of_a_nested_group_is_its_top_level_row(self):
        row, group = self.build_nested()
        from django.test import RequestFactory

        from apps.storefront_builder import views

        request = RequestFactory().get("/")
        request.user = self.staff
        request.store = self.store
        request.session = self.client.session
        fragment = views.render_preview_fragment(request, self.store, self.draft, container_id=group.pk)
        self.assertIsNotNone(fragment)
        self.assertEqual((fragment["kind"], fragment["id"]), ("container", row.pk))
        self.assertIn("rcontainer--nested", fragment["html"])


class LayoutTreeEndpointTests(_GroupBase):
    def test_the_tree_endpoint_mirrors_the_nested_structure_and_is_store_scoped(self):
        from django.urls import reverse

        row = self.row()
        self.mutate({"type": "cell.split", "cell_id": self.cells(row)[0].pk, "axis": "horizontal", "count": 2})
        left = self.cells(row)[0]
        self.put(left, "rich_text")
        self.mutate({"type": "cell.split", "cell_id": left.pk, "axis": "vertical", "count": 3})
        response = self.client.get(reverse("dashboard:storefront-builder-r4-layout-tree") + "?page=home")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        node = next(r for r in data["tree"] if r["id"] == row.pk)
        self.assertEqual([c["span"] for c in node["cells"]], [6, 6])
        group = node["cells"][0]["group"]
        self.assertEqual((group["axis"], [c["span"] for c in group["cells"]], group["depth"]), ("vertical", [4, 4, 4], 1))
        self.assertEqual(group["cells"][0]["blocks"][0]["key"], "rich_text")
        self.assertEqual(data["revision"], self._revision())
        self.assertEqual(self.client.get(reverse("dashboard:storefront-builder-r4-layout-tree") + "?page=nope").status_code, 400)
        self.client.logout()
        self.assertNotEqual(self.client.get(reverse("dashboard:storefront-builder-r4-layout-tree") + "?page=home").status_code, 200)


class WidthBucketTests(_GroupBase):
    def test_cells_of_a_group_carry_a_width_bucket_and_ordinary_rows_do_not(self):
        ordinary = self.build_container("thirds", [["rich_text"], ["rich_text"], ["rich_text"]])
        row = self.row()
        self.mutate({"type": "cell.split", "cell_id": self.cells(row)[0].pk, "axis": "horizontal", "count": 3})     # 4 / 12 each -> «۲»
        first = self.cells(row)[0]
        self.mutate({"type": "cell.split", "cell_id": first.pk, "axis": "horizontal", "count": 2})                  # 6/12 of 4/12 -> «۱»
        html = self.home_preview()
        self.assertEqual(len(re.findall(r'data-cw="2"', html)), 3)       # the three columns (the first one hosts the nested Group)
        self.assertEqual(len(re.findall(r'data-cw="1"', html)), 2)
        self.assertEqual(html.count("data-cw="), 5, "only the Group's cells carry a bucket; the three cells of the ordinary row carry none")
        # the columns come from the shelf's own variable, capped only inside a Group cell and only on desktop
        css = open("apps/storefront_builder/static/css/storefront_builder.css", encoding="utf-8").read()
        self.assertIn('.rcontainer-cell[data-cw="2"] :is(.pcarousel, .grid).rsec-cols { --cols-desktop: 2; }', css)
        self.assertRegex(css, r"@media \(min-width: 1001px\) \{\s*\.rcontainer-cell\[data-cw=\"1\"\]")
