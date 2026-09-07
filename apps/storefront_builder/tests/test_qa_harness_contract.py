from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from apps.storefront_builder import section_registry
from apps.storefront_builder.models import StorefrontPage


class StorefrontBuilderQAHarnessContractTests(SimpleTestCase):
    def test_every_registry_definition_is_either_hidden_or_in_a_page_library(self):
        library_keys = set()
        for page_type, _label in StorefrontPage.PageType.choices:
            for _category, definitions in section_registry.list_library_groups(page_type=page_type):
                library_keys.update(definition.key for definition in definitions)

        definitions = section_registry.list_definitions()
        self.assertGreaterEqual(len(definitions), 34)
        missing = [
            definition.key
            for definition in definitions
            if not definition.hidden_from_library and definition.key not in library_keys
        ]
        self.assertEqual(missing, [])

    def test_browser_runner_covers_actions_layout_errors_and_destructive_controls(self):
        runner = Path(settings.BASE_DIR) / "tools" / "storefront_builder_qa" / "run.mjs"
        package = runner.with_name("package.json")
        self.assertTrue(runner.exists())
        self.assertTrue(package.exists())
        source = runner.read_text(encoding="utf-8")
        for marker in (
            "registry:all-definitions-covered",
            "duplicate-capability",
            "hide-and-undo",
            "lock-unlock-and-command-disable",
            "move-up-and-undo",
            "remove-and-undo",
            "settings-save-noop",
            "internal-links-stay-in-builder",
            "library:drag-drop-onto-canvas",
            "quarter_left",
            "quarter_right",
            "keyboard:undo-redo-shortcuts",
            "browser:console-errors",
            "browser:request-failures",
            "topbar:publish-button-real-submit",
            "library:discard-draft-real-submit",
        ):
            self.assertIn(marker, source)

    def test_r4_runner_and_command_support_phase3_viewports(self):
        """Phase 3 harness additions are opt-in and additive: the R4 runner
        references the three Phase 3 viewport dimensions and the ``phase3``
        manifest field, and the R4 QA command wires a ``--phase3`` flag through
        into the manifest. The default (non-phase3) behavior is unchanged."""
        base = Path(settings.BASE_DIR)
        runner = base / "tools" / "storefront_builder_r4_qa" / "run.mjs"
        command = (
            base / "apps" / "storefront_builder" / "management"
            / "commands" / "qa_storefront_builder_r4.py"
        )
        self.assertTrue(runner.exists())
        self.assertTrue(command.exists())

        runner_source = runner.read_text(encoding="utf-8")
        # The three Phase 3 viewport dimensions the runner iterates.
        for dimension in ("1440", "900", "390", "844", "768", "1024"):
            self.assertIn(dimension, runner_source)
        # The runner keys its opt-in responsive capture off the manifest flag.
        self.assertIn("manifest.phase3", runner_source)

        command_source = command.read_text(encoding="utf-8")
        # The command exposes the opt-in flag and threads it into the manifest.
        self.assertIn("--phase3", command_source)
        self.assertIn('"phase3"', command_source)

    def test_r4_runner_and_command_support_task7_matrix_additions(self):
        """Task 7 harness additions are opt-in (phase3-only) and additive:
        computed layout/RTL/keyboard-focus/native-scroll assertions, the
        combined dual-pilot Cart proof, the E6 index companion smoke, the
        disposable broken-image fixtures (Brand + Collection), and the
        tenant/unauthorized Preview negative — without a second harness,
        command, package or endpoint."""
        base = Path(settings.BASE_DIR)
        runner = base / "tools" / "storefront_builder_r4_qa" / "run.mjs"
        command = (
            base / "apps" / "storefront_builder" / "management"
            / "commands" / "qa_storefront_builder_r4.py"
        )
        runner_source = runner.read_text(encoding="utf-8")
        for marker in (
            "phase3CombinedCartHtmx",
            "phase3CollectionIndexCompanion",
            "phase3BrandBrokenImage",
            "qa-broken-nonexistent",
            "document.documentElement.dir",
            "scrollLeft",
            "activeElement",
            "gridTemplateColumns",
            "objectFit",
        ):
            self.assertIn(marker, runner_source)

        command_source = command.read_text(encoding="utf-8")
        for marker in (
            "_phase3_tenant_negatives",
            "broken_image_brand_id",
            "broken_collection_slug",
            "tenant_negatives.json",
        ):
            self.assertIn(marker, command_source)
