"""RastiSi Design Studio — transient Design Lab operations required by the
approved Studio UX (RastiSi_Design_Studio.html).

Three pure, read-only transforms of the EXISTING transient
``DesignLabCandidate`` exposed as actions on the EXISTING Design Lab endpoint:

* ``set_theme``              — temporary occasion Theme inside the experiment;
* ``reset_to_base``          — «برگشت به شروع»: Candidate -> fixed experiment
                               Base, locks cleared, same Base/draft/revision;
* ``return_to_template_dna`` — «بازگشت به سبک اولیه»: design families -> the
                               exact current Ready Template's canonical DNA,
                               Theme preserved, Base/binding unchanged.

None of them may write the Draft, history, revision or Published state. The
only persistence boundary stays ``design_lab.apply_candidate``.
"""

import json

from django.urls import reverse

from apps.storefront_builder import layout_preset_registry, theme_catalog
from apps.storefront_builder.services import design_lab_service
from apps.storefront_builder.storefront_appearance.persistence import (
    load_store_appearance_manifest,
)

from .test_w3_design_lab import (
    EXPECTED_RANDOMIZABLE,
    DesignLabBaseTestCase,
    _draft_persistent_fingerprint,
)


def _occasion_key(index=0):
    """A real (non-no-op) occasion Theme component key from the canonical catalog."""
    keys = [
        o.component_key
        for o in theme_catalog.list_theme_occasions()
        if o.component_key != design_lab_service.THEME_NONE_COMPONENT_KEY
    ]
    return keys[index]


class _LabEndpointMixin:
    def _lab(self, action, **extra):
        body = {"action": action}
        body.update(extra)
        return self.client.post(
            reverse("dashboard:storefront-builder-r4-design-lab"),
            data=json.dumps(body),
            content_type="application/json",
        )

    def _mix(self, token=None, locked=None):
        extra = {"locked_families": locked or []}
        if token:
            extra["candidate_token"] = token
        resp = self._lab("random_mix", **extra)
        self.assertEqual(resp.status_code, 200, resp.content)
        return resp.json()

    def _decode(self, token):
        return design_lab_service.decode_candidate_token(token)

    def _mutate(self, mutation, base_revision=None):
        self.draft.refresh_from_db()
        if base_revision is None:
            base_revision = self.draft.edit_revision
        return self.client.post(
            reverse("dashboard:storefront-builder-r4-mutation"),
            data=json.dumps({
                "base_revision": base_revision,
                "mutation": {"draft_id": self.draft.pk, **mutation},
            }),
            content_type="application/json",
        )

    def _apply(self, token):
        payload = self._lab("apply_payload", candidate_token=token)
        self.assertEqual(payload.status_code, 200, payload.content)
        return self._mutate(payload.json()["mutation"])


# ===========================================================================
# set_theme
# ===========================================================================
class DesignLabSetThemeTests(_LabEndpointMixin, DesignLabBaseTestCase):
    def _mixed_locked(self):
        first = self._mix(locked=["card"])
        return first["token"], self._decode(first["token"])

    def test_set_theme_changes_candidate_theme_only(self):
        token, before = self._mixed_locked()
        key = _occasion_key()
        resp = self._lab(
            "set_theme", candidate_token=token, theme_component_key=key, intensity="strong"
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        after = self._decode(resp.json()["token"])
        self.assertEqual(after.candidate_selections["theme"], key)
        self.assertEqual(after.candidate_settings["theme"]["intensity"], "strong")
        # Every non-theme candidate selection is untouched (incl. the 7 families).
        for family, value in before.candidate_selections.items():
            if family != "theme":
                self.assertEqual(after.candidate_selections[family], value, family)
        for family in EXPECTED_RANDOMIZABLE:
            self.assertEqual(
                after.candidate_selections[family], before.candidate_selections[family]
            )
        # Non-theme settings untouched.
        before_other = {k: v for k, v in before.candidate_settings.items() if k != "theme"}
        after_other = {k: v for k, v in after.candidate_settings.items() if k != "theme"}
        self.assertEqual(after_other, before_other)

    def test_set_theme_preserves_base_locks_seed_and_binding(self):
        token, before = self._mixed_locked()
        resp = self._lab(
            "set_theme", candidate_token=token,
            theme_component_key=_occasion_key(), intensity="balanced",
        )
        after = self._decode(resp.json()["token"])
        self.assertEqual(after.base_selections, before.base_selections)
        self.assertEqual(after.base_settings, before.base_settings)
        self.assertEqual(after.locked_families, before.locked_families)
        self.assertEqual(after.seed, before.seed)
        self.assertEqual(after.draft_id, before.draft_id)
        self.assertEqual(after.base_revision, before.base_revision)

    def test_set_theme_writes_nothing(self):
        token, _ = self._mixed_locked()
        before = _draft_persistent_fingerprint(self.draft)
        resp = self._lab(
            "set_theme", candidate_token=token,
            theme_component_key=_occasion_key(), intensity="subtle",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(_draft_persistent_fingerprint(self.draft), before)

    def test_invalid_theme_component_is_rejected(self):
        token, _ = self._mixed_locked()
        for bad in ("theme.not_a_real_occasion.v1", "header.editorial.v1", "", None, 7):
            resp = self._lab(
                "set_theme", candidate_token=token, theme_component_key=bad, intensity="balanced"
            )
            self.assertEqual(resp.status_code, 400, (bad, resp.content))
            self.assertIs(resp.json()["ok"], False)
        # A non-theme family's real component key is also rejected.
        header_key = self._decode(token).candidate_selections["header"]
        resp = self._lab(
            "set_theme", candidate_token=token, theme_component_key=header_key, intensity="balanced"
        )
        self.assertEqual(resp.status_code, 400, resp.content)

    def test_invalid_intensity_is_rejected(self):
        token, _ = self._mixed_locked()
        for bad in ("extreme", "", None, 3):
            resp = self._lab(
                "set_theme", candidate_token=token,
                theme_component_key=_occasion_key(), intensity=bad,
            )
            self.assertEqual(resp.status_code, 400, (bad, resp.content))

    def test_invalid_token_is_rejected(self):
        resp = self._lab(
            "set_theme", candidate_token="tampered.token",
            theme_component_key=_occasion_key(), intensity="balanced",
        )
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertEqual(resp.json()["code"], "invalid_candidate")

    def test_none_theme_behaves_like_remove_theme(self):
        token, _ = self._mixed_locked()
        with_theme = self._lab(
            "set_theme", candidate_token=token,
            theme_component_key=_occasion_key(), intensity="strong",
        ).json()["token"]
        resp = self._lab(
            "set_theme", candidate_token=with_theme,
            theme_component_key=design_lab_service.THEME_NONE_COMPONENT_KEY, intensity="balanced",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        after = self._decode(resp.json()["token"])
        self.assertEqual(after.candidate_selections["theme"], design_lab_service.THEME_NONE_COMPONENT_KEY)
        self.assertNotIn("theme", after.candidate_settings)

    def test_remove_theme_still_works(self):
        token, _ = self._mixed_locked()
        with_theme = self._lab(
            "set_theme", candidate_token=token,
            theme_component_key=_occasion_key(), intensity="strong",
        ).json()["token"]
        resp = self._lab("remove_theme", candidate_token=with_theme)
        self.assertEqual(resp.status_code, 200, resp.content)
        after = self._decode(resp.json()["token"])
        self.assertEqual(after.candidate_selections["theme"], design_lab_service.THEME_NONE_COMPONENT_KEY)

    def test_random_mix_after_set_theme_preserves_theme(self):
        token, _ = self._mixed_locked()
        key = _occasion_key()
        themed = self._lab(
            "set_theme", candidate_token=token, theme_component_key=key, intensity="strong",
        ).json()["token"]
        for _ in range(3):
            themed = self._mix(token=themed)["token"]
            cand = self._decode(themed)
            self.assertEqual(cand.candidate_selections["theme"], key)
            self.assertEqual(cand.candidate_settings["theme"]["intensity"], "strong")

    def test_apply_persists_candidate_theme_through_apply_candidate_only(self):
        token, _ = self._mixed_locked()
        key = _occasion_key()
        themed = self._lab(
            "set_theme", candidate_token=token, theme_component_key=key, intensity="strong",
        ).json()["token"]
        self.draft.refresh_from_db()
        history_before = self.draft.edit_history_entries.count()
        rev_before = self.draft.edit_revision
        resp = self._apply(themed)
        self.assertEqual(resp.status_code, 200, resp.content)
        self.draft.refresh_from_db()
        manifest = load_store_appearance_manifest(self.draft)
        self.assertEqual(manifest.selections["theme"], key)
        self.assertEqual(dict(manifest.settings)["theme"]["intensity"], "strong")
        self.assertEqual(self.draft.edit_revision, rev_before + 1)
        self.assertEqual(self.draft.edit_history_entries.count(), history_before + 1)

    def test_stale_candidate_cannot_apply_theme_over_newer_draft_work(self):
        token, _ = self._mixed_locked()
        themed = self._lab(
            "set_theme", candidate_token=token,
            theme_component_key=_occasion_key(), intensity="strong",
        ).json()["token"]
        # Newer Draft work lands elsewhere (another theme write through the
        # canonical mutation boundary).
        other = self._mutate({"type": "theme.apply", "component_key": _occasion_key(1), "intensity": "subtle"})
        self.assertEqual(other.status_code, 200, other.content)
        self.draft.refresh_from_db()
        newer = manifest_after = load_store_appearance_manifest(self.draft).selections["theme"]
        preflight = self._lab("apply_payload", candidate_token=themed)
        self.assertEqual(preflight.status_code, 409, preflight.content)
        self.assertEqual(preflight.json()["code"], "stale_candidate")
        # Even if the stale signed mutation is forced through the canonical
        # boundary with the current revision, it is rejected there too.
        forced = design_lab_service.candidate_apply_mutation(self._decode(themed), draft_id=self.draft.pk)
        resp = self._mutate(forced)
        self.assertEqual(resp.status_code, 409, resp.content)
        self.draft.refresh_from_db()
        self.assertEqual(load_store_appearance_manifest(self.draft).selections["theme"], newer)
        del manifest_after


# ===========================================================================
# reset_to_base («برگشت به شروع»)
# ===========================================================================
class DesignLabResetToBaseTests(_LabEndpointMixin, DesignLabBaseTestCase):
    def test_reset_to_base_restores_base_clears_locks_keeps_binding(self):
        first = self._mix(locked=["card", "header"])
        themed = self._lab(
            "set_theme", candidate_token=first["token"],
            theme_component_key=_occasion_key(), intensity="strong",
        ).json()["token"]
        before = self._decode(themed)
        resp = self._lab("reset_to_base", candidate_token=themed)
        self.assertEqual(resp.status_code, 200, resp.content)
        after = self._decode(resp.json()["token"])
        self.assertEqual(dict(after.candidate_selections), dict(before.base_selections))
        self.assertEqual(after.candidate_settings, before.base_settings)
        # The experiment Base Theme is restored (candidate theme dropped).
        self.assertEqual(after.candidate_selections["theme"], before.base_selections["theme"])
        self.assertEqual(after.locked_families, frozenset())
        self.assertEqual(resp.json()["locked_families"], [])
        self.assertEqual(after.base_selections, before.base_selections)
        self.assertEqual(after.base_settings, before.base_settings)
        self.assertEqual(after.draft_id, before.draft_id)
        self.assertEqual(after.base_revision, before.base_revision)
        self.assertEqual(resp.json()["diffs"], [])

    def test_reset_to_base_never_rebases_onto_newer_draft(self):
        first = self._mix()
        original = self._decode(first["token"])
        # The Draft changes elsewhere while the experiment is open.
        other = self._mutate({"type": "theme.apply", "component_key": _occasion_key(), "intensity": "subtle"})
        self.assertEqual(other.status_code, 200, other.content)
        resp = self._lab("reset_to_base", candidate_token=first["token"])
        self.assertEqual(resp.status_code, 200, resp.content)
        after = self._decode(resp.json()["token"])
        # Same (old) Base and binding — the experiment stays stale.
        self.assertEqual(after.base_selections, original.base_selections)
        self.assertEqual(after.base_revision, original.base_revision)
        self.draft.refresh_from_db()
        self.assertNotEqual(after.base_revision, self.draft.edit_revision)
        self.assertTrue(design_lab_service.candidate_is_stale(self.draft, after))

    def test_reset_to_base_writes_nothing(self):
        first = self._mix(locked=["badge"])
        before = _draft_persistent_fingerprint(self.draft)
        resp = self._lab("reset_to_base", candidate_token=first["token"])
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(_draft_persistent_fingerprint(self.draft), before)

    def test_reset_to_base_requires_a_candidate(self):
        resp = self._lab("reset_to_base")
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertEqual(resp.json()["code"], "no_candidate")

    def test_legacy_reset_action_still_starts_fresh_from_current_draft(self):
        first = self._mix(locked=["card"])
        resp = self._lab("reset", candidate_token=first["token"])
        self.assertEqual(resp.status_code, 200, resp.content)
        self.draft.refresh_from_db()
        self.assertEqual(resp.json()["base_revision"], self.draft.edit_revision)


# ===========================================================================
# return_to_template_dna («بازگشت به سبک اولیه»)
# ===========================================================================
class DesignLabReturnToTemplateDnaTests(_LabEndpointMixin, DesignLabBaseTestCase):
    def _template_selections(self):
        prov = self.draft.template_provenance["template"]
        preset = layout_preset_registry.get_layout_preset_version(prov["key"], prov["version"])
        return dict(preset.store_appearance["selections"])

    def test_restores_design_families_to_exact_template_dna_and_keeps_theme(self):
        mixed = self._mix(locked=["card", "hero"])["token"]
        key = _occasion_key()
        themed = self._lab(
            "set_theme", candidate_token=mixed, theme_component_key=key, intensity="strong",
        ).json()["token"]
        before = self._decode(themed)
        resp = self._lab("return_to_template_dna", candidate_token=themed)
        self.assertEqual(resp.status_code, 200, resp.content)
        after = self._decode(resp.json()["token"])
        tpl = self._template_selections()
        for family in EXPECTED_RANDOMIZABLE:
            if family in tpl:
                # Independent of locks: locked families are restored too.
                self.assertEqual(after.candidate_selections[family], tpl[family], family)
        # Current candidate Theme preserved.
        self.assertEqual(after.candidate_selections["theme"], key)
        self.assertEqual(after.candidate_settings["theme"]["intensity"], "strong")
        # Page composition family untouched.
        self.assertEqual(after.candidate_selections.get("layout"), before.candidate_selections.get("layout"))
        # Base + binding unchanged.
        self.assertEqual(after.base_selections, before.base_selections)
        self.assertEqual(after.base_settings, before.base_settings)
        self.assertEqual(after.draft_id, before.draft_id)
        self.assertEqual(after.base_revision, before.base_revision)

    def test_return_to_template_dna_writes_nothing(self):
        mixed = self._mix()["token"]
        before = _draft_persistent_fingerprint(self.draft)
        resp = self._lab("return_to_template_dna", candidate_token=mixed)
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(_draft_persistent_fingerprint(self.draft), before)

    def test_differs_from_reset_to_base_when_base_diverged_from_template(self):
        # Merchant already customised a design family away from the template
        # DNA before opening the Lab -> Base != template DNA.
        tpl = self._template_selections()
        from apps.storefront_builder.storefront_appearance.registry import list_components

        alt = next(
            c.key for c in list_components()
            if c.family_key == "header" and c.key != tpl.get("header")
        )
        resp = self._mutate({"type": "appearance.component.update", "family": "header", "component_key": alt})
        if resp.status_code != 200:
            self.skipTest(f"canonical header selection mutation unavailable: {resp.content!r}")
        mixed = self._mix()["token"]
        to_base = self._decode(self._lab("reset_to_base", candidate_token=mixed).json()["token"])
        to_dna = self._decode(self._lab("return_to_template_dna", candidate_token=mixed).json()["token"])
        self.assertEqual(to_base.candidate_selections["header"], alt)
        self.assertEqual(to_dna.candidate_selections["header"], tpl["header"])

    def test_fails_closed_when_exact_template_version_is_unresolvable(self):
        mixed = self._mix()["token"]
        prov = dict(self.draft.template_provenance)
        tpl = dict(prov["template"])
        tpl["version"] = "999999"
        prov["template"] = tpl
        type(self.draft).objects.filter(pk=self.draft.pk).update(template_provenance=prov)
        resp = self._lab("return_to_template_dna", candidate_token=mixed)
        self.assertEqual(resp.status_code, 409, resp.content)
        self.assertEqual(resp.json()["code"], "template_dna_unavailable")

    def test_fails_closed_without_template_provenance(self):
        mixed = self._mix()["token"]
        type(self.draft).objects.filter(pk=self.draft.pk).update(template_provenance={})
        resp = self._lab("return_to_template_dna", candidate_token=mixed)
        self.assertEqual(resp.status_code, 409, resp.content)
        self.assertEqual(resp.json()["code"], "template_dna_unavailable")

    def test_requires_a_candidate(self):
        resp = self._lab("return_to_template_dna")
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertEqual(resp.json()["code"], "no_candidate")


# ===========================================================================
# Whole-experiment guard: every Studio Lab operation before Apply
# ===========================================================================
class DesignLabFullChainWritesNothingTests(_LabEndpointMixin, DesignLabBaseTestCase):
    def test_every_lab_operation_before_apply_writes_nothing(self):
        before = _draft_persistent_fingerprint(self.draft)
        key = _occasion_key()

        start = self._lab("reset")
        self.assertEqual(start.status_code, 200, start.content)
        token = start.json()["token"]
        base = self._decode(token)

        token = self._mix(token=token, locked=["card"])["token"]
        resp = self._lab("randomize_one", candidate_token=token, family="hero", locked_families=["card"])
        self.assertEqual(resp.status_code, 200, resp.content)
        token = resp.json()["token"]
        for action, extra in (
            ("compare", {}),
            ("set_theme", {"theme_component_key": key, "intensity": "strong"}),
            ("random_mix", {"locked_families": ["card"]}),
            ("randomize_one", {"family": "footer"}),
            ("remove_theme", {}),
            ("set_theme", {"theme_component_key": key, "intensity": "subtle"}),
            ("return_to_template_dna", {}),
            ("reset_to_base", {}),
        ):
            resp = self._lab(action, candidate_token=token, **extra)
            self.assertEqual(resp.status_code, 200, (action, resp.content))
            token = resp.json()["token"]
            candidate = self._decode(token)
            # The experiment stays bound to the same fixed Base and Draft.
            self.assertEqual(candidate.base_selections, base.base_selections, action)
            self.assertEqual(candidate.base_revision, base.base_revision, action)
            self.assertEqual(candidate.draft_id, base.draft_id, action)

        payload = self._lab("apply_payload", candidate_token=token)
        self.assertEqual(payload.status_code, 200, payload.content)

        self.assertEqual(_draft_persistent_fingerprint(self.draft), before)

    def test_random_mix_and_randomize_one_never_change_the_candidate_theme(self):
        key = _occasion_key()
        token = self._mix()["token"]
        token = self._lab(
            "set_theme", candidate_token=token, theme_component_key=key, intensity="strong",
        ).json()["token"]
        for family in EXPECTED_RANDOMIZABLE:
            token = self._lab("randomize_one", candidate_token=token, family=family).json()["token"]
            token = self._mix(token=token)["token"]
            candidate = self._decode(token)
            self.assertEqual(candidate.candidate_selections["theme"], key, family)
            self.assertEqual(candidate.candidate_settings["theme"]["intensity"], "strong", family)
