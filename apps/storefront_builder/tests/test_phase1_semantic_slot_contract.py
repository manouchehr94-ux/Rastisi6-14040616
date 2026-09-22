"""Phase-1 RED tests — CROSS-TEMPLATE SEMANTIC SLOT IDENTITY CONTRACT.

Architecture Convergence / Phase 1 — Safe Ready Template Switching /
Merchant Preservation.

These are RED tests. They encode the *ratified* semantic-slot contract that
production code does NOT yet implement:

  * ``PresetSectionEntry`` will gain ``semantic_slot_key: str | None = None``
    (recipe metadata only — NO new DB field/model/migration/registry).
  * Every Ready Template ``PresetSectionEntry`` must carry an explicit,
    non-empty, syntactically-valid ``semantic_slot_key``.
  * Identity is NOT positional (not derived from list index).
  * A semantic role must be unique within one Ready Template page.
  * The SAME role may sit at DIFFERENT indexes across templates.
  * The SAME ``section_key`` may carry DIFFERENT semantic roles.
  * Non-Ready structural presets may keep ``semantic_slot_key=None``.
  * Historical identity resolves ONLY through the exact registered version
    via ``get_layout_preset_version(key, version)`` — never latest-version
    fallback, never heuristic; unresolved => fail safe / preserve.

Per the round rules, this module MUST import cleanly even though
``semantic_slot_key`` does not exist yet. Every assertion that depends on
the missing field is written so the *test* fails with a descriptive message
(via ``_semantic_slot_key`` introspection returning a sentinel), never an
ImportError / AttributeError at collection time.

The ratified A8 composition-token -> semantic-role mapping is the single
operational authority reproduced here as EXPECTED test data (this is test
data, not a second production catalog).
"""

from django.test import SimpleTestCase, TestCase

from apps.storefront_builder import a8_ready_templates as a8
from apps.storefront_builder import layout_preset_registry as lpr


# --- Ratified mapping (EXPECTED data for the tests — NOT a production catalog) ---

# Home-page composition token -> semantic role (Binding Decision #3).
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

# Non-home ratified roles keyed by (page_type, section_key) (Binding Decision #4).
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
    """Yield ``(page_type, index, entry)`` for every section entry of a preset."""
    for page_type, entries in definition.pages.items():
        for index, entry in enumerate(entries):
            yield page_type, index, entry


class SemanticSlotFieldExistenceTests(SimpleTestCase):
    """1 & 9 — the field must exist on the canonical recipe contract, and
    Ready Templates must populate it (non-Ready may omit)."""

    def test_preset_section_entry_declares_semantic_slot_key_field(self):
        import dataclasses

        field_names = {f.name for f in dataclasses.fields(lpr.PresetSectionEntry)}
        self.assertIn(
            "semantic_slot_key",
            field_names,
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
        # A non-Ready preset (e.g. clean_minimal / v5_golden_homepage) is
        # ALLOWED to leave semantic_slot_key None. Once the field exists this
        # must not raise; today it proves the field is introspectable.
        non_ready = [p for p in lpr.list_layout_presets() if not p.is_ready_template]
        self.assertTrue(non_ready, "expected at least one non-Ready structural preset")
        for preset in non_ready:
            for _pt, _idx, entry in _iter_entries(preset):
                key = _semantic_slot_key(entry)
                # None (explicit omission) OR a valid string are both fine.
                self.assertTrue(
                    key is _MISSING or key is None or isinstance(key, str),
                    f"non-Ready preset {preset.key}: semantic_slot_key must be None or str",
                )


class SemanticSlotSyntaxTests(SimpleTestCase):
    """5 — normalized syntax; 2 — not positional."""

    def test_semantic_slot_key_uses_safe_normalized_syntax(self):
        import re

        # dotted lower snake segments, e.g. hero.primary / products.sale
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
        # A positional key would embed the list index. Prove the ratified key
        # never equals a position-derived string for the same entry.
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


class SemanticSlotUniquenessTests(SimpleTestCase):
    """3 — duplicate semantic role inside one Ready Template page is rejected."""

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
        # Constructing a Ready-Template-shaped definition with two entries
        # sharing a semantic role on one page must FAIL closed at import-time
        # validation. Until the contract exists, register_layout_preset will
        # not raise for this reason -> RED.
        import dataclasses

        field_names = {f.name for f in dataclasses.fields(lpr.PresetSectionEntry)}
        if "semantic_slot_key" not in field_names:
            self.fail(
                "RED: semantic_slot_key not implemented; registry cannot yet "
                "validate duplicate semantic roles per page."
            )
        # If/when implemented, this is the executable proof:
        entry_a = lpr.PresetSectionEntry("hero_banner", semantic_slot_key="hero.primary")
        entry_b = lpr.PresetSectionEntry("hero_banner", semantic_slot_key="hero.primary")
        bad = lpr.LayoutPresetDefinition(
            key="__red_dupe_role__",
            label_fa="x",
            description_fa="x",
            is_ready_template=True,
            store_appearance=None,
            pages={"home": (entry_a, entry_b)},
        )
        with self.assertRaises(lpr.InvalidLayoutPresetError):
            lpr.register_layout_preset(bad)


class RatifiedMappingTests(SimpleTestCase):
    """The 50 current Ready Templates + retained historical versions must
    carry EXACTLY the ratified semantic role for each composition token.

    This is the operational authority for existing recipes (Binding
    Decisions #3 and #4)."""

    def _all_specs(self):
        specs = list(getattr(a8, "_SPECS", ()))
        specs += list(getattr(a8, "_HISTORICAL_SPECS", ()))
        return specs

    def test_home_composition_tokens_map_to_ratified_roles(self):
        # For every current+historical recipe, the built home entries must be
        # tagged with the ratified role derived from each composition token.
        mismatches = []
        for spec in self._all_specs():
            composition = getattr(spec, "composition", ())
            # Rebuild the same home entries the recipe produces, in order.
            preset = lpr.get_layout_preset_version(
                getattr(spec, "key", None), getattr(spec, "version", "1")
            )
            if preset is None or "home" not in preset.pages:
                continue
            home_entries = preset.pages["home"]
            # Walk tokens that actually produce an entry (hero==none produces
            # nothing) and line them up with the produced entries in order.
            produced_roles = [
                _semantic_slot_key(e) for e in home_entries
            ]
            expected_roles = []
            for token in composition:
                if token == "hero":
                    # hero token may be skipped when spec.hero == "none".
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
    """6, 7 & 5 — featured vs primary distinct; ferdowsi_department has no
    collision; same section_key may carry different roles."""

    def test_featured_products_and_product_grid_have_distinct_roles(self):
        self.assertNotEqual(
            RATIFIED_HOME_TOKEN_ROLE["featured_products"],
            RATIFIED_HOME_TOKEN_ROLE["product_grid"],
            "featured_products must not collapse into products.primary",
        )
        self.assertEqual(RATIFIED_HOME_TOKEN_ROLE["featured_products"], "products.featured")
        self.assertEqual(RATIFIED_HOME_TOKEN_ROLE["product_grid"], "products.primary")

    def test_ferdowsi_department_has_no_semantic_role_collision(self):
        preset = lpr.get_layout_preset("ferdowsi_department")
        self.assertIsNotNone(
            preset, "expected the real ferdowsi_department Ready Template to exist"
        )
        home = preset.pages.get("home", ())
        roles = [_semantic_slot_key(e) for e in home]
        resolved = [r for r in roles if r is not _MISSING and r is not None]
        self.assertEqual(
            len(resolved),
            len(set(resolved)),
            "RED: ferdowsi_department (contains BOTH featured_products AND "
            f"product_grid) must have no per-page role collision. roles={roles}",
        )

    def test_same_section_key_may_carry_different_semantic_roles(self):
        # product_section (via product_grid vs sale_products) is the same
        # section_key expressing two different business roles.
        self.assertNotEqual(
            RATIFIED_HOME_TOKEN_ROLE["product_grid"],
            RATIFIED_HOME_TOKEN_ROLE["sale_products"],
            "same section_key must be allowed to carry different roles "
            "(products.primary vs products.sale)",
        )


class AllRecipeRowsUniquePerPageTests(SimpleTestCase):
    """8 — every current + historical A8 recipe row has unique roles per page
    under the ratified mapping (the Architect verified all 74 rows)."""

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
        # Find any key that has more than one registered version.
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
            home = preset.pages.get("home", ())
            for entry in home:
                role = _semantic_slot_key(entry)
                self.assertFalse(
                    role is _MISSING or role is None,
                    f"RED: historical {key}:{version} home entry must resolve a "
                    "semantic role from its EXACT registered recipe, not latest.",
                )

    def test_unknown_historical_version_returns_none_and_must_be_preserved(self):
        # The exact-version registry must not silently fall back to latest.
        self.assertIsNone(
            lpr.get_layout_preset_version("ferdowsi_department", "99999"),
            "get_layout_preset_version must return None for an unknown version "
            "(production resolution must then PRESERVE / fail safe, never "
            "substitute the latest version).",
        )

    def test_unknown_key_returns_none_and_must_be_preserved(self):
        self.assertIsNone(lpr.get_layout_preset_version("__no_such_template__", "1"))
