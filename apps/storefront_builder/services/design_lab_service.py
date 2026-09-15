"""P5-W3 — Design Lab / Random Mix (transient experimentation surface).

**Central invariant: a Design Lab candidate is a transient experiment, never a
second source of truth.** Nothing in this module persists anything. It reads the
committed Draft's canonical Store-Appearance selections/settings, produces an
in-memory :class:`DesignLabCandidate`, resolves/compares/previews it through the
existing canonical primitives, and — only on an explicit merchant Apply —
serialises the candidate into the single canonical mutation
(``design_lab.apply_candidate``) dispatched by
``r4_mutation_service.apply_mutation``. There is no other write path here.

This module deliberately does NOT own (it reuses):

* the candidate resolver — ``preset_service.resolve_preset_candidate`` /
  ``rendering.resolve_store_appearance_manifest_state``;
* the appearance write authority — ``appearance_authority_service``;
* the Theme owner — ``appearance_authority_service.clear_theme`` (W2);
* the mutation boundary / stale / tenant / history — ``r4_mutation_service``;
* the Preview route / renderer — ``storefront_preview`` / ``render_service``;
* the component registry — ``storefront_appearance.registry`` / ``families``.

It adds exactly one new concept: the transient candidate. No model, no
migration, no registered preset, no DB row, no ``localStorage`` authority.
"""

from __future__ import annotations

import base64
import dataclasses
import json
import random
from collections.abc import Mapping

from ..layout_preset_registry import LayoutPresetDefinition
from ..storefront_appearance.families import COMPONENT_FAMILIES
from ..storefront_appearance.persistence import (
    load_store_appearance_manifest,
    manifest_to_primitive,
)
from ..storefront_appearance.registry import get_component, list_components
from ..storefront_appearance.rendering import (
    ResolvedStoreAppearance,
    resolve_store_appearance_manifest_state,
)


#: The appearance DNA families Random Mix is allowed to change. Chosen because
#: they (a) have real registry alternatives, (b) are visually meaningful storefront
#: chrome / section DNA, and (c) are never commerce truth. ``theme`` is
#: deliberately EXCLUDED — it is orthogonal and only ever changes when the
#: merchant explicitly randomizes it or explicitly Removes Theme (§9).
#: ``mega_menu`` (single option), ``layout`` (page composition) and ``motion``
#: (a subtle appearance token) are excluded so Random Mix changes visible chrome
#: without touching the merchant's page composition.
DESIGN_LAB_RANDOMIZABLE_FAMILIES: frozenset[str] = frozenset(
    {"header", "hero", "product_view", "card", "footer", "badge", "bottom_nav"}
)

#: The Theme no-op component key (owned by the W2 theme catalog).
THEME_NONE_COMPONENT_KEY = "theme.none.v1"

#: Wire mutation type for the ONE atomic Design Lab Apply.
DESIGN_LAB_APPLY_MUTATION_TYPE = "design_lab.apply_candidate"


@dataclasses.dataclass(frozen=True)
class DesignLabCandidate:
    """A transient, in-memory Design Lab experiment. NEVER persisted.

    * ``base_selections`` — the committed Draft's current family->component_key
      selections at generation time (the "Base" for Compare/Return).
    * ``candidate_selections`` — the experimental family->component_key mapping.
    * ``settings`` — per-family typed settings (e.g. ``{"theme": {"intensity": ...}}``).
    * ``locked_families`` — families the merchant locked (exploration lock only).
    * ``seed`` — the deterministic PRNG seed used to generate it (opaque to the
      merchant; used only for reproducibility/tests).
    """

    base_selections: Mapping[str, str]
    candidate_selections: Mapping[str, str]
    settings: Mapping
    locked_families: frozenset[str]
    seed: int | None = None

    def __post_init__(self) -> None:
        # Freeze the mutable inputs into immutable copies so the transient
        # candidate can never be mutated in place by a caller.
        object.__setattr__(self, "base_selections", dict(self.base_selections))
        object.__setattr__(
            self, "candidate_selections", dict(self.candidate_selections)
        )
        object.__setattr__(self, "settings", _deep_freeze_settings(self.settings))
        object.__setattr__(self, "locked_families", frozenset(self.locked_families))


def _deep_freeze_settings(settings: Mapping) -> dict:
    """Return a plain-dict deep copy of settings (JSON-shaped, bounded)."""
    return json.loads(json.dumps(dict(settings)))


def _base_state(draft) -> tuple[dict[str, str], dict]:
    """Read the committed Draft's canonical selections + settings.

    This is a pure read through the single canonical manifest loader — it does
    not write, and it is the authoritative "Base" every Design Lab operation
    starts from.
    """
    manifest = load_store_appearance_manifest(draft)
    primitive = manifest_to_primitive(manifest)
    return dict(primitive["selections"]), dict(primitive.get("settings", {}))


def _component_label(component_key: str) -> str:
    """Merchant-facing label for a component key (falls back to the key)."""
    component = get_component(component_key)
    if component is None:
        return component_key
    return component.label_fa or component_key


def _family_label(family_key: str) -> str:
    family = COMPONENT_FAMILIES.get(family_key)
    if family is None:
        return family_key
    return family.label_fa or family_key


# ---------------------------------------------------------------------------
# Pure Random-Mix generator (§8)
# ---------------------------------------------------------------------------
def generate_candidate(
    draft,
    *,
    randomize_families: set[str],
    locked_families: set[str],
    seed: int | None = None,
) -> DesignLabCandidate:
    """Produce a transient candidate from the committed Draft.

    Rules (§8): start from the Draft's canonical selections; only families in
    ``randomize_families`` may change; a family in ``locked_families`` never
    changes; options come only from the canonical registry (never fabricated);
    prefer a component different from the current one when alternatives exist;
    leaving a family unchanged is valid when it has no compatible alternative.
    Deterministic for a given (draft state, randomize set, locked set, seed).
    """
    base_selections, base_settings = _base_state(draft)
    locked = frozenset(locked_families)
    # A locked family is never randomized, even if also requested — lock wins.
    effective_randomize = (
        (set(randomize_families) & set(DESIGN_LAB_RANDOMIZABLE_FAMILIES)) - locked
    )

    rng = random.Random(seed)
    candidate_selections = dict(base_selections)

    # Deterministic family ordering so the PRNG draw sequence is stable.
    for family in sorted(effective_randomize):
        current = base_selections.get(family)
        # Deterministic option ordering from the canonical registry.
        options = [c.key for c in list_components(family)]
        # Prefer a different component so Randomize visibly does something (§8.10).
        alternatives = [key for key in options if key != current]
        if alternatives:
            candidate_selections[family] = rng.choice(alternatives)
        # else: no compatible alternative -> leave unchanged (§8.11).

    return DesignLabCandidate(
        base_selections=base_selections,
        candidate_selections=candidate_selections,
        settings=base_settings,
        locked_families=locked,
        seed=seed,
    )


# ---------------------------------------------------------------------------
# Candidate -> canonical preview preset (§10)
# ---------------------------------------------------------------------------
def _candidate_manifest_primitive(candidate: DesignLabCandidate) -> dict:
    """Build the complete typed manifest primitive from a candidate."""
    return {
        "schema_version": 1,
        "selections": dict(candidate.candidate_selections),
        "settings": _deep_freeze_settings(candidate.settings),
    }


def _draft_provenance_preset_key(draft) -> str:
    """The registered Ready-Template key the committed Draft is built from.

    ``preset_service.resolve_preset_candidate`` validates a candidate preset's
    ``key`` as a real ``layout_preset_key`` (it drives provenance, not DNA), so a
    transient candidate preset must carry a genuinely registered key. The DNA of
    a Design Lab candidate comes entirely from ``store_appearance``; the key is
    only provenance, so reusing the Draft's own current template key is correct
    (composition is preserved via empty ``pages``) and never fabricates a key.
    """
    from .. import variant_contract

    provenance = variant_contract.validate_template_provenance(
        draft.template_provenance
    )
    return provenance["template"]["key"]


def candidate_to_preset(draft, candidate: DesignLabCandidate) -> LayoutPresetDefinition:
    """Return a transient, in-memory, Store-agnostic ``LayoutPresetDefinition``
    whose ``store_appearance`` is the candidate's manifest.

    It preserves the Draft's current page composition (``pages`` is empty ->
    "leave every page untouched"), carries the Draft's own registered template
    key as provenance (so the canonical ``preset_service.resolve_preset_candidate``
    accepts it), and is NEVER registered and NEVER saved.
    """
    return LayoutPresetDefinition(
        key=_draft_provenance_preset_key(draft),
        label_fa="کاندید آزمایشگاه طراحی",
        description_fa="کاندید موقتِ آزمایشگاه طراحی — هرگز ذخیره نمی‌شود",
        store_appearance=_candidate_manifest_primitive(candidate),
        pages={},  # composition preserved: no page is replaced
    )


def resolve_candidate_appearance(
    draft, candidate: DesignLabCandidate
) -> ResolvedStoreAppearance:
    """Resolve the candidate manifest into ``ResolvedStoreAppearance`` through the
    exact same pure resolver the persisted path uses — no I/O, no persistence.

    Validates through the canonical contract: a fabricated/invalid component key
    raises ``InvalidStoreAppearanceContract`` (the same exception the persisted
    path raises for the same bad input).
    """
    from ..storefront_appearance.validation import validate_store_appearance_manifest

    validated = validate_store_appearance_manifest(
        _candidate_manifest_primitive(candidate), require_complete=True
    )
    version_id = draft.pk if getattr(draft, "pk", None) is not None else 0
    return resolve_store_appearance_manifest_state(
        validated.manifest, version_id=version_id
    )


# ---------------------------------------------------------------------------
# Compare with Base / Return to Original DNA / Reset / Remove Theme (§17-19, §9)
# ---------------------------------------------------------------------------
def compare_with_base(candidate: DesignLabCandidate) -> list[dict]:
    """Server-authoritative family-by-family diff between Base and candidate.

    Returns one entry per CHANGED family (selection or settings), each carrying
    merchant-facing Persian labels. Unchanged/locked families never appear.
    JavaScript may display this; it is never the source of truth (§17).
    """
    diffs: list[dict] = []
    families = list(COMPONENT_FAMILIES.keys())
    base_settings = dict(candidate.settings) if candidate.settings else {}
    for family in families:
        base_key = candidate.base_selections.get(family)
        cand_key = candidate.candidate_selections.get(family)
        if base_key == cand_key:
            continue
        if base_key is None and cand_key is None:
            continue
        diffs.append(
            {
                "family": family,
                "family_label": _family_label(family),
                "base_key": base_key,
                "candidate_key": cand_key,
                "base_label": _component_label(base_key) if base_key else "",
                "candidate_label": _component_label(cand_key) if cand_key else "",
            }
        )
    return diffs


def return_to_original_dna(draft, candidate: DesignLabCandidate) -> DesignLabCandidate:
    """Return the TRANSIENT candidate to the Design Lab's committed Draft base
    state (§18). ZERO Draft writes. Does NOT restore a historic Ready-Template
    baseline over merchant customizations — the "original DNA" is the current
    committed Draft appearance the candidate was generated from.
    """
    return DesignLabCandidate(
        base_selections=candidate.base_selections,
        candidate_selections=dict(candidate.base_selections),
        settings=candidate.settings,
        locked_families=candidate.locked_families,
        seed=candidate.seed,
    )


def reset_candidate(draft) -> DesignLabCandidate:
    """Discard any transient experiment and return a candidate equal to the
    current committed Draft (§19). No write, no history, no revision change.
    Not Undo — this never touches edit history.
    """
    base_selections, base_settings = _base_state(draft)
    return DesignLabCandidate(
        base_selections=base_selections,
        candidate_selections=dict(base_selections),
        settings=base_settings,
        locked_families=frozenset(),
        seed=None,
    )


def remove_theme(candidate: DesignLabCandidate) -> DesignLabCandidate:
    """Transient Remove Theme (§9): set the candidate's theme selection to the
    no-op and drop theme settings. NO Draft write — the real removal happens on
    Apply through the canonical W2 ``clear_theme`` owner. All non-theme state is
    preserved exactly.
    """
    new_selections = dict(candidate.candidate_selections)
    new_selections["theme"] = THEME_NONE_COMPONENT_KEY
    new_settings = dict(candidate.settings) if candidate.settings else {}
    new_settings.pop("theme", None)
    return DesignLabCandidate(
        base_selections=candidate.base_selections,
        candidate_selections=new_selections,
        settings=new_settings,
        locked_families=candidate.locked_families,
        seed=candidate.seed,
    )


# ---------------------------------------------------------------------------
# Explicit Apply -> ONE canonical atomic mutation payload (§13)
# ---------------------------------------------------------------------------
def candidate_apply_mutation(candidate: DesignLabCandidate, *, draft_id: int) -> dict:
    """Serialise a candidate into the ONE canonical ``design_lab.apply_candidate``
    mutation payload. The whole multi-family change is applied atomically inside
    ``r4_mutation_service.apply_mutation`` — one base_revision, one stale check,
    one transaction, one history entry.

    Only the candidate's SELECTIONS + theme intensity are sent; the server
    re-validates every component against the canonical registry and applies
    Theme removal through the W2 ``clear_theme`` owner.
    """
    theme_intensity = None
    if candidate.settings and isinstance(candidate.settings.get("theme"), Mapping):
        theme_intensity = candidate.settings["theme"].get("intensity")
    return {
        "type": DESIGN_LAB_APPLY_MUTATION_TYPE,
        "draft_id": draft_id,
        "selections": dict(candidate.candidate_selections),
        "theme_intensity": theme_intensity,
    }


# ---------------------------------------------------------------------------
# Transient candidate token for the existing Preview route (§11)
# ---------------------------------------------------------------------------
def encode_candidate_token(candidate: DesignLabCandidate) -> str:
    """Encode a candidate into a bounded, URL-safe token for the existing
    ``storefront_preview`` route's ``?design_lab=`` param.

    This is NOT an authority: the server ALWAYS re-validates every component key
    against the canonical registry when resolving the token for preview. It is a
    transport, not a source of truth. It carries no store/draft identity (tenant
    boundary is enforced by the preview route's own store resolution).
    """
    payload = {
        "selections": dict(candidate.candidate_selections),
        "settings": _deep_freeze_settings(candidate.settings),
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def decode_candidate_token(token: str) -> DesignLabCandidate:
    """Decode a ``?design_lab=`` token into a candidate. Raises ``ValueError`` on
    malformed input. Does NOT validate component keys against the registry — the
    caller (preview) must resolve through ``resolve_candidate_appearance`` /
    ``validate_store_appearance_manifest`` which fail closed on bad keys.
    """
    if not isinstance(token, str) or not token:
        raise ValueError("empty design_lab token")
    try:
        raw = base64.urlsafe_b64decode(token.encode("ascii"))
        payload = json.loads(raw.decode("utf-8"))
    except (ValueError, TypeError) as exc:
        raise ValueError("malformed design_lab token") from exc
    if not isinstance(payload, dict):
        raise ValueError("malformed design_lab token")
    selections = payload.get("selections")
    settings = payload.get("settings", {})
    if not isinstance(selections, dict) or not isinstance(settings, dict):
        raise ValueError("malformed design_lab token")
    return DesignLabCandidate(
        base_selections=selections,
        candidate_selections=selections,
        settings=settings,
        locked_families=frozenset(),
        seed=None,
    )
