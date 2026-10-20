"""تست‌های مدیریت منوهای ناوبری — مدل، داشبورد، فروشگاه."""


from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db.models import ProtectedError
from django.test import TestCase
from django.urls import reverse

from django.utils import timezone

from apps.catalog.models import Category, Vendor
from apps.content.models import Menu, MenuItem
from apps.stores.models import Store, StoreMembership


def _grant_akhlaghi_membership(user):
    StoreMembership.objects.create(
        store=Store.objects.get(slug="akhlaghi"), user=user,
        role=StoreMembership.Role.OWNER, status=StoreMembership.MembershipStatus.ACTIVE,
        accepted_at=timezone.now(),
    )

User = get_user_model()


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


# ============================================================ MENU MODEL TESTS


class MenuModelTests(TestCase):
    def test_valid_creation(self):
        menu = Menu.objects.create(store=_akhlaghi(), title="منوی اصلی", location="header")
        self.assertTrue(menu.pk)

    def test_unique_location(self):
        Menu.objects.create(store=_akhlaghi(), title="M1", location="header")
        with self.assertRaises(IntegrityError):
            Menu.objects.create(store=_akhlaghi(), title="M2", location="header")

    def test_required_title(self):
        menu = Menu(title="", location="footer_1")
        with self.assertRaises(ValidationError):
            menu.full_clean()

    def test_active_default(self):
        menu = Menu.objects.create(store=_akhlaghi(), title="T", location="mobile")
        self.assertTrue(menu.is_active)

    def test_ordering_by_location(self):
        Menu.objects.create(store=_akhlaghi(), title="Footer", location="footer_1")
        Menu.objects.create(store=_akhlaghi(), title="Header", location="header")
        locations = list(Menu.objects.values_list("location", flat=True))
        self.assertEqual(locations[0], "footer_1")  # f < h alphabetically

    def test_persian_labels(self):
        menu = Menu(title="T", location="header")
        self.assertEqual(menu.get_location_display(), "منوی اصلی")

    def test_str_representation(self):
        menu = Menu(title="فوتر ۱", location="footer_1")
        self.assertIn("فوتر ۱", str(menu))


# ============================================================ MENU ITEM MODEL TESTS


class MenuItemModelTests(TestCase):
    def setUp(self):
        self.menu = Menu.objects.create(store=_akhlaghi(), title="Header", location="header")
        self.vendor = Vendor.objects.create(store=_akhlaghi(), name="V", slug="v-nav")
        self.category = Category.objects.create(store=_akhlaghi(), name="Cat", slug="cat-nav")

    def test_valid_top_level_item(self):
        item = MenuItem.objects.create(
            menu=self.menu, title="Home",
            destination_type="category", destination_category=self.category,
        )
        self.assertTrue(item.pk)
        self.assertIsNone(item.parent)

    def test_valid_child_item(self):
        parent = MenuItem.objects.create(
            menu=self.menu, title="Parent",
            destination_type="category", destination_category=self.category,
        )
        child = MenuItem.objects.create(
            menu=self.menu, title="Child", parent=parent,
            destination_type="external", destination_external_url="https://example.com",
        )
        self.assertEqual(child.parent, parent)

    def test_same_menu_parent_required(self):
        other_menu = Menu.objects.create(store=_akhlaghi(), title="Other", location="footer_1")
        parent = MenuItem.objects.create(
            menu=other_menu, title="Other Parent",
            destination_type="none",
        )
        item = MenuItem(
            menu=self.menu, title="Child", parent=parent,
            destination_type="none",
        )
        with self.assertRaises(ValidationError) as ctx:
            item.full_clean()
        self.assertIn("parent", ctx.exception.message_dict)

    def test_self_parent_rejected(self):
        item = MenuItem.objects.create(
            menu=self.menu, title="Self",
            destination_type="none",
        )
        item.parent = item
        with self.assertRaises(ValidationError) as ctx:
            item.full_clean()
        self.assertIn("parent", ctx.exception.message_dict)

    def test_grandchild_rejected(self):
        parent = MenuItem.objects.create(
            menu=self.menu, title="P", destination_type="none",
        )
        child = MenuItem.objects.create(
            menu=self.menu, title="C", parent=parent, destination_type="none",
        )
        grandchild = MenuItem(
            menu=self.menu, title="GC", parent=child, destination_type="none",
        )
        with self.assertRaises(ValidationError) as ctx:
            grandchild.full_clean()
        self.assertIn("parent", ctx.exception.message_dict)

    def test_item_with_children_cannot_become_child(self):
        parent = MenuItem.objects.create(
            menu=self.menu, title="P", destination_type="none",
        )
        MenuItem.objects.create(
            menu=self.menu, title="C", parent=parent, destination_type="none",
        )
        other_top = MenuItem.objects.create(
            menu=self.menu, title="OT", destination_type="none",
        )
        parent.parent = other_top
        with self.assertRaises(ValidationError) as ctx:
            parent.full_clean()
        self.assertIn("parent", ctx.exception.message_dict)

    def test_required_title(self):
        item = MenuItem(menu=self.menu, title="", destination_type="none")
        with self.assertRaises(ValidationError):
            item.full_clean()

    def test_stable_ordering(self):
        MenuItem.objects.create(menu=self.menu, title="B", destination_type="none", display_order=2)
        MenuItem.objects.create(menu=self.menu, title="A", destination_type="none", display_order=1)
        titles = list(MenuItem.objects.values_list("title", flat=True))
        self.assertEqual(titles, ["A", "B"])

    def test_destination_validation_reused(self):
        """DestinationMixin validation fires — category required when type=category."""
        item = MenuItem(
            menu=self.menu, title="X", destination_type="category",
        )
        with self.assertRaises(ValidationError):
            item.full_clean()

    def test_external_url_security(self):
        item = MenuItem(
            menu=self.menu, title="X",
            destination_type="external",
            destination_external_url="javascript:alert(1)",
        )
        with self.assertRaises(ValidationError):
            item.full_clean()

    def test_open_in_new_tab(self):
        item = MenuItem.objects.create(
            menu=self.menu, title="Ext",
            destination_type="external",
            destination_external_url="https://example.com",
            open_in_new_tab=True,
        )
        self.assertTrue(item.open_in_new_tab)

    def test_parent_protection_on_delete(self):
        parent = MenuItem.objects.create(
            menu=self.menu, title="P", destination_type="none",
        )
        MenuItem.objects.create(
            menu=self.menu, title="C", parent=parent, destination_type="none",
        )
        with self.assertRaises(ProtectedError):
            parent.delete()


# ============================================================ DASHBOARD ACCESS TESTS


class MenuDashboardAccessTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(username="staff_nav", password="p!", is_staff=True)
        _grant_akhlaghi_membership(self.staff)
        self.non_staff = User.objects.create_user(username="user_nav", password="p!", is_staff=False)

    def test_anonymous_redirected(self):
        response = self.client.get(reverse("dashboard:menu-list"))
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("/admin-portal/login/", response.url)
        self.assertIn("admin_return=", response.url)

    def test_non_staff_rejected(self):
        self.client.login(username="user_nav", password="p!")
        response = self.client.get(reverse("dashboard:menu-list"))
        self.assertEqual(response.status_code, 302)

    def test_staff_allowed(self):
        self.client.login(username="staff_nav", password="p!")
        response = self.client.get(reverse("dashboard:menu-list"))
        self.assertEqual(response.status_code, 200)

    def test_menu_create_accessible(self):
        self.client.login(username="staff_nav", password="p!")
        response = self.client.get(reverse("dashboard:menu-add"))
        self.assertEqual(response.status_code, 200)

    def test_menu_edit_accessible(self):
        self.client.login(username="staff_nav", password="p!")
        menu = Menu.objects.create(store=_akhlaghi(), title="T", location="header")
        response = self.client.get(reverse("dashboard:menu-edit", args=[menu.pk]))
        self.assertEqual(response.status_code, 200)

    def test_item_management_accessible(self):
        self.client.login(username="staff_nav", password="p!")
        menu = Menu.objects.create(store=_akhlaghi(), title="T", location="header")
        response = self.client.get(reverse("dashboard:menu-item-list", args=[menu.pk]))
        self.assertEqual(response.status_code, 200)

    def test_delete_requires_post(self):
        self.client.login(username="staff_nav", password="p!")
        menu = Menu.objects.create(store=_akhlaghi(), title="T", location="header")
        response = self.client.get(reverse("dashboard:menu-delete", args=[menu.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Menu.objects.filter(pk=menu.pk).exists())

    def test_toggle_requires_post(self):
        self.client.login(username="staff_nav", password="p!")
        menu = Menu.objects.create(store=_akhlaghi(), title="T", location="header")
        response = self.client.get(reverse("dashboard:menu-toggle", args=[menu.pk]))
        self.assertEqual(response.status_code, 405)

    def test_item_delete_requires_post(self):
        self.client.login(username="staff_nav", password="p!")
        menu = Menu.objects.create(store=_akhlaghi(), title="T", location="header")
        item = MenuItem.objects.create(menu=menu, title="I", destination_type="none")
        response = self.client.get(reverse("dashboard:menu-item-delete", args=[item.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(MenuItem.objects.filter(pk=item.pk).exists())

    def test_item_toggle_requires_post(self):
        self.client.login(username="staff_nav", password="p!")
        menu = Menu.objects.create(store=_akhlaghi(), title="T", location="header")
        item = MenuItem.objects.create(menu=menu, title="I", destination_type="none")
        response = self.client.get(reverse("dashboard:menu-item-toggle", args=[item.pk]))
        self.assertEqual(response.status_code, 405)


# ============================================================ DASHBOARD CRUD TESTS


class MenuDashboardCRUDTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(username="staff_mc", password="p!", is_staff=True)
        _grant_akhlaghi_membership(self.staff)
        self.client.login(username="staff_mc", password="p!")

    def test_create_menu(self):
        response = self.client.post(reverse("dashboard:menu-add"), {
            "title": "منوی هدر", "location": "header", "is_active": "on",
        })
        menu = Menu.objects.get(title="منوی هدر")
        self.assertRedirects(response, reverse("dashboard:menu-item-list", args=[menu.pk]))
        self.assertTrue(Menu.objects.filter(title="منوی هدر").exists())

    def test_edit_menu(self):
        menu = Menu.objects.create(store=_akhlaghi(), title="Old", location="footer_1")
        self.client.post(reverse("dashboard:menu-edit", args=[menu.pk]), {
            "title": "New Title", "location": "footer_1", "is_active": "on",
        })
        menu.refresh_from_db()
        self.assertEqual(menu.title, "New Title")

    def test_delete_empty_menu(self):
        menu = Menu.objects.create(store=_akhlaghi(), title="Empty", location="footer_2")
        self.client.post(reverse("dashboard:menu-delete", args=[menu.pk]))
        self.assertFalse(Menu.objects.filter(pk=menu.pk).exists())

    def test_prevent_deleting_populated_menu(self):
        menu = Menu.objects.create(store=_akhlaghi(), title="Full", location="footer_3")
        MenuItem.objects.create(menu=menu, title="I", destination_type="none")
        self.client.post(reverse("dashboard:menu-delete", args=[menu.pk]))
        self.assertTrue(Menu.objects.filter(pk=menu.pk).exists())

    def test_toggle_menu(self):
        menu = Menu.objects.create(store=_akhlaghi(), title="T", location="header", is_active=True)
        self.client.post(reverse("dashboard:menu-toggle", args=[menu.pk]))
        menu.refresh_from_db()
        self.assertFalse(menu.is_active)

    def test_create_item(self):
        menu = Menu.objects.create(store=_akhlaghi(), title="M", location="header")
        cat = Category.objects.create(store=_akhlaghi(), name="C", slug="c-nav-crud")
        response = self.client.post(reverse("dashboard:menu-item-add", args=[menu.pk]), {
            "title": "New Item", "display_order": "0", "is_active": "on",
            "destination_type": "category", "destination_category": str(cat.pk),
            "destination_external_url": "", "destination_product": "", "destination_brand": "",
        })
        self.assertRedirects(response, reverse("dashboard:menu-item-list", args=[menu.pk]))
        self.assertTrue(MenuItem.objects.filter(title="New Item").exists())

    def test_edit_item(self):
        menu = Menu.objects.create(store=_akhlaghi(), title="M", location="header")
        cat = Category.objects.create(store=_akhlaghi(), name="EC", slug="ec-edit")
        item = MenuItem.objects.create(
            menu=menu, title="Old", destination_type="category",
            destination_category=cat,
        )
        self.client.post(reverse("dashboard:menu-item-edit", args=[item.pk]), {
            "title": "Updated", "display_order": "5", "is_active": "on",
            "destination_type": "category", "destination_category": str(cat.pk),
            "destination_external_url": "",
            "destination_product": "", "destination_brand": "",
            "parent": "",
        })
        item.refresh_from_db()
        self.assertEqual(item.title, "Updated")
        self.assertEqual(item.display_order, 5)

    def test_delete_leaf_item(self):
        menu = Menu.objects.create(store=_akhlaghi(), title="M", location="header")
        item = MenuItem.objects.create(menu=menu, title="Leaf", destination_type="none")
        self.client.post(reverse("dashboard:menu-item-delete", args=[item.pk]))
        self.assertFalse(MenuItem.objects.filter(pk=item.pk).exists())

    def test_prevent_deleting_parent_with_children(self):
        menu = Menu.objects.create(store=_akhlaghi(), title="M", location="header")
        parent = MenuItem.objects.create(menu=menu, title="P", destination_type="none")
        MenuItem.objects.create(menu=menu, title="C", parent=parent, destination_type="none")
        self.client.post(reverse("dashboard:menu-item-delete", args=[parent.pk]))
        # Parent should still exist
        self.assertTrue(MenuItem.objects.filter(pk=parent.pk).exists())

    def test_toggle_item(self):
        menu = Menu.objects.create(store=_akhlaghi(), title="M", location="header")
        item = MenuItem.objects.create(menu=menu, title="I", destination_type="none", is_active=True)
        self.client.post(reverse("dashboard:menu-item-toggle", args=[item.pk]))
        item.refresh_from_db()
        self.assertFalse(item.is_active)

    def test_invalid_parent_rejected(self):
        menu = Menu.objects.create(store=_akhlaghi(), title="M", location="header")
        other_menu = Menu.objects.create(store=_akhlaghi(), title="O", location="footer_1")
        other_parent = MenuItem.objects.create(menu=other_menu, title="OP", destination_type="none")
        response = self.client.post(reverse("dashboard:menu-item-add", args=[menu.pk]), {
            "title": "Bad", "display_order": "0", "is_active": "on",
            "destination_type": "none", "destination_external_url": "",
            "destination_category": "", "destination_product": "", "destination_brand": "",
            "parent": str(other_parent.pk),
        })
        # Should not create — stays on form with error
        self.assertFalse(MenuItem.objects.filter(title="Bad").exists())

    def test_invalid_destination_rejected(self):
        menu = Menu.objects.create(store=_akhlaghi(), title="M", location="header")
        response = self.client.post(reverse("dashboard:menu-item-add", args=[menu.pk]), {
            "title": "Bad", "display_order": "0", "is_active": "on",
            "destination_type": "external",
            "destination_external_url": "javascript:alert(1)",
            "destination_category": "", "destination_product": "", "destination_brand": "",
        })
        self.assertFalse(MenuItem.objects.filter(title="Bad").exists())

    def test_duplicate_location_rejected(self):
        Menu.objects.create(store=_akhlaghi(), title="M1", location="header")
        response = self.client.post(reverse("dashboard:menu-add"), {
            "title": "M2", "location": "header", "is_active": "on",
        })
        # Should stay on form with error — only 1 header menu
        self.assertEqual(Menu.objects.filter(location="header").count(), 1)


# ============================================================ STOREFRONT TESTS


class NavigationStorefrontTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(store=_akhlaghi(), name="Electronics", slug="electronics-nav")

    def test_header_menu_renders(self):
        menu = Menu.objects.create(store=_akhlaghi(), title="Header", location="header", is_active=True)
        MenuItem.objects.create(
            menu=menu, title="فروشگاه",
            destination_type="category", destination_category=self.category,
            is_active=True, display_order=0,
        )
        response = self.client.get("/")
        self.assertContains(response, "فروشگاه")
        self.assertContains(response, "category=electronics-nav")

    def test_footer_menu_renders(self):
        menu = Menu.objects.create(store=_akhlaghi(), title="Quick", location="footer_1", is_active=True)
        MenuItem.objects.create(
            menu=menu, title="درباره ما",
            destination_type="external",
            destination_external_url="https://example.com/about",
            is_active=True,
        )
        response = self.client.get("/")
        self.assertContains(response, "درباره ما")
        self.assertContains(response, "https://example.com/about")

    def test_inactive_menu_hidden(self):
        menu = Menu.objects.create(store=_akhlaghi(), title="Hidden", location="header", is_active=False)
        MenuItem.objects.create(
            menu=menu, title="ShouldNotShow",
            destination_type="external",
            destination_external_url="https://hidden.com",
            is_active=True,
        )
        response = self.client.get("/")
        self.assertNotContains(response, "ShouldNotShow")

    def test_inactive_item_hidden(self):
        menu = Menu.objects.create(store=_akhlaghi(), title="H", location="header", is_active=True)
        MenuItem.objects.create(
            menu=menu, title="ActiveItem",
            destination_type="category", destination_category=self.category,
            is_active=True,
        )
        MenuItem.objects.create(
            menu=menu, title="InactiveItem",
            destination_type="external",
            destination_external_url="https://hidden.com",
            is_active=False,
        )
        response = self.client.get("/")
        self.assertContains(response, "ActiveItem")
        self.assertNotContains(response, "InactiveItem")

    def test_inactive_parent_hides_child(self):
        menu = Menu.objects.create(store=_akhlaghi(), title="H", location="header", is_active=True)
        parent = MenuItem.objects.create(
            menu=menu, title="Parent",
            destination_type="category", destination_category=self.category,
            is_active=False,
        )
        MenuItem.objects.create(
            menu=menu, title="ChildOfInactive", parent=parent,
            destination_type="external",
            destination_external_url="https://child.com",
            is_active=True,
        )
        response = self.client.get("/")
        self.assertNotContains(response, "ChildOfInactive")

    def test_top_level_ordering(self):
        menu = Menu.objects.create(store=_akhlaghi(), title="H", location="header", is_active=True)
        MenuItem.objects.create(
            menu=menu, title="Second",
            destination_type="external", destination_external_url="https://b.com",
            is_active=True, display_order=2,
        )
        MenuItem.objects.create(
            menu=menu, title="First",
            destination_type="external", destination_external_url="https://a.com",
            is_active=True, display_order=1,
        )
        response = self.client.get("/")
        content = response.content.decode()
        self.assertLess(content.find("First"), content.find("Second"))

    def test_external_target_rel_safe(self):
        menu = Menu.objects.create(store=_akhlaghi(), title="H", location="header", is_active=True)
        MenuItem.objects.create(
            menu=menu, title="Ext",
            destination_type="external",
            destination_external_url="https://example.com",
            open_in_new_tab=True, is_active=True,
        )
        response = self.client.get("/")
        self.assertContains(response, 'target="_blank"')
        self.assertContains(response, 'rel="noopener noreferrer"')

    def test_internal_no_new_tab(self):
        menu = Menu.objects.create(store=_akhlaghi(), title="H", location="header", is_active=True)
        MenuItem.objects.create(
            menu=menu, title="Internal",
            destination_type="category", destination_category=self.category,
            open_in_new_tab=False, is_active=True,
        )
        response = self.client.get("/")
        # Should NOT have target="_blank" for this internal link
        content = response.content.decode()
        idx = content.find("Internal")
        # Get the link around it
        link_start = content.rfind("<a", 0, idx)
        link_end = content.find(">", idx)
        link_tag = content[link_start:link_end]
        self.assertNotIn('target="_blank"', link_tag)

    def test_escaped_item_title(self):
        menu = Menu.objects.create(store=_akhlaghi(), title="H", location="header", is_active=True)
        MenuItem.objects.create(
            menu=menu, title='<script>xss</script>',
            destination_type="external",
            destination_external_url="https://example.com",
            is_active=True,
        )
        response = self.client.get("/")
        self.assertNotContains(response, '<script>xss</script>')
        self.assertContains(response, "&lt;script&gt;")

    def test_empty_header_no_managed_links(self):
        """No header menu → no nav links in nav-links-scroll (no hardcoded fallback)."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        # The nav-links-scroll should not contain any <a class="nl" links
        import re
        nav_match = re.search(r'<div class="nav-links-scroll">(.*?)</div>', content, re.DOTALL)
        if nav_match:
            inner = nav_match.group(1)
            self.assertNotIn('class="nl"', inner)

    def test_no_hardcoded_when_managed_header(self):
        """When managed header exists, no fallback links appear."""
        menu = Menu.objects.create(store=_akhlaghi(), title="H", location="header", is_active=True)
        MenuItem.objects.create(
            menu=menu, title="ManagedLink",
            destination_type="external",
            destination_external_url="https://managed.com",
            is_active=True,
        )
        response = self.client.get("/")
        self.assertContains(response, "ManagedLink")
        content = response.content.decode()
        # Should not have the old hardcoded "برندها" link in nav area
        import re
        nav_match = re.search(r'<div class="nav-links-scroll">(.*?)</div>', content, re.DOTALL)
        if nav_match:
            self.assertNotIn("برندها", nav_match.group(1))

    def test_invalid_destination_does_not_crash(self):
        """Item with deleted category → skipped, page doesn't crash."""
        menu = Menu.objects.create(store=_akhlaghi(), title="H", location="header", is_active=True)
        MenuItem.objects.create(
            menu=menu, title="Stale",
            destination_type="category",
            destination_category=None,  # Simulates SET_NULL
            is_active=True,
        )
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Stale")

    def test_footer_locations_independent(self):
        """Footer menus render independently."""
        menu1 = Menu.objects.create(store=_akhlaghi(), title="F1", location="footer_1", is_active=True)
        menu2 = Menu.objects.create(store=_akhlaghi(), title="F2", location="footer_2", is_active=True)
        cat = self.category
        MenuItem.objects.create(menu=menu1, title="Link1", destination_type="category", destination_category=cat, is_active=True)
        MenuItem.objects.create(menu=menu2, title="Link2", destination_type="external", destination_external_url="https://f2.com", is_active=True)
        response = self.client.get("/")
        self.assertContains(response, "Link1")
        self.assertContains(response, "Link2")
        self.assertContains(response, "F1")
        self.assertContains(response, "F2")




# ============================================================ FALLBACK REMOVAL TESTS


class NavigationFallbackRemovalTests(TestCase):
    """تست‌های حذف fallback — مدیر کنترل کامل دارد."""

    def test_inactive_header_menu_no_fallback(self):
        """Inactive header menu → no nav links at all."""
        menu = Menu.objects.create(store=_akhlaghi(), title="H", location="header", is_active=False)
        MenuItem.objects.create(
            menu=menu, title="Should Not Show",
            destination_type="external", destination_external_url="https://x.com",
            is_active=True,
        )
        response = self.client.get("/")
        self.assertNotContains(response, "Should Not Show")
        content = response.content.decode()
        import re
        nav_match = re.search(r'<div class="nav-links-scroll">(.*?)</div>', content, re.DOTALL)
        if nav_match:
            self.assertNotIn('class="nl"', nav_match.group(1))

    def test_empty_active_header_no_wrapper(self):
        """Active header menu with no items → no nav links rendered."""
        Menu.objects.create(store=_akhlaghi(), title="Empty", location="header", is_active=True)
        response = self.client.get("/")
        content = response.content.decode()
        import re
        nav_match = re.search(r'<div class="nav-links-scroll">(.*?)</div>', content, re.DOTALL)
        if nav_match:
            self.assertNotIn('class="nl"', nav_match.group(1))

    def test_no_footer_menu_no_column(self):
        """No footer_1 menu → no column rendered for that location."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        # No "دسترسی سریع" default heading should appear (removed)
        self.assertNotContains(response, "دسترسی سریع")

    def test_inactive_footer_menu_no_column(self):
        """Inactive footer menu → column not rendered."""
        menu = Menu.objects.create(store=_akhlaghi(), title="F1", location="footer_1", is_active=False)
        MenuItem.objects.create(
            menu=menu, title="Hidden",
            destination_type="external", destination_external_url="https://x.com",
            is_active=True,
        )
        response = self.client.get("/")
        self.assertNotContains(response, "Hidden")

    def test_footer_menu_only_inactive_items_no_column(self):
        """Footer menu with only inactive/unresolvable items → column not rendered."""
        cat = Category.objects.create(store=_akhlaghi(), name="FC", slug="fc-fr")
        menu = Menu.objects.create(store=_akhlaghi(), title="F1", location="footer_1", is_active=True)
        MenuItem.objects.create(
            menu=menu, title="Inactive",
            destination_type="category", destination_category=cat,
            is_active=False,
        )
        response = self.client.get("/")
        # The column heading should not render since no renderable items
        # exist. Scoped to the actual <h5> heading markup (not a bare "F1"
        # substring search) — a bare substring can coincidentally match
        # inside an unrelated random token (e.g. the CSRF token) anywhere
        # else on the page.
        self.assertNotContains(response, "<h5>F1</h5>")

    def test_other_non_navigation_content_remains(self):
        """Non-navigation elements (newsletter, branding) remain."""
        from apps.content.models import FooterSettings
        fs = FooterSettings.load()
        fs.show_newsletter = True
        fs.show_contact = True
        fs.phone = "021-12345"
        fs.save()
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "عضویت در خبرنامه")
        self.assertContains(response, "ارتباط با ما")


# ============================================================ DESTINATION POLICY TESTS


class DestinationPolicyTests(TestCase):
    """تست‌های سیاست مقصد آیتم‌های منو."""

    def setUp(self):
        self.menu = Menu.objects.create(store=_akhlaghi(), title="T", location="header")
        self.category = Category.objects.create(store=_akhlaghi(), name="DC", slug="dc-dp")

    def test_leaf_with_no_destination_allowed_as_provisional(self):
        """Top-level item with destination=none → allowed (provisional parent, won't render)."""
        item = MenuItem(menu=self.menu, title="Provisional", destination_type="none")
        item.full_clean()  # Should NOT raise — provisional parent

    def test_child_with_no_destination_rejected(self):
        """Child item with destination=none → rejected."""
        parent = MenuItem.objects.create(
            menu=self.menu, title="P",
            destination_type="category", destination_category=self.category,
        )
        child = MenuItem(
            menu=self.menu, title="C", parent=parent, destination_type="none",
        )
        with self.assertRaises(ValidationError) as ctx:
            child.full_clean()
        self.assertIn("destination_type", ctx.exception.message_dict)

    def test_parent_without_destination_with_children_allowed(self):
        """Parent (with children) and destination=none → allowed."""
        parent = MenuItem.objects.create(
            menu=self.menu, title="Heading", destination_type="none",
        )
        # Add a child so parent has children
        MenuItem.objects.create(
            menu=self.menu, title="Child", parent=parent,
            destination_type="category", destination_category=self.category,
        )
        # Re-validate parent — should pass since it has children
        parent.refresh_from_db()
        parent.full_clean()  # Should not raise

    def test_provisional_parent_does_not_render(self):
        """Top-level with destination=none and no children → does not render."""
        menu = Menu.objects.create(store=_akhlaghi(), title="H", location="footer_2", is_active=True)
        MenuItem.objects.create(menu=menu, title="Provisional", destination_type="none", is_active=True)
        response = self.client.get("/")
        self.assertNotContains(response, "Provisional")

    def test_no_href_hash_in_storefront(self):
        """Storefront must never produce href='#' for menu items."""
        menu = Menu.objects.create(store=_akhlaghi(), title="H", location="footer_1", is_active=True)
        MenuItem.objects.create(
            menu=menu, title="Valid",
            destination_type="category", destination_category=self.category,
            is_active=True,
        )
        response = self.client.get("/")
        content = response.content.decode()
        import re
        footer_match = re.search(r'<h5>H</h5>(.*?)</ul>', content, re.DOTALL)
        if footer_match:
            self.assertNotIn('href="#"', footer_match.group(1))

    def test_non_clickable_parent_renders_as_span(self):
        """Parent with no URL renders as <span>, not <a href='#'>."""
        # Use a location that won't conflict with setUp's header menu
        hmenu = Menu.objects.create(store=_akhlaghi(), title="HH", location="footer_1", is_active=True)
        p = MenuItem.objects.create(menu=hmenu, title="HeadingItem", destination_type="none")
        MenuItem.objects.create(
            menu=hmenu, title="Sub", parent=p,
            destination_type="external", destination_external_url="https://sub.com",
            is_active=True,
        )
        response = self.client.get("/")
        content = response.content.decode()
        # HeadingItem has no URL so should not produce href="#"
        self.assertIn("HeadingItem", content)
        self.assertNotIn('href="#">HeadingItem', content)

    def test_exactly_one_destination_enforced(self):
        """Multiple destinations still rejected by DestinationMixin validation."""
        item = MenuItem(
            menu=self.menu, title="Multi",
            destination_type="category",
            destination_category=self.category,
            destination_external_url="https://x.com",
        )
        with self.assertRaises(ValidationError):
            item.full_clean()


# ============================================================ MENU DELETION PROTECTION TESTS


class MenuDeletionProtectionTests(TestCase):
    """تست‌های حفاظت حذف منو در سطح داده."""

    def setUp(self):
        self.staff = User.objects.create_user(username="staff_del", password="p!", is_staff=True)
        _grant_akhlaghi_membership(self.staff)
        self.client.login(username="staff_del", password="p!")

    def test_orm_deletion_of_populated_menu_raises_protected(self):
        """Direct ORM deletion of menu with items → ProtectedError."""
        menu = Menu.objects.create(store=_akhlaghi(), title="P", location="header")
        MenuItem.objects.create(menu=menu, title="I", destination_type="none")
        with self.assertRaises(ProtectedError):
            menu.delete()

    def test_dashboard_deletion_of_populated_menu_blocked(self):
        """Dashboard delete of populated menu → blocked with message."""
        menu = Menu.objects.create(store=_akhlaghi(), title="P", location="footer_1")
        MenuItem.objects.create(menu=menu, title="I", destination_type="none")
        self.client.post(reverse("dashboard:menu-delete", args=[menu.pk]))
        self.assertTrue(Menu.objects.filter(pk=menu.pk).exists())

    def test_empty_menu_deletion_succeeds(self):
        """Empty menu can be deleted."""
        menu = Menu.objects.create(store=_akhlaghi(), title="E", location="footer_2")
        self.client.post(reverse("dashboard:menu-delete", args=[menu.pk]))
        self.assertFalse(Menu.objects.filter(pk=menu.pk).exists())

    def test_items_remain_after_blocked_deletion(self):
        """Items remain intact after blocked menu deletion."""
        menu = Menu.objects.create(store=_akhlaghi(), title="P", location="footer_3")
        item = MenuItem.objects.create(menu=menu, title="I", destination_type="none")
        self.client.post(reverse("dashboard:menu-delete", args=[menu.pk]))
        self.assertTrue(MenuItem.objects.filter(pk=item.pk).exists())

    def test_no_silent_cascade(self):
        """PROTECT prevents cascade — items survive."""
        menu = Menu.objects.create(store=_akhlaghi(), title="P", location="mobile")
        item = MenuItem.objects.create(menu=menu, title="I", destination_type="none")
        try:
            menu.delete()
        except ProtectedError:
            pass
        self.assertTrue(MenuItem.objects.filter(pk=item.pk).exists())




# ============================================================ HIERARCHY RENDERING TESTS


class HeaderHierarchyRenderingTests(TestCase):
    """تست‌های رندر زیرمنوی هدر."""

    def setUp(self):
        self.category = Category.objects.create(store=_akhlaghi(), name="HCat", slug="hcat-hr")
        self.menu = Menu.objects.create(store=_akhlaghi(), title="Header", location="header", is_active=True)

    def test_parent_and_child_both_render(self):
        parent = MenuItem.objects.create(
            menu=self.menu, title="ParentItem",
            destination_type="category", destination_category=self.category,
            is_active=True,
        )
        MenuItem.objects.create(
            menu=self.menu, title="ChildItem", parent=parent,
            destination_type="external", destination_external_url="https://child.example.com",
            is_active=True,
        )
        response = self.client.get("/")
        self.assertContains(response, "ParentItem")
        self.assertContains(response, "ChildItem")
        self.assertContains(response, "https://child.example.com")

    def test_child_order_deterministic(self):
        parent = MenuItem.objects.create(
            menu=self.menu, title="P", destination_type="none", is_active=True,
        )
        MenuItem.objects.create(
            menu=self.menu, title="ChildB", parent=parent, display_order=2,
            destination_type="external", destination_external_url="https://b.com",
            is_active=True,
        )
        MenuItem.objects.create(
            menu=self.menu, title="ChildA", parent=parent, display_order=1,
            destination_type="external", destination_external_url="https://a.com",
            is_active=True,
        )
        response = self.client.get("/")
        content = response.content.decode()
        self.assertLess(content.find("ChildA"), content.find("ChildB"))

    def test_inactive_child_hidden(self):
        parent = MenuItem.objects.create(
            menu=self.menu, title="P", destination_type="none", is_active=True,
        )
        MenuItem.objects.create(
            menu=self.menu, title="ActiveChild", parent=parent,
            destination_type="external", destination_external_url="https://a.com",
            is_active=True,
        )
        MenuItem.objects.create(
            menu=self.menu, title="InactiveChild", parent=parent,
            destination_type="external", destination_external_url="https://b.com",
            is_active=False,
        )
        response = self.client.get("/")
        self.assertContains(response, "ActiveChild")
        self.assertNotContains(response, "InactiveChild")

    def test_inactive_parent_hides_children(self):
        parent = MenuItem.objects.create(
            menu=self.menu, title="InactiveP", destination_type="none", is_active=False,
        )
        MenuItem.objects.create(
            menu=self.menu, title="ChildOfInactive", parent=parent,
            destination_type="external", destination_external_url="https://c.com",
            is_active=True,
        )
        response = self.client.get("/")
        self.assertNotContains(response, "ChildOfInactive")

    def test_destinationless_parent_renders_as_button(self):
        """Parent with no URL renders button trigger, not <a href='#'>."""
        parent = MenuItem.objects.create(
            menu=self.menu, title="HeadingParent", destination_type="none", is_active=True,
        )
        MenuItem.objects.create(
            menu=self.menu, title="SubItem", parent=parent,
            destination_type="external", destination_external_url="https://sub.com",
            is_active=True,
        )
        response = self.client.get("/")
        content = response.content.decode()
        self.assertIn("HeadingParent", content)
        self.assertIn("nav-submenu-trigger", content)
        self.assertIn("aria-haspopup", content)
        self.assertNotIn('href="#">HeadingParent', content)

    def test_parent_with_destination_renders_as_link(self):
        """Parent with valid URL renders as clickable <a>."""
        parent = MenuItem.objects.create(
            menu=self.menu, title="ClickableP",
            destination_type="category", destination_category=self.category,
            is_active=True,
        )
        MenuItem.objects.create(
            menu=self.menu, title="SubChild", parent=parent,
            destination_type="external", destination_external_url="https://sub.com",
            is_active=True,
        )
        response = self.client.get("/")
        content = response.content.decode()
        self.assertIn("ClickableP", content)
        self.assertIn("category=hcat-hr", content)

    def test_no_href_hash(self):
        """No href='#' anywhere in managed header nav."""
        parent = MenuItem.objects.create(
            menu=self.menu, title="P", destination_type="none", is_active=True,
        )
        MenuItem.objects.create(
            menu=self.menu, title="C", parent=parent,
            destination_type="external", destination_external_url="https://x.com",
            is_active=True,
        )
        response = self.client.get("/")
        content = response.content.decode()
        import re
        nav_match = re.search(r'<div class="nav-links-scroll">(.*?)</div>\s*</div>\s*</nav>', content, re.DOTALL)
        if nav_match:
            self.assertNotIn('href="#"', nav_match.group(1))

    def test_empty_submenu_not_rendered(self):
        """Parent with no renderable children → not rendered at all."""
        parent = MenuItem.objects.create(
            menu=self.menu, title="EmptyP", destination_type="none", is_active=True,
        )
        # Add only inactive child
        MenuItem.objects.create(
            menu=self.menu, title="InactiveC", parent=parent,
            destination_type="external", destination_external_url="https://x.com",
            is_active=False,
        )
        response = self.client.get("/")
        self.assertNotContains(response, "EmptyP")

    def test_title_escaping_in_submenu(self):
        """XSS in parent/child titles is escaped."""
        parent = MenuItem.objects.create(
            menu=self.menu, title='<img src=x onerror=alert(1)>',
            destination_type="none", is_active=True,
        )
        MenuItem.objects.create(
            menu=self.menu, title='<script>xss</script>', parent=parent,
            destination_type="external", destination_external_url="https://x.com",
            is_active=True,
        )
        response = self.client.get("/")
        self.assertNotContains(response, '<img src=x')
        self.assertNotContains(response, '<script>xss</script>')
        self.assertContains(response, "&lt;script&gt;")


class FooterHierarchyRenderingTests(TestCase):
    """تست‌های رندر سلسله‌مراتب فوتر."""

    def setUp(self):
        self.category = Category.objects.create(store=_akhlaghi(), name="FC", slug="fc-fhr")

    def test_footer_child_rendered(self):
        """Footer children render in nested <ul>."""
        menu = Menu.objects.create(store=_akhlaghi(), title="F1", location="footer_1", is_active=True)
        parent = MenuItem.objects.create(
            menu=menu, title="FParent",
            destination_type="category", destination_category=self.category,
            is_active=True,
        )
        MenuItem.objects.create(
            menu=menu, title="FChild", parent=parent,
            destination_type="external", destination_external_url="https://fc.com",
            is_active=True,
        )
        response = self.client.get("/")
        self.assertContains(response, "FParent")
        self.assertContains(response, "FChild")
        self.assertContains(response, "https://fc.com")

    def test_footer_inactive_child_hidden(self):
        menu = Menu.objects.create(store=_akhlaghi(), title="F1", location="footer_1", is_active=True)
        parent = MenuItem.objects.create(
            menu=menu, title="P",
            destination_type="category", destination_category=self.category,
            is_active=True,
        )
        MenuItem.objects.create(
            menu=menu, title="HiddenChild", parent=parent,
            destination_type="external", destination_external_url="https://h.com",
            is_active=False,
        )
        response = self.client.get("/")
        self.assertNotContains(response, "HiddenChild")


class ParentCreationWorkflowTests(TestCase):
    """تست‌های گردش کار ایجاد والد موقت."""

    def setUp(self):
        self.menu = Menu.objects.create(store=_akhlaghi(), title="M", location="header")
        self.category = Category.objects.create(store=_akhlaghi(), name="WC", slug="wc-pcw")
        self.staff = User.objects.create_user(username="staff_pcw", password="p!", is_staff=True)
        _grant_akhlaghi_membership(self.staff)
        self.client.login(username="staff_pcw", password="p!")

    def test_destinationless_parent_can_be_created(self):
        """Top-level item with destination=none can be created via dashboard."""
        response = self.client.post(reverse("dashboard:menu-item-add", args=[self.menu.pk]), {
            "title": "Provisional",
            "display_order": "0", "is_active": "on",
            "destination_type": "none", "destination_external_url": "",
            "destination_category": "", "destination_product": "", "destination_brand": "",
            "parent": "",
        })
        self.assertRedirects(response, reverse("dashboard:menu-item-list", args=[self.menu.pk]))
        self.assertTrue(MenuItem.objects.filter(title="Provisional").exists())

    def test_provisional_does_not_render_without_children(self):
        """Provisional parent without children does not appear on storefront."""
        self.menu.is_active = True
        self.menu.save()
        MenuItem.objects.create(
            menu=self.menu, title="NoRender", destination_type="none", is_active=True,
        )
        response = self.client.get("/")
        self.assertNotContains(response, "NoRender")

    def test_provisional_renders_after_child_added(self):
        """After adding a child, provisional parent renders in storefront."""
        self.menu.is_active = True
        self.menu.save()
        parent = MenuItem.objects.create(
            menu=self.menu, title="NowVisible", destination_type="none", is_active=True,
        )
        MenuItem.objects.create(
            menu=self.menu, title="ValidChild", parent=parent,
            destination_type="category", destination_category=self.category,
            is_active=True,
        )
        response = self.client.get("/")
        self.assertContains(response, "NowVisible")
        self.assertContains(response, "ValidChild")

    def test_no_temporary_destination_required(self):
        """Provisional parent does not need a placeholder destination."""
        item = MenuItem(menu=self.menu, title="Clean", destination_type="none")
        item.full_clean()  # Must not raise




# ============================================================ QUERY COUNT TESTS


class NavigationQueryCountTests(TestCase):
    """تست شمارش query — حداکثر ۲ query برای ناوبری."""

    def setUp(self):
        self.category = Category.objects.create(store=_akhlaghi(), name="QC", slug="qc-qct")
        self.menu = Menu.objects.create(store=_akhlaghi(), title="H", location="header", is_active=True)
        parent = MenuItem.objects.create(
            menu=self.menu, title="P1", destination_type="none", is_active=True,
        )
        for i in range(5):
            MenuItem.objects.create(
                menu=self.menu, title=f"C{i}", parent=parent,
                destination_type="category", destination_category=self.category,
                is_active=True, display_order=i,
            )
        # Second menu
        self.footer = Menu.objects.create(store=_akhlaghi(), title="F", location="footer_1", is_active=True)
        MenuItem.objects.create(
            menu=self.footer, title="FL",
            destination_type="external", destination_external_url="https://f.com",
            is_active=True,
        )

    def test_navigation_context_bounded_queries(self):
        """Navigation context processor uses at most 2 queries regardless of item count."""
        from apps.content.context_processors import navigation_menus

        class FakeRequest:
            store = _akhlaghi()

        from django.test.utils import CaptureQueriesContext
        from django.db import connection

        with CaptureQueriesContext(connection) as ctx:
            result = navigation_menus(FakeRequest())

        # Expected: 1 for menus + 1 for prefetched items (with select_related JOINs)
        self.assertLessEqual(len(ctx), 2, f"Expected ≤2 queries, got {len(ctx)}")
        # Verify data was actually loaded
        self.assertIsNotNone(result["NAV_HEADER"])
        self.assertEqual(len(result["NAV_HEADER"]["items"][0]["children"]), 5)


# ============================================================ ACCESSIBILITY ATTRIBUTE TESTS


class NavigationAccessibilityTests(TestCase):
    """تست‌های ویژگی‌های دسترسی‌پذیری در رندر هدر."""

    def setUp(self):
        self.category = Category.objects.create(store=_akhlaghi(), name="AC", slug="ac-nat")
        self.menu = Menu.objects.create(store=_akhlaghi(), title="H", location="header", is_active=True)

    def test_escape_handler_present(self):
        """Rendered markup includes @keydown.escape handler."""
        parent = MenuItem.objects.create(
            menu=self.menu, title="DropP", destination_type="none", is_active=True,
        )
        MenuItem.objects.create(
            menu=self.menu, title="Sub", parent=parent,
            destination_type="external", destination_external_url="https://x.com",
            is_active=True,
        )
        response = self.client.get("/")
        self.assertContains(response, "@keydown.escape")

    def test_aria_expanded_present(self):
        """Trigger has :aria-expanded binding."""
        parent = MenuItem.objects.create(
            menu=self.menu, title="AE", destination_type="none", is_active=True,
        )
        MenuItem.objects.create(
            menu=self.menu, title="C", parent=parent,
            destination_type="external", destination_external_url="https://x.com",
            is_active=True,
        )
        response = self.client.get("/")
        self.assertContains(response, ':aria-expanded="open.toString()"')

    def test_aria_haspopup_present(self):
        """Trigger has aria-haspopup="true"."""
        parent = MenuItem.objects.create(
            menu=self.menu, title="HP", destination_type="none", is_active=True,
        )
        MenuItem.objects.create(
            menu=self.menu, title="C", parent=parent,
            destination_type="external", destination_external_url="https://x.com",
            is_active=True,
        )
        response = self.client.get("/")
        self.assertContains(response, 'aria-haspopup="true"')

    def test_trigger_has_accessible_label(self):
        """Trigger button has aria-label for accessibility."""
        parent = MenuItem.objects.create(
            menu=self.menu, title="Products", destination_type="none", is_active=True,
        )
        MenuItem.objects.create(
            menu=self.menu, title="C", parent=parent,
            destination_type="external", destination_external_url="https://x.com",
            is_active=True,
        )
        response = self.client.get("/")
        # Destinationless parent: aria-label is the title itself
        self.assertContains(response, 'aria-label="Products"')

    def test_parent_with_url_trigger_has_submenu_label(self):
        """Parent with URL: trigger has 'باز کردن زیرمنوی ...' label."""
        parent = MenuItem.objects.create(
            menu=self.menu, title="Shop",
            destination_type="category", destination_category=self.category,
            is_active=True,
        )
        MenuItem.objects.create(
            menu=self.menu, title="C", parent=parent,
            destination_type="external", destination_external_url="https://x.com",
            is_active=True,
        )
        response = self.client.get("/")
        content = response.content.decode()
        self.assertIn("باز کردن زیرمنوی Shop", content)

    def test_parent_link_and_trigger_are_separate(self):
        """Parent with URL: the <a> and <button> are separate elements."""
        parent = MenuItem.objects.create(
            menu=self.menu, title="Nav",
            destination_type="category", destination_category=self.category,
            is_active=True,
        )
        MenuItem.objects.create(
            menu=self.menu, title="C", parent=parent,
            destination_type="external", destination_external_url="https://x.com",
            is_active=True,
        )
        response = self.client.get("/")
        content = response.content.decode()
        # Should have both <a class="nl"...>Nav</a> AND <button...nav-submenu-trigger
        # The link
        self.assertIn('>Nav</a>', content)
        # The button trigger (separate)
        self.assertIn('nav-submenu-trigger', content)

    def test_focus_return_ref_present(self):
        """x-ref on trigger is present for focus return."""
        parent = MenuItem.objects.create(
            menu=self.menu, title="FR", destination_type="none", is_active=True,
        )
        MenuItem.objects.create(
            menu=self.menu, title="C", parent=parent,
            destination_type="external", destination_external_url="https://x.com",
            is_active=True,
        )
        response = self.client.get("/")
        self.assertContains(response, "x-ref=")
        self.assertContains(response, ".focus()")
