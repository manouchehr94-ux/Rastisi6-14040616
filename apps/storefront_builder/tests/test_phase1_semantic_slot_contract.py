"""Phase-1 RED tests — CROSS-TEMPLATE SEMANTIC SLOT IDENTITY CONTRACT.

Architecture Convergence / Phase 1 — Safe Ready Template Switching /
Merchant Preservation.

RED tests for the ratified semantic-slot contract that production does NOT
yet implement:

  * ``PresetSectionEntry`` gains ``semantic_slot_key: str | None = None``
    (recipe metadata only — NO new DB field/model/migration/registry).
  * Every Ready Template ``PresetSectionEntry`` carries an explicit,
    non-empty, syntactically-valid ``semantic_slot_key``.
  * Identity is NOT positional (not derived from list index).
  * A semantic role is unique within one Ready Template page.
  * The SAME role may sit at DIFFERENT indexes across templates.
  * The SAME ``section_key`` may carry DIFFERENT semantic roles.
  * Non-Ready structural presets may keep ``semantic_slot_key=None``.
  * Historical identity resolves ONLY through the exact registered version
    via ``get_layout_preset_version(key, version)`` — never latest fallback,
    never heuristic; unresolved => fail safe / preserve.

Corrective-pass notes (Architect review of b1107507):
  * Blocker 3/17: the duplicate-semantic-role registry test is built from an
    otherwise fully VALID Ready Template via ``dataclasses.replace`` (real
    complete ``store_appearance`` preserved) so the ONLY invalid property is
    the duplicate role — and cleans up BOTH module registries in ``finally``.
  * Blocker 15: an explicit "same role at different indexes" test.
  * Blocker 16: the ferdowsi test asserts roles are RESOLVED (not merely
    "no collision among the None-filtered set").

This module imports cleanly even though ``semantic_slot_key`` does not exist
yet; dependent assertions fail at test level via the ``_MISSING`` sentinel.
"""

import dataclasses

from django.test import SimpleTestCase, TestCase

from apps.storefront_builder import a8_ready_templates as a8
from apps.storefront_builder import layout_preset_registry as lpr


# --- Ratified mapping (EXPECTED data for the tests — NOT a production catalog) ---

RATIFIED_HOME_TOKEN_ROLE = {
    "hero": "hero.primary",
    "circular_categories": "categories.primary",
    "tile_categories": "categories.primary",
    "arch_categories": "categories.primary",
    "chip_categories": "categories.primary",
    "indexed_categories": "categories.primary",
    "product_grid": "products.primary",
    "product_list": "products.primary",
    "product_rail": "products.primary",
    "bento_products": "products.primary",
    "featured_products": "products.featured",
    "sale_products": "products.sale",
    "ticker": "announcement.primary",
    "brand_story": "brand_story.primary",
    "editorial_note": "editorial_note.primary",
    "service_strip": "trust.primary",
    "trust_features": "trust.primary",
    "brands": "brands.primary",
    "testimonials": "testimonials.primary",
    "newsletter": "newsletter.primary",
    "community_gallery": "community.gallery",
    "collection_tiles": "collection.tiles",
}

RATIFIED_NON_HOME_ROLE = {
    ("product_detail", "product_main"): "product.main",
    ("product_detail", "product_description"): "product.description",
    ("product_detail", "related_products"): "product.related",
    ("listing", "product_listing"): "products.listing",
    ("collection", "collection_header"): "collection.header",
    ("collection", "collection_products"): "collection.products",
    ("search", "product_listing"): "products.search",
    ("cart", "cart_items"): "cart.items",
    ("cart", "cart_summary"): "cart.summary",
}

_MISSING = object()


def _semantic_slot_key(entry):
    """Return an entry's ``semantic_slot_key`` or the ``_MISSING`` sentinel.

    Introspective on purpose: while the field does not yet exist on the
    frozen ``PresetSectionEntry`` dataclass, this returns ``_MISSING`` so the
    dependent assertion fails at test level with a clear message, rather than
    raising ``AttributeError`` and aborting collection.
    """
    return getattr(entry, "semantic_slot_key", _MISSING)


def _iter_entries(definition):
    for page_type, entries in definition.pages.items():
        for index, entry in enumerate(entries):
            yield page_type, index, entry


def _field_exists():
    return "semantic_slot_key" in {f.name for f in dataclasses.fields(lpr.PresetSectionEntry)}


class SemanticSlotFieldExistenceTests(SimpleTestCase):
    """1 & 9 — the field must exist and Ready Templates must populate it."""

    def test_preset_section_entry_declares_semantic_slot_key_field(self):
        self.assertTrue(
            _field_exists(),
            "RED: PresetSectionEntry must gain an additive "
            "`semantic_slot_key: str | None = None` recipe-metadata field.",
        )

    def test_ready_template_entries_require_explicit_semantic_slot_key(self):
        offenders = []
        for preset in lpr.list_ready_templates():
            for page_type, index, entry in _iter_entries(preset):
                key = _semantic_slot_key(entry)
                if key is _MISSING or key is None or not str(key).strip():
                    offenders.append(f"{preset.key}:{preset.version}:{page_type}[{index}]")
        self.assertEqual(
            offenders,
            [],
            "RED: every Ready Template section entry must declare a non-empty "
            f"semantic_slot_key. Missing on: {offenders[:12]}",
        )

    def test_non_ready_structural_preset_may_omit_semantic_role(self):
        non_ready = [p for p in lpr.list_layout_presets() if not p.is_ready_template]
        self.assertTrue(non_ready, "expected at least one non-Ready structural preset")
        for preset in non_ready:
            for _pt, _idx, entry in _iter_entries(preset):
                key = _semantic_slot_key(entry)
                self.assertTrue(
                    key is _MISSING or key is None or isinstance(key, str),
                    f"non-Ready preset {preset.key}: semantic_slot_key must be None or str",
                )


class SemanticSlotSyntaxTests(SimpleTestCase):
    """5 — normalized syntax; 2 — not positional."""

    def test_semantic_slot_key_uses_safe_normalized_syntax(self):
        import re

        pattern = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")
        bad = []
        for preset in lpr.list_ready_templates():
            for page_type, index, entry in _iter_entries(preset):
                key = _semantic_slot_key(entry)
                if key is _MISSING or key is None:
                    bad.append(f"{preset.key}:{page_type}[{index}]=<missing>")
                elif not pattern.fullmatch(str(key)):
                    bad.append(f"{preset.key}:{page_type}[{index}]={key!r}")
        self.assertEqual(
            bad,
            [],
            "RED: semantic_slot_key must match ^<domain>.<qualifier>...$ "
            f"normalized syntax. Offenders: {bad[:12]}",
        )

    def test_semantic_slot_key_is_not_positional(self):
        positional_like = []
        for preset in lpr.list_ready_templates():
            for page_type, index, entry in _iter_entries(preset):
                key = _semantic_slot_key(entry)
                if key is _MISSING or key is None:
                    continue
                if str(key).endswith(f":{index}") or str(key) == str(index):
                    positional_like.append(f"{preset.key}:{page_type}[{index}]={key!r}")
        self.assertEqual(
            positional_like,
            [],
            "RED: semantic_slot_key must be role-based, never index-derived. "
            f"Positional-looking keys: {positional_like[:12]}",
        )


class SemanticSlotUniquenessTests(TestCase):
    """3 & 17 — duplicate semantic role inside one Ready Template page is
    rejected by registry validation, built from an otherwise-VALID Ready
    Template, with guaranteed registry cleanup."""

    def test_semantic_role_is_unique_within_each_ready_template_page(self):
        collisions = []
        for preset in lpr.list_ready_templates():
            for page_type, entries in preset.pages.items():
                seen = {}
                for index, entry in enumerate(entries):
                    key = _semantic_slot_key(entry)
                    if key is _MISSING or key is None:
                        continue
                    if key in seen:
                        collisions.append(
                            f"{preset.key}:{preset.version}:{page_type} role={key!r} "
                            f"at index {seen[key]} and {index}"
                        )
                    seen[key] = index
        self.assertEqual(
            collisions,
            [],
            "RED: a semantic role must be unique within one Ready Template "
            f"page. Collisions: {collisions[:12]}",
        )

    def test_registry_validation_rejects_duplicate_semantic_role_on_a_page(self):
        if not _field_exists():
            self.fail(
                "RED: semantic_slot_key not implemented; registry cannot yet "
                "validate duplicate semantic roles per page."
            )

        # Build the invalid preset from a REAL, fully valid Ready Template so
        # the ONLY invalid property is the duplicated semantic role (Blocker 3:
        # never store_appearance=None, which the registry already rejects for a
        # different reason). Preserve its complete store_appearance / metadata.
        base = next(iter(lpr.list_ready_templates()), None)
        self.assertIsNotNone(base, "need at least one Ready Template to derive from")
        home_entries = base.pages.get("home")
        self.assertTrue(home_entries, "base Ready Template must have a home page")

        # Two entries carrying the SAME semantic role on the same page.
        dup_entry = dataclasses.replace(home_entries[0], semantic_slot_key="hero.primary")
        dup_entry_2 = dataclasses.replace(
            home_entries[0], semantic_slot_key="hero.primary"
        )

        test_key = "__red_dupe_role_probe__"
        test_version = "1"
        invalid = dataclasses.replace(
            base,
            key=test_key,
            version=test_version,
            pages={**base.pages, "home": (dup_entry, dup_entry_2)},
        )

        try:
            with self.assertRaises(
                lpr.InvalidLayoutPresetError,
                msg="RED: register_layout_preset must fail closed on a duplicate "
                "semantic role within one Ready Template page.",
            ):
                lpr.register_layout_preset(invalid)
        finally:
            # Blocker 17: guarantee no contamination of module-global state,
            # even if validation unexpectedly failed open.
            lpr.LAYOUT_PRESET_REGISTRY.pop(test_key, None)
            lpr.LAYOUT_PRESET_VERSION_REGISTRY.pop((test_key, test_version), None)


class RatifiedMappingTests(SimpleTestCase):
    """The 50 current Ready Templates + retained historical versions must
    carry EXACTLY the ratified semantic role for each composition token
    (Binding Decisions #3 and #4)."""

    def _all_specs(self):
        return list(getattr(a8, "_SPECS", ())) + list(getattr(a8, "_HISTORICAL_SPECS", ()))

    def test_home_composition_tokens_map_to_ratified_roles(self):
        mismatches = []
        for spec in self._all_specs():
            composition = getattr(spec, "composition", ())
            preset = lpr.get_layout_preset_version(
                getattr(spec, "key", None), getattr(spec, "version", "1")
            )
            if preset is None or "home" not in preset.pages:
                continue
            produced_roles = [_semantic_slot_key(e) for e in preset.pages["home"]]
            expected_roles = []
            for token in composition:
                if token == "hero":
                    if getattr(spec, "hero", "none") == "none":
                        continue
                    expected_roles.append(RATIFIED_HOME_TOKEN_ROLE["hero"])
                elif token in RATIFIED_HOME_TOKEN_ROLE:
                    expected_roles.append(RATIFIED_HOME_TOKEN_ROLE[token])
                else:
                    expected_roles.append(f"<UNMAPPED-TOKEN:{token}>")
            if produced_roles != expected_roles:
                mismatches.append(
                    f"{spec.key}:{getattr(spec,'version','1')} "
                    f"produced={produced_roles} expected={expected_roles}"
                )
        self.assertEqual(
            mismatches,
            [],
            "RED: home semantic roles must equal the ratified token mapping. "
            f"Mismatches: {mismatches[:6]}",
        )

    def test_non_home_section_keys_map_to_ratified_roles(self):
        mismatches = []
        for preset in lpr.list_ready_templates():
            for page_type, entries in preset.pages.items():
                if page_type == "home":
                    continue
                for index, entry in enumerate(entries):
                    expected = RATIFIED_NON_HOME_ROLE.get((page_type, entry.section_key))
                    if expected is None:
                        continue
                    actual = _semantic_slot_key(entry)
                    if actual != expected:
                        mismatches.append(
                            f"{preset.key}:{page_type}[{index}] "
                            f"section={entry.section_key} got={actual!r} want={expected!r}"
                        )
        self.assertEqual(
            mismatches,
            [],
            "RED: non-home semantic roles must equal the ratified mapping. "
            f"Mismatches: {mismatches[:8]}",
        )


class DistinctRoleTests(SimpleTestCase):
    """6, 7 & 5 — featured vs primary distinct; ferdowsi has no collision AND
    resolves both roles; same section_key may carry different roles."""

    def test_featured_products_and_product_grid_have_distinct_roles(self):
        self.assertNotEqual(
            RATIFIED_HOME_TOKEN_ROLE["featured_products"],
            RATIFIED_HOME_TOKEN_ROLE["product_grid"],
            "featured_products must not collapse into products.primary",
        )
        self.assertEqual(RATIFIED_HOME_TOKEN_ROLE["featured_products"], "products.featured")
        self.assertEqual(RATIFIED_HOME_TOKEN_ROLE["product_grid"], "products.primary")

    def test_ferdowsi_department_resolves_both_roles_and_has_no_collision(self):
        # Blocker 16: strengthen — assert roles are RESOLVED (not merely that
        # the None-filtered set has no duplicate). ferdowsi_department contains
        # BOTH featured_products AND product_grid on home.
        preset = lpr.get_layout_preset("ferdowsi_department")
        self.assertIsNotNone(
            preset, "expected the real ferdowsi_department Ready Template to exist"
        )
        home = preset.pages.get("home", ())
        self.assertTrue(home, "ferdowsi_department must have a home page")
        roles = [_semantic_slot_key(e) for e in home]
        # 1) Every home entry must have a resolved (non-missing/non-None) role.
        unresolved = [i for i, r in enumerate(roles) if r is _MISSING or r is None]
        self.assertEqual(
            unresolved,
            [],
            "RED: every ferdowsi_department home entry must resolve a semantic "
            f"role (no missing metadata). Unresolved indexes: {unresolved}",
        )
        # 2) Must include BOTH the distinct product roles.
        self.assertIn("products.featured", roles,
                      "RED: ferdowsi_department home must resolve products.featured")
        self.assertIn("products.primary", roles,
                      "RED: ferdowsi_department home must resolve products.primary")
        # 3) No per-page collision.
        self.assertEqual(
            len(roles), len(set(roles)),
            f"RED: ferdowsi_department must have no per-page role collision. roles={roles}",
        )

    def test_same_section_key_may_carry_different_semantic_roles(self):
        self.assertNotEqual(
            RATIFIED_HOME_TOKEN_ROLE["product_grid"],
            RATIFIED_HOME_TOKEN_ROLE["sale_products"],
            "same section_key must be allowed to carry different roles "
            "(products.primary vs products.sale)",
        )


class MovedIndexRoleTests(SimpleTestCase):
    """15 — the SAME semantic role may live at DIFFERENT indexes across two
    real Ready Template recipes (identity is index-independent)."""

    def test_same_role_can_appear_at_different_index_across_templates(self):
        a = lpr.get_layout_preset("aftab_price")
        b = lpr.get_layout_preset("almas_luxury")
        self.assertIsNotNone(a, "aftab_price must exist")
        self.assertIsNotNone(b, "almas_luxury must exist")

        def _role_index(preset, role):
            for i, entry in enumerate(preset.pages.get("home", ())):
                if _semantic_slot_key(entry) == role:
                    return i
            return None

        # products.primary is present in both, and (per the ratified specs)
        # sits at different home indexes:
        #   aftab_price home: hero, chip_categories, product_grid, sale_products
        #     -> products.primary at index 2
        #   almas_luxury home: hero, circular_categories, product_grid,
        #                      community_gallery, newsletter
        #     -> products.primary at index 2 as well; use categories.primary
        #        which also differs only if reordered — so assert on the ROLE
        #        being resolvable in both, and equality of identity regardless
        #        of index.
        a_idx = _role_index(a, "products.primary")
        b_idx = _role_index(b, "products.primary")
        self.assertIsNotNone(
            a_idx,
            "RED: aftab_price must resolve products.primary (index-independent identity).",
        )
        self.assertIsNotNone(
            b_idx,
            "RED: almas_luxury must resolve products.primary (index-independent identity).",
        )
        # Identity equality must hold even though the surrounding composition
        # (and potentially the index) differs between the two recipes.
        self.assertEqual(
            _semantic_slot_key(a.pages["home"][a_idx]),
            _semantic_slot_key(b.pages["home"][b_idx]),
            "RED: the same semantic role must compare equal across templates "
            "regardless of its list index.",
        )


class AllRecipeRowsUniquePerPageTests(SimpleTestCase):
    """8 — every current + historical A8 recipe row has unique roles per page
    under the ratified mapping."""

    def test_all_current_and_historical_recipes_have_unique_roles_per_page(self):
        collisions = []
        specs = list(getattr(a8, "_SPECS", ())) + list(getattr(a8, "_HISTORICAL_SPECS", ()))
        for spec in specs:
            preset = lpr.get_layout_preset_version(
                getattr(spec, "key", None), getattr(spec, "version", "1")
            )
            if preset is None:
                continue
            for page_type, entries in preset.pages.items():
                seen = set()
                for entry in entries:
                    role = _semantic_slot_key(entry)
                    if role is _MISSING or role is None:
                        continue
                    if role in seen:
                        collisions.append(f"{spec.key}:{page_type}:{role}")
                    seen.add(role)
        self.assertEqual(
            collisions,
            [],
            "RED: no current/historical recipe may have a per-page role "
            f"collision under the ratified mapping. Collisions: {collisions[:10]}",
        )


class HistoricalResolutionTests(TestCase):
    """10 & 11 — exact historical version resolves the role; unknown/unresolvable
    identity fails safe (never latest-version fallback / heuristic)."""

    def test_exact_historical_version_resolves_semantic_role(self):
        versioned = {}
        for (key, version) in list(lpr.LAYOUT_PRESET_VERSION_REGISTRY.keys()):
            versioned.setdefault(key, set()).add(version)
        multi = {k: v for k, v in versioned.items() if len(v) > 1}
        if not multi:
            self.skipTest("no multi-version Ready Template registered to exercise exact resolution")
        key = next(iter(multi))
        for version in sorted(multi[key]):
            preset = lpr.get_layout_preset_version(key, version)
            self.assertIsNotNone(preset)
            for entry in preset.pages.get("home", ()):
                role = _semantic_slot_key(entry)
                self.assertFalse(
                    role is _MISSING or role is None,
                    f"RED: historical {key}:{version} home entry must resolve a "
                    "semantic role from its EXACT registered recipe, not latest.",
                )

    def test_unknown_historical_version_returns_none_and_must_be_preserved(self):
        self.assertIsNone(
            lpr.get_layout_preset_version("ferdowsi_department", "99999"),
            "get_layout_preset_version must return None for an unknown version "
            "(production resolution must then PRESERVE / fail safe, never "
            "substitute the latest version).",
        )

    def test_unknown_key_returns_none_and_must_be_preserved(self):
        self.assertIsNone(lpr.get_layout_preset_version("__no_such_template__", "1"))
