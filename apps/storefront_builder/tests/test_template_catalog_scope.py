"""The PUBLIC display catalog and the SELLER's restricted gallery are two different questions and must never control each other.

* public landing site (platform marketing page): which Ready Templates does the platform DISPLAY? -> every registered Ready Template (display-only);
* onboarding / Studio gallery: which may a seller CHOOSE? -> the owner-restricted subset (``template_gallery_policy``) + the pinned «current» card.
``RASTISI_TEMPLATE_GALLERY_RESTRICTED`` only ever limits the second. Nothing is removed; server-side switch checks are unchanged."""

import ast
import pathlib

from django.test import SimpleTestCase, override_settings

from apps.storefront_builder import layout_preset_registry, template_gallery_policy
from apps.storefront_builder.services import ready_template_card_service as svc

ROOT = pathlib.Path(__file__).resolve().parents[3]


def keys(cards):
    return [c["preset"].key for c in cards]


def build(scope=None, key=None, version=None):
    kwargs = {} if scope is None else {"scope": scope}
    return svc.build_ready_template_cards(None, current_template_key=key, current_template_version=version, **kwargs)


class ScopeSeparationTests(SimpleTestCase):
    def setUp(self):
        self.ready = [p.key for p in layout_preset_registry.list_ready_templates()]
        self.selectable = list(template_gallery_policy.SELECTABLE_TEMPLATE_KEYS)

    @override_settings(RASTISI_TEMPLATE_GALLERY_RESTRICTED=True)
    def test_the_public_catalog_shows_every_ready_template_while_the_gallery_stays_restricted(self):
        self.assertGreater(len(self.ready), len(self.selectable))                                  # the premise: the policy really hides some
        self.assertEqual(keys(build(svc.SCOPE_PUBLIC)), self.ready)                                # public: ALL registered Ready Templates
        self.assertEqual(keys(build(svc.SCOPE_GALLERY)), self.selectable)                          # gallery: only the owner's list, in the owner's order

    @override_settings(RASTISI_TEMPLATE_GALLERY_RESTRICTED=True)
    def test_the_default_scope_is_the_public_catalog_because_the_landing_site_calls_it_without_a_scope(self):
        """The landing site (platform) calls ``build_ready_template_cards(None, current_template_key=None, current_template_version=None)``."""
        self.assertEqual(keys(build()), self.ready)

    @override_settings(RASTISI_TEMPLATE_GALLERY_RESTRICTED=False)
    def test_with_the_restriction_off_both_scopes_agree(self):
        self.assertEqual(keys(build(svc.SCOPE_PUBLIC)), keys(build(svc.SCOPE_GALLERY)))

    @override_settings(RASTISI_TEMPLATE_GALLERY_RESTRICTED=True)
    def test_the_public_scope_never_gets_a_pinned_hidden_current_card_but_the_gallery_does(self):
        hidden = next(p for p in layout_preset_registry.list_ready_templates() if p.key not in self.selectable)
        gallery = build(svc.SCOPE_GALLERY, hidden.key, hidden.version)
        pinned = [c for c in gallery if c.get("is_hidden_current")]
        self.assertEqual([c["preset"].key for c in pinned], [hidden.key])                         # a store keeps its hidden template, shown as current
        self.assertEqual(len(gallery), len(self.selectable) + 1)
        public = build(svc.SCOPE_PUBLIC, hidden.key, hidden.version)
        self.assertFalse(any(c.get("is_hidden_current") for c in public))                         # display-only: nothing is pinned or "current-restricted"
        self.assertEqual(keys(public), self.ready)

    def test_an_unknown_scope_is_refused_instead_of_silently_choosing_one(self):
        with self.assertRaises(ValueError):
            build("everything")

    @override_settings(RASTISI_TEMPLATE_GALLERY_RESTRICTED=True)
    def test_no_template_is_removed_and_the_selection_rule_is_unchanged(self):
        hidden = next(p for p in layout_preset_registry.list_ready_templates() if p.key not in self.selectable)
        self.assertFalse(template_gallery_policy.is_selectable_key(hidden.key))                   # a seller still cannot SWITCH TO a hidden template
        self.assertIn(hidden.key, keys(build(svc.SCOPE_PUBLIC)))                                   # …yet it stays registered and publicly displayed


class EveryProductionCallerIsExplicitTests(SimpleTestCase):
    """AST guard: the default (public) scope is only for the platform's public landing site. Any other production caller must pass the restricted gallery
    scope explicitly, otherwise a future seller-facing gallery would silently offer every template (fail-open)."""

    PUBLIC_ALLOWLIST = {"apps/portal/public_site/services.py"}            # the landing site (lives on `main`); display-only
    SERVICE = "apps/storefront_builder/services/ready_template_card_service.py"

    def calls(self):
        found = []
        for path in (ROOT / "apps").rglob("*.py"):
            rel = path.relative_to(ROOT).as_posix()
            if "/tests/" in rel or rel == self.SERVICE or "/migrations/" in rel:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and getattr(node.func, "attr", getattr(node.func, "id", "")) == "build_ready_template_cards":
                    scope = next((kw.value for kw in node.keywords if kw.arg == "scope"), None)
                    found.append((rel, ast.unparse(scope) if scope is not None else None))
        return found

    def test_seller_facing_callers_pass_the_gallery_scope_explicitly(self):
        calls = self.calls()
        self.assertGreaterEqual(len(calls), 2)                                                      # the guard is not vacuous: onboarding + Studio galleries
        for rel, scope in calls:
            if rel in self.PUBLIC_ALLOWLIST:
                continue
            self.assertTrue(scope and scope.endswith("SCOPE_GALLERY"), f"{rel} must pass scope=SCOPE_GALLERY (got {scope!r})")
        self.assertEqual({rel for rel, _ in calls} & {"apps/portal/views.py", "apps/storefront_builder/r4_views.py"},
                         {"apps/portal/views.py", "apps/storefront_builder/r4_views.py"})
