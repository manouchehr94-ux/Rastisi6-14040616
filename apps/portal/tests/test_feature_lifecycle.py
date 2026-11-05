"""Acceptance: the full lifecycle of an owner-defined feature, end to end (admin UI → public page → real backend access).

The scenario: the owner registers a *future* capability («دستیار هوشمند»), assigns it to Ultra only, shows it publicly as
«به‌زودی», proves it grants nothing, a developer later "implements" the gate (simulated by ``registered_for_test`` — the same
act as adding a ``Capability`` to ``capability_registry.CAPABILITIES``), the owner marks it ready/available, publishes a new
Ultra version, and real access flips on for Ultra subscribers only. Synthetic plan values — fixtures, not product decisions."""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.portal.models import PlatformAuditLogEntry
from apps.subscriptions import capability_registry as registry
from apps.subscriptions.models import Plan, PlanEntitlement, PlanVersion, PricingFeature
from apps.subscriptions.services import enforcement
from apps.subscriptions.services import entitlement_service as ent
from apps.subscriptions.services import feature_gate
from apps.subscriptions.services import feature_service as fs
from apps.subscriptions.services import plan_service as ps
from apps.subscriptions.services import pricing_page_service as page
from apps.subscriptions.services.entitlement_service import FeatureNotAvailable
from apps.subscriptions.tests.test_pricing_dynamic import make_plan, store_on

User = get_user_model()
PUBLIC = "rastisi.localhost"
ADMIN = "platformadmins.rastisi.localhost"
KEY = "ai.assistant"


def _capability():
    return registry.Capability(key=KEY, enforced_by="apps/ai/services/assistant.py::ask (test double)", tests=("test_feature_lifecycle",))


@override_settings(ALLOWED_HOSTS=[PUBLIC, ADMIN, "testserver"])
class FeatureLifecycleAcceptanceTests(TestCase):
    def setUp(self):
        self.addCleanup(cache.clear)
        cache.clear()
        self.owner = User.objects.create_user(username="owner@example.com", email="owner@example.com", password="a-very-strong-pass-1",
                                              is_staff=True, is_superuser=True)
        self.base_plan, self.base_v = make_plan("base", base=290000, order=1, limits={"catalog.products": 100})
        self.adv_plan, self.adv_v = make_plan("advanced", base=690000, order=2, limits={"catalog.products": 1000})
        self.ultra_plan, self.ultra_v = make_plan("ultra", base=1490000, order=3, limits={"catalog.products": None})
        self.base_store, _ = store_on(self.base_v, "s-base")
        self.adv_store, _ = store_on(self.adv_v, "s-adv")
        self.ultra_store, _ = store_on(self.ultra_v, "s-ultra")   # subscribed to ultra v1 (published BEFORE the feature exists)

    def feature(self):
        return PricingFeature.objects.get(key="ai_assistant")

    def public_row(self):
        for cat in page.build_pricing_page()["matrix"]:
            for row in cat["rows"]:
                if row["feature"].key == "ai_assistant":
                    return row
        return None

    def assert_access(self, expected):
        for store, name in ((self.base_store, "base"), (self.adv_store, "advanced"), (self.ultra_store, "ultra")):
            ent.clear_entitlement_cache()
            self.assertEqual(ent.has_entitlement(store, KEY), expected[name], f"{name}: has_entitlement")
            if expected[name]:
                enforcement.enforce_feature(store, KEY)
            else:
                with self.assertRaises(FeatureNotAvailable):
                    enforcement.enforce_feature(store, KEY)

    def new_ultra_version(self, *, enabled):
        draft = ps.get_or_create_draft(self.ultra_plan, actor=self.owner)
        fs.assign_to_plan_version(actor=self.owner, plan_version=draft, feature=self.feature(), enabled=enabled)
        return ps.publish_plan_version(draft, actor=self.owner)

    # ------------------------------------------------------------------------------------------------ the 11 steps
    def test_full_lifecycle(self):
        # 1. create the feature from the Platform Admin UI (real HTTP, no code change)
        self.client.force_login(self.owner)
        response = self.client.post("/features/add/", {
            "key": "ai_assistant", "title": "دستیار هوشمند", "category": "marketing", "icon": "🤖", "entitlement_key": KEY,
            "description": "پاسخ‌دهیِ هوشمند به مشتریان", "help_text": "راهنما", "commercial_status": "coming_soon", "is_visible": "on",
            "planned_release_on": "2027-03-01",
        }, HTTP_HOST=ADMIN)
        self.assertEqual(response.status_code, 302)
        feature = self.feature()
        self.assertTrue(feature.is_custom)
        self.assertEqual((feature.technical_status, feature.commercial_status), ("planned", "coming_soon"))
        self.assertFalse(feature.grants_access)

        # 2. assign to Ultra only (a published version is immutable → new draft → assign → publish)
        ultra_v2 = self.new_ultra_version(enabled=True)
        self.assertEqual(ultra_v2.version_number, 2)

        # 3. the public pricing page shows it as «به‌زودی» for Ultra only, never as available
        row = self.public_row()
        self.assertIsNotNone(row)
        self.assertTrue(row["is_soon"])
        self.assertEqual([c["kind"] for c in row["cells"]], ["none", "none", "soon"])
        html = self.client.get("/plans/", HTTP_HOST=PUBLIC).content.decode()
        self.assertIn('data-feature="ai_assistant"', html)
        self.assertIn("به‌زودی", html)
        self.assertIn("دستیار هوشمند", html)
        self.assertIn("🤖", html)

        # 4. it grants NO access — not to Ultra subscribers, not to anyone (key is unregistered in code, tech status planned)
        self.assertFalse(registry.is_registered(KEY))
        self.assert_access({"base": False, "advanced": False, "ultra": False})
        # moving the ultra subscriber onto the version that lists it still grants nothing
        from apps.subscriptions.services import subscription_service as sub_svc
        sub_svc.change_plan_version(self.ultra_store.subscriptions.get(is_current=True), ultra_v2, actor=self.owner, reason="test")
        self.assert_access({"base": False, "advanced": False, "ultra": False})

        # a mere DB flag cannot fake readiness: «ready» without a registered gate is refused
        with self.assertRaises(fs.FeatureError):
            fs.set_technical_status(actor=self.owner, feature=feature, status="ready")
        with self.assertRaises(fs.FeatureError):
            fs.set_commercial_status(actor=self.owner, feature=feature, status="available")

        # 5. the developer implements + registers the backend gate; 6. the owner marks it technically ready
        with registry.registered_for_test(_capability()):
            fs.set_technical_status(actor=self.owner, feature=self.feature(), status="ready")
            self.assertTrue(self.feature().is_technically_ready)
            # ready but not yet commercially available → still no access
            self.assert_access({"base": False, "advanced": False, "ultra": False})
            fs.set_commercial_status(actor=self.owner, feature=self.feature(), status="available")
            self.assertEqual(self.feature().public_state, "available")

            # 7+8. ultra v2 was published BEFORE activation → explicit new-version contract: it does not silently start granting;
            #      the owner publishes a new Ultra version with it enabled and the subscriber is moved onto it
            self.assert_access({"base": False, "advanced": False, "ultra": False})
            ultra_v3 = self.new_ultra_version(enabled=True)
            self.assertEqual(ultra_v3.version_number, 3)
            sub_svc.change_plan_version(self.ultra_store.subscriptions.get(is_current=True), ultra_v3, actor=self.owner, reason="test")
            # 8 + 9. Ultra subscribers have real access; Base/Advanced do not
            self.assert_access({"base": False, "advanced": False, "ultra": True})
            # the public page now shows it as a real, available feature for Ultra only
            row = self.public_row()
            self.assertFalse(row["is_soon"])
            self.assertEqual([c["kind"] for c in row["cells"]], ["none", "none", "check"])

            # 10. disable it in a future Ultra version (v4): new subscribers of v4 don't get it …
            ultra_v4 = self.new_ultra_version(enabled=False)
            ent.clear_entitlement_cache()
            self.assertFalse(ent.has_entitlement(None, KEY, plan_version=ultra_v4))
            self.assertTrue(ent.has_entitlement(None, KEY, plan_version=ultra_v3))
            # 11. … but the existing subscriber, still contractually on v3, is NOT silently stripped
            self.assert_access({"base": False, "advanced": False, "ultra": True})
            self.assertEqual(self.ultra_store.subscriptions.get(is_current=True).plan_version_id, ultra_v3.pk)

        # without the code registration (developer rolled the gate back) nothing is granted any more — fail closed
        ent.clear_entitlement_cache()
        self.assertFalse(ent.has_entitlement(self.ultra_store, KEY))

        # every step was audited with actor + before/after
        actions = set(PlatformAuditLogEntry.objects.values_list("action_code", flat=True))
        for code in ("platform_admin.feature_created", "platform_admin.feature_assigned", "platform_admin.feature_technical_status",
                     "platform_admin.feature_commercial_status", "platform_admin.plan_version_published", "platform_admin.plan_draft_created"):
            self.assertIn(code, actions)
        entry = PlatformAuditLogEntry.objects.filter(action_code="platform_admin.feature_commercial_status").first()
        self.assertEqual(entry.actor_id, self.owner.pk)
        self.assertIn("coming_soon", entry.before_summary)
        self.assertIn("available", entry.after_summary)

    # ------------------------------------------------------------------------------------------------ gate invariants
    def test_arbitrary_key_in_a_plan_version_never_grants_access(self):
        feature = fs.create_feature(actor=self.owner, key="ghost", title="شبح", category="marketing", entitlement_key="ghost.feature")
        draft = ps.get_or_create_draft(self.base_plan)
        fs.assign_to_plan_version(actor=self.owner, plan_version=draft, feature=feature, enabled=True)
        published = ps.publish_plan_version(draft)
        ent.clear_entitlement_cache()
        self.assertFalse(ent.has_entitlement(None, "ghost.feature", plan_version=published))
        self.assertFalse(ent.has_entitlement(self.base_store, "ghost.feature"))
        # even forcing every DB state to "ready/available" cannot make an unregistered key enforceable
        PricingFeature.objects.filter(pk=feature.pk).update(technical_status="ready", commercial_status="available")
        feature_gate.invalidate()
        ent.clear_entitlement_cache()
        self.assertFalse(PricingFeature.objects.get(pk=feature.pk).is_technically_ready)
        self.assertFalse(ent.has_entitlement(self.base_store, "ghost.feature"))
        self.assertEqual(PricingFeature.objects.get(pk=feature.pk).public_state, "coming_soon")

    def test_kill_switch_cuts_access_and_requires_a_reason(self):
        with registry.registered_for_test(_capability()):
            f = fs.create_feature(actor=self.owner, key="ai_assistant", title="دستیار", category="marketing", entitlement_key=KEY)
            fs.set_technical_status(actor=self.owner, feature=f, status="ready")
            fs.set_commercial_status(actor=self.owner, feature=f, status="available")
            v = self.new_ultra_version(enabled=True)
            from apps.subscriptions.services import subscription_service as sub_svc
            sub_svc.change_plan_version(self.ultra_store.subscriptions.get(is_current=True), v, actor=self.owner, reason="t")
            self.assert_access({"base": False, "advanced": False, "ultra": True})
            with self.assertRaises(fs.FeatureError):
                fs.set_kill_switch(actor=self.owner, feature=f, on=True, reason="")
            fs.set_kill_switch(actor=self.owner, feature=f, on=True, reason="incident")
            self.assert_access({"base": False, "advanced": False, "ultra": False})
            fs.set_kill_switch(actor=self.owner, feature=f, on=False)
            self.assert_access({"base": False, "advanced": False, "ultra": True})

    def test_cannot_roll_an_available_feature_back_to_coming_soon(self):
        with registry.registered_for_test(_capability()):
            f = fs.create_feature(actor=self.owner, key="ai_assistant", title="دستیار", category="marketing", entitlement_key=KEY)
            fs.set_technical_status(actor=self.owner, feature=f, status="ready")
            fs.set_commercial_status(actor=self.owner, feature=f, status="available")
            with self.assertRaises(fs.FeatureError):
                fs.set_commercial_status(actor=self.owner, feature=f, status="coming_soon")
            with self.assertRaises(fs.FeatureError):
                fs.set_technical_status(actor=self.owner, feature=f, status="planned")
            # withdrawn: closes sale/display but keeps the access of versions that already contain it
            v = self.new_ultra_version(enabled=True)
            from apps.subscriptions.services import subscription_service as sub_svc
            sub_svc.change_plan_version(self.ultra_store.subscriptions.get(is_current=True), v, actor=self.owner, reason="t")
            fs.set_commercial_status(actor=self.owner, feature=f, status="withdrawn")
            self.assertEqual(PricingFeature.objects.get(pk=f.pk).public_state, "hidden")
            self.assert_access({"base": False, "advanced": False, "ultra": True})

    def test_hidden_feature_is_not_on_the_public_page_and_hide_toggle_is_audited(self):
        f = fs.create_feature(actor=self.owner, key="ai_assistant", title="دستیار", category="marketing", entitlement_key=KEY)
        fs.assign_to_plan_version(actor=self.owner, plan_version=ps.get_or_create_draft(self.ultra_plan), feature=f, enabled=True)
        ps.publish_plan_version(ps.get_or_create_draft(self.ultra_plan))
        self.assertIsNotNone(self.public_row())
        fs.update_feature(actor=self.owner, feature=f, is_visible=False)
        self.assertIsNone(self.public_row())
        entry = PlatformAuditLogEntry.objects.filter(action_code="platform_admin.feature_updated").latest("pk")
        self.assertIn('"visible": true', entry.before_summary)
        self.assertIn('"visible": false', entry.after_summary)

    def test_planned_row_is_not_shown_when_no_published_plan_lists_it(self):
        fs.create_feature(actor=self.owner, key="ai_assistant", title="دستیار", category="marketing", entitlement_key=KEY)
        self.assertIsNone(self.public_row())

    def test_planned_release_date_is_shown_only_when_the_owner_set_one(self):
        import datetime
        f = fs.create_feature(actor=self.owner, key="ai_assistant", title="دستیار", category="marketing", entitlement_key=KEY)
        ps.publish_plan_version(self.assign_ultra(f))
        self.assertEqual(self.public_row()["when"], "")
        fs.update_feature(actor=self.owner, feature=f, planned_release_on=datetime.date(2027, 3, 21))
        self.assertIn("فروردین", self.public_row()["when"])

    def assign_ultra(self, feature):
        draft = ps.get_or_create_draft(self.ultra_plan)
        fs.assign_to_plan_version(actor=self.owner, plan_version=draft, feature=feature, enabled=True)
        return draft

    # ------------------------------------------------------------------------------------------------ immutability / drafts
    def test_published_versions_are_immutable_and_assignment_needs_a_draft(self):
        f = fs.create_feature(actor=self.owner, key="ai_assistant", title="دستیار", category="marketing", entitlement_key=KEY)
        with self.assertRaises(fs.FeatureError):
            fs.assign_to_plan_version(actor=self.owner, plan_version=self.ultra_v, feature=f, enabled=True)
        with self.assertRaises(ps.PlanServiceError):
            ps.update_draft_version(self.ultra_v, actor=self.owner, trial_days=3)

    def test_draft_is_edited_in_place_and_clone_keeps_prices_and_entitlements(self):
        draft = ps.get_or_create_draft(self.ultra_plan, actor=self.owner)
        again = ps.get_or_create_draft(self.ultra_plan, actor=self.owner)
        self.assertEqual(draft.pk, again.pk)                       # no pile of drafts
        self.assertEqual(self.ultra_plan.versions.filter(status="draft").count(), 1)
        self.assertTrue(PlanEntitlement.objects.filter(plan_version=draft, entitlement__key="catalog.products", is_unlimited=True).exists())
        ps.update_draft_version(draft, actor=self.owner, trial_days=9)
        draft.refresh_from_db()
        self.assertEqual(draft.trial_days, 9)
        self.assertEqual(self.ultra_v.__class__.objects.get(pk=self.ultra_v.pk).trial_days, 0)   # published untouched
        entry = PlatformAuditLogEntry.objects.filter(action_code="platform_admin.plan_draft_updated").latest("pk")
        self.assertIn("0", entry.before_summary)
        self.assertIn("9", entry.after_summary)

    def test_quota_schema_bounds_are_validated_per_plan(self):
        f = fs.create_feature(actor=self.owner, key="ai_credits", title="اعتبارِ هوش مصنوعی", category="marketing",
                              entitlement_key="ai.credits", value_type="integer_limit", unit_label="درخواست", config_schema={"min": 10, "max": 500})
        draft = ps.get_or_create_draft(self.base_plan)
        with self.assertRaises(fs.FeatureError):
            fs.assign_to_plan_version(actor=self.owner, plan_version=draft, feature=f, enabled=True, limit=5)
        with self.assertRaises(fs.FeatureError):
            fs.assign_to_plan_version(actor=self.owner, plan_version=draft, feature=f, enabled=True, limit=501)
        with self.assertRaises(fs.FeatureError):
            fs.assign_to_plan_version(actor=self.owner, plan_version=draft, feature=f, enabled=True, limit="abc")
        out = fs.assign_to_plan_version(actor=self.owner, plan_version=draft, feature=f, enabled=True, limit=100)
        self.assertEqual(out["limit"], 100)
        with self.assertRaises(fs.FeatureError):
            fs.create_feature(actor=self.owner, key="bad", title="x", category="marketing", config_schema={"min": 9, "max": 3})

    def test_feature_key_is_unique_and_stable(self):
        fs.create_feature(actor=self.owner, key="ai_assistant", title="دستیار", category="marketing", entitlement_key=KEY)
        with self.assertRaises(fs.FeatureError):
            fs.create_feature(actor=self.owner, key="ai_assistant", title="دیگری", category="marketing", entitlement_key="x.y")
        with self.assertRaises(fs.FeatureError):
            fs.create_feature(actor=self.owner, key="Bad Key", title="x", category="marketing")
        with self.assertRaises(fs.FeatureError):
            fs.update_feature(actor=self.owner, feature=self.feature(), key="other")

    # ------------------------------------------------------------------------------------------------ archive / migration
    def test_archiving_a_plan_with_subscribers_does_not_break_them(self):
        ent.clear_entitlement_cache()
        before = ent.get_entitlement_limit(self.adv_store, "catalog.products")
        ps.set_plan_archived(self.adv_plan, archived=True, actor=self.owner)
        ent.clear_entitlement_cache()
        self.assertEqual(ent.get_entitlement_limit(self.adv_store, "catalog.products"), before)
        self.assertTrue(self.adv_store.subscriptions.filter(is_current=True, plan_version=self.adv_v).exists())
        self.assertNotIn("advanced", [c["plan"].code for c in page.build_pricing_page()["cards"]])     # closed to new sales / public page
        entry = PlatformAuditLogEntry.objects.filter(action_code="platform_admin.plan_archived").latest("pk")
        self.assertEqual(entry.metadata.get("current_subscribers_unaffected"), 1)
        ps.set_plan_archived(self.adv_plan, archived=False, actor=self.owner)
        self.assertIn("advanced", [c["plan"].code for c in page.build_pricing_page()["cards"]])

    def test_explicit_migration_needs_reason_and_blocks_silent_loss(self):
        draft = ps.get_or_create_draft(self.adv_plan)
        ps.set_plan_entitlement(draft, "catalog.import", is_enabled=False)
        v2 = ps.publish_plan_version(draft)
        old_preview = ps.plan_migration_preview(self.adv_v, v2)
        self.assertEqual(old_preview["subscribers"], 1)
        # grandfathering default: publishing v2 moved nobody
        self.assertEqual(self.adv_store.subscriptions.get(is_current=True).plan_version_id, self.adv_v.pk)
        with self.assertRaises(ps.PlanServiceError):
            ps.migrate_subscribers(self.adv_v, v2, actor=self.owner, reason="")
        # a migration that removes an entitlement needs explicit acceptance
        # explicit loss scenario: base v2 grants catalog.export, base v3 removes it (published versions are immutable → drafts)
        d2 = ps.get_or_create_draft(self.base_plan)
        ps.set_plan_entitlement(d2, "catalog.export", is_enabled=True)
        b2 = ps.publish_plan_version(d2)
        d3 = ps.get_or_create_draft(self.base_plan)
        ps.set_plan_entitlement(d3, "catalog.export", is_enabled=False)
        b3 = ps.publish_plan_version(d3)
        from apps.subscriptions.services import subscription_service as sub_svc
        sub_svc.change_plan_version(self.base_store.subscriptions.get(is_current=True), b2, actor=self.owner, reason="t")
        self.assertIn("catalog.export", ps.plan_migration_preview(b2, b3)["lost"])
        with self.assertRaises(ps.PlanServiceError):
            ps.migrate_subscribers(b2, b3, actor=self.owner, reason="cleanup")
        self.assertEqual(ps.migrate_subscribers(b2, b3, actor=self.owner, reason="cleanup", accept_losses=True), 1)
        self.assertEqual(self.base_store.subscriptions.get(is_current=True).plan_version_id, b3.pk)
        entry = PlatformAuditLogEntry.objects.filter(action_code="platform_admin.subscribers_migrated").latest("pk")
        self.assertEqual(entry.actor_id, self.owner.pk)

    # ------------------------------------------------------------------------------------------------ admin UI
    def test_admin_screens_render_and_non_staff_are_refused(self):
        f = fs.create_feature(actor=self.owner, key="ai_assistant", title="دستیار هوشمند", category="marketing", entitlement_key=KEY, icon="🤖")
        self.new_ultra_version(enabled=True)
        self.client.force_login(self.owner)
        for path in ("/features/", f"/features/{f.pk}/edit/", "/features/add/", "/plans/assignments/", f"/plans/{self.ultra_plan.pk}/migrate/", "/plans/"):
            response = self.client.get(path, HTTP_HOST=ADMIN)
            self.assertEqual(response.status_code, 200, path)
        html = self.client.get("/plans/assignments/", HTTP_HOST=ADMIN).content.decode()
        self.assertIn("دستیار هوشمند", html)
        self.assertIn("برنامه‌ریزی‌شده", html)          # published ultra v2 lists it but it grants nothing
        self.assertIn("بدونِ دسترسی", html)
        self.client.logout()
        ordinary = User.objects.create_user(username="x@example.com", email="x@example.com", password="a-very-strong-pass-1")
        self.client.force_login(ordinary)
        for path in ("/features/", "/plans/assignments/", f"/plans/{self.ultra_plan.pk}/migrate/"):
            self.assertNotEqual(self.client.get(path, HTTP_HOST=ADMIN).status_code, 200, path)

    def test_assignment_matrix_post_saves_to_the_draft_only(self):
        f = fs.create_feature(actor=self.owner, key="ai_assistant", title="دستیار", category="marketing", entitlement_key=KEY)
        draft = ps.get_or_create_draft(self.ultra_plan)
        self.client.force_login(self.owner)
        response = self.client.post("/plans/assignments/", {"action": "save", f"present_{draft.pk}": "1", f"cell_{draft.pk}_{f.pk}": "1", f"en_{draft.pk}_{f.pk}": "on"}, HTTP_HOST=ADMIN)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(PlanEntitlement.objects.filter(plan_version=draft, entitlement=f.entitlement, is_enabled=True).exists())
        self.assertFalse(PlanEntitlement.objects.filter(plan_version=self.ultra_v, entitlement=f.entitlement).exists())

    def test_plan_promo_label_is_saved_and_shown_on_the_public_card(self):
        self.client.force_login(self.owner)
        self.client.post(f"/plans/{self.ultra_plan.pk}/edit/", {
            "name": "Ultra", "code": "ultra", "billing_interval": "monthly", "display_price": "1490000", "marketing_submitted": "1",
            "promo_label": "۲ ماه رایگان", "price_monthly": "1490000",
        }, HTTP_HOST=ADMIN)
        self.ultra_plan.refresh_from_db()
        self.assertEqual(self.ultra_plan.promo_label, "۲ ماه رایگان")
        self.assertEqual(self.ultra_plan.versions.filter(status="draft").count(), 1)       # edited the draft in place
        self.client.post(f"/plans/{self.ultra_plan.pk}/edit/", {"name": "Ultra", "code": "ultra", "billing_interval": "monthly", "display_price": "1490000"}, HTTP_HOST=ADMIN)
        self.assertEqual(self.ultra_plan.versions.filter(status="draft").count(), 1)       # still one draft, no pile-up
        self.assertIn("۲ ماه رایگان", self.client.get("/plans/", HTTP_HOST=PUBLIC).content.decode())
