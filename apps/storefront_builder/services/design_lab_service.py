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

    The candidate carries BOTH the immutable **generation base** (the committed
    Draft state the whole experiment is measured against) AND the evolving
    **working state**, so chained operations (Random Mix, Randomize One, Lock)
    build on the current candidate while Compare/Return always measure against
    the original Base. It also binds the candidate to the Draft it was generated
    from (``draft_id``) and the revision at generation time (``base_revision``),
    so a stale Apply can be rejected.

    * ``base_selections`` / ``base_settings`` — the committed Draft's canonical
      selections/settings at generation time (the fixed "Base" for Compare/Return).
    * ``candidate_selections`` / ``candidate_settings`` — the evolving working state.
    * ``locked_families`` — families the merchant locked (transient exploration lock).
    * ``seed`` — the deterministic PRNG seed used by the last generation step.
    * ``base_revision`` — the Draft ``edit_revision`` at generation time (stale check).
    * ``draft_id`` — the Draft pk the candidate belongs to (tenant/stale binding).

    ``settings`` is retained as an alias of ``candidate_settings`` for backward
    compatibility with existing call sites (preview manifest, apply payload).
    """

    base_selections: Mapping[str, str]
    candidate_selections: Mapping[str, str]
    # Backward-compatible alias for candidate_settings (kept as a positional/
    # keyword arg some call sites still pass); normalised in __post_init__.
    settings: Mapping = None
    locked_families: frozenset[str] = frozenset()
    seed: int | None = None
    base_settings: Mapping = None
    candidate_settings: Mapping = None
    base_revision: int | None = None
    draft_id: int | None = None

    def __post_init__(self) -> None:
        # Normalise the settings aliases: candidate_settings is authoritative;
        # ``settings`` is a backward-compatible alias that mirrors it.
        cand_settings = (
            self.candidate_settings
            if self.candidate_settings is not None
            else (self.settings if self.settings is not None else {})
        )
        base_settings = (
            self.base_settings if self.base_settings is not None else cand_settings
        )
        # Freeze the mutable inputs into immutable copies so the transient
        # candidate can never be mutated in place by a caller.
        object.__setattr__(self, "base_selections", dict(self.base_selections))
        object.__setattr__(
            self, "candidate_selections", dict(self.candidate_selections)
        )
        object.__setattr__(self, "base_settings", _deep_freeze_settings(base_settings))
        object.__setattr__(
            self, "candidate_settings", _deep_freeze_settings(cand_settings)
        )
        # ``settings`` mirrors candidate_settings (what preview/apply consume).
        object.__setattr__(self, "settings", _deep_freeze_settings(cand_settings))
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
    current_candidate: "DesignLabCandidate | None" = None,
    randomize_families: set[str],
    locked_families: set[str],
    seed: int | None = None,
) -> DesignLabCandidate:
    """Produce a transient candidate.

    Rules (§8):
    - The **original Base** stays fixed for the whole experiment: it comes from
      ``current_candidate`` when chaining, else from the committed Draft.
    - The randomization starts from the CURRENT candidate working state (when
      chaining) so chained operations preserve prior candidate choices — NOT the
      committed Draft (Architect IMPORTANT 2). Fresh runs start from the Draft.
    - Only families in ``randomize_families`` (∩ eligible) may change.
    - A family in ``locked_families`` never changes — it preserves its CURRENT
      candidate value (not the committed Draft value).
    - Options come only from the canonical registry (never fabricated); prefer a
      component different from the current one when alternatives exist; leaving a
      family unchanged is valid when it has no alternative.
    Deterministic for a given (starting state, randomize set, locked set, seed).
    """
    draft_selections, draft_settings = _base_state(draft)

    if current_candidate is not None:
        # Fixed original Base + binding survive across the whole experiment.
        base_selections = dict(current_candidate.base_selections)
        base_settings = _deep_freeze_settings(current_candidate.base_settings)
        working_selections = dict(current_candidate.candidate_selections)
        working_settings = _deep_freeze_settings(current_candidate.candidate_settings)
        base_revision = current_candidate.base_revision
        draft_id = current_candidate.draft_id
    else:
        base_selections = draft_selections
        base_settings = draft_settings
        working_selections = dict(draft_selections)
        working_settings = _deep_freeze_settings(draft_settings)
        base_revision = getattr(draft, "edit_revision", None)
        draft_id = getattr(draft, "pk", None)

    locked = frozenset(locked_families)
    # A locked family is never randomized, even if also requested — lock wins.
    effective_randomize = (
        (set(randomize_families) & set(DESIGN_LAB_RANDOMIZABLE_FAMILIES)) - locked
    )

    rng = random.Random(seed)
    candidate_selections = dict(working_selections)

    # Deterministic family ordering so the PRNG draw sequence is stable.
    for family in sorted(effective_randomize):
        # Randomize away from the CURRENT candidate value (working state), so a
        # visible change accumulates on top of prior choices (§8.10).
        current = working_selections.get(family)
        options = [c.key for c in list_components(family)]
        alternatives = [key for key in options if key != current]
        if alternatives:
            candidate_selections[family] = rng.choice(alternatives)
        # else: no compatible alternative -> leave unchanged (§8.11).

    return DesignLabCandidate(
        base_selections=base_selections,
        base_settings=base_settings,
        candidate_selections=candidate_selections,
        candidate_settings=working_settings,
        locked_families=locked,
        seed=seed,
        base_revision=base_revision,
        draft_id=draft_id,
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
    base_settings = dict(candidate.base_settings) if candidate.base_settings else {}
    cand_settings = dict(candidate.candidate_settings) if candidate.candidate_settings else {}
    for family in families:
        base_key = candidate.base_selections.get(family)
        cand_key = candidate.candidate_selections.get(family)
        # A family differs if EITHER its selection OR its per-family settings
        # changed (Architect RED C: settings differences must be detected).
        selection_changed = base_key != cand_key and not (
            base_key is None and cand_key is None
        )
        settings_changed = base_settings.get(family) != cand_settings.get(family)
        if not selection_changed and not settings_changed:
            continue
        diffs.append(
            {
                "family": family,
                "family_label": _family_label(family),
                "base_key": base_key,
                "candidate_key": cand_key,
                "base_label": _component_label(base_key) if base_key else "",
                "candidate_label": _component_label(cand_key) if cand_key else "",
                "base_settings": base_settings.get(family),
                "candidate_settings": cand_settings.get(family),
                "settings_changed": settings_changed,
            }
        )
    return diffs


def all_family_labels(candidate: DesignLabCandidate) -> dict[str, dict[str, str]]:
    """Merchant-facing Persian labels for EVERY family — never only the ones
    that changed (Architect IMPORTANT 2). ``compare_with_base`` only reports
    changed families, so a family that returns to its Base value (Return to
    Original DNA, Reset, Undo, or simply randomizing back to the same key)
    disappears from ``diffs`` even though its visible label must still be
    refreshed. The endpoint returns this for ALL families so the client never
    has to derive a label in JavaScript — it only ever reflects a server-
    computed string.
    """
    labels: dict[str, dict[str, str]] = {}
    for family in COMPONENT_FAMILIES:
        base_key = candidate.base_selections.get(family)
        cand_key = candidate.candidate_selections.get(family)
        labels[family] = {
            "family_label": _family_label(family),
            "base_label": _component_label(base_key) if base_key else "",
            "candidate_label": _component_label(cand_key) if cand_key else "",
        }
    return labels


def return_to_original_dna(draft, candidate: DesignLabCandidate) -> DesignLabCandidate:
    """Return the TRANSIENT candidate to the Design Lab's committed Draft base
    state (§18). ZERO Draft writes. Does NOT restore a historic Ready-Template
    baseline over merchant customizations — the "original DNA" is the current
    committed Draft appearance the candidate was generated from.
    """
    return DesignLabCandidate(
        base_selections=candidate.base_selections,
        base_settings=candidate.base_settings,
        candidate_selections=dict(candidate.base_selections),
        candidate_settings=_deep_freeze_settings(candidate.base_settings),
        locked_families=candidate.locked_families,
        seed=candidate.seed,
        base_revision=candidate.base_revision,
        draft_id=candidate.draft_id,
    )


def reset_candidate(draft) -> DesignLabCandidate:
    """Discard any transient experiment and return a candidate equal to the
    current committed Draft (§19). No write, no history, no revision change.
    Not Undo — this never touches edit history. Binds the fresh candidate to the
    Draft's current identity + revision.
    """
    base_selections, base_settings = _base_state(draft)
    return DesignLabCandidate(
        base_selections=base_selections,
        base_settings=base_settings,
        candidate_selections=dict(base_selections),
        candidate_settings=_deep_freeze_settings(base_settings),
        locked_families=frozenset(),
        seed=None,
        base_revision=getattr(draft, "edit_revision", None),
        draft_id=getattr(draft, "pk", None),
    )


def remove_theme(candidate: DesignLabCandidate) -> DesignLabCandidate:
    """Transient Remove Theme (§9): set the candidate's theme selection to the
    no-op and drop theme settings. NO Draft write — the real removal happens on
    Apply through the canonical W2 ``clear_theme`` owner. All non-theme state and
    the original Base are preserved exactly.
    """
    new_selections = dict(candidate.candidate_selections)
    new_selections["theme"] = THEME_NONE_COMPONENT_KEY
    new_settings = dict(candidate.candidate_settings) if candidate.candidate_settings else {}
    new_settings.pop("theme", None)
    return DesignLabCandidate(
        base_selections=candidate.base_selections,
        base_settings=candidate.base_settings,
        candidate_selections=new_selections,
        candidate_settings=new_settings,
        locked_families=candidate.locked_families,
        seed=candidate.seed,
        base_revision=candidate.base_revision,
        draft_id=candidate.draft_id,
    )


def _with_candidate_state(
    candidate: DesignLabCandidate,
    *,
    candidate_selections: Mapping[str, str],
    candidate_settings: Mapping,
    locked_families: frozenset[str] | None = None,
) -> DesignLabCandidate:
    """A copy of ``candidate`` whose WORKING state is replaced; the fixed Base,
    seed and Draft/revision binding are always carried over unchanged."""
    return DesignLabCandidate(
        base_selections=candidate.base_selections,
        base_settings=candidate.base_settings,
        candidate_selections=candidate_selections,
        candidate_settings=candidate_settings,
        locked_families=(
            candidate.locked_families if locked_families is None else locked_families
        ),
        seed=candidate.seed,
        base_revision=candidate.base_revision,
        draft_id=candidate.draft_id,
    )


def reset_experiment_to_base(candidate: DesignLabCandidate) -> DesignLabCandidate:
    """«برگشت به شروع» (Studio) — return the transient Candidate to the FIXED
    Base the experiment captured when it started, clearing every transient
    family lock and restoring the experiment Base Theme.

    Unlike :func:`reset_candidate` it never re-reads the committed Draft: the
    same Base, ``draft_id`` and ``base_revision`` binding survive, so an
    experiment that went stale (the Draft moved elsewhere) stays stale and is
    never silently rebased onto newer work. Pure: no Draft/history/revision
    write.
    """
    return _with_candidate_state(
        candidate,
        candidate_selections=dict(candidate.base_selections),
        candidate_settings=_deep_freeze_settings(candidate.base_settings),
        locked_families=frozenset(),
    )


class TemplateDnaUnavailable(Exception):
    """The Draft's exact current Ready Template version, or its canonical Store
    Appearance DNA, cannot be resolved. Callers fail closed — never guess
    another version."""


def _exact_template_dna(draft) -> tuple[dict[str, str], dict]:
    """The canonical Store Appearance DNA declared by the EXACT Ready Template
    key + version recorded in the Draft's provenance, resolved through the
    existing immutable version registry and validated by the canonical manifest
    contract. Raises :class:`TemplateDnaUnavailable` on any gap."""
    from .. import layout_preset_registry
    from ..storefront_appearance.contracts import InvalidStoreAppearanceContract
    from ..storefront_appearance.validation import validate_store_appearance_manifest

    provenance = getattr(draft, "template_provenance", None)
    template = provenance.get("template") if isinstance(provenance, Mapping) else None
    key = template.get("key") if isinstance(template, Mapping) else None
    version = template.get("version") if isinstance(template, Mapping) else None
    if not isinstance(key, str) or not key or not isinstance(version, str) or not version:
        raise TemplateDnaUnavailable("draft has no exact template provenance")
    preset = layout_preset_registry.get_layout_preset_version(key, version)
    if preset is None or not isinstance(preset.store_appearance, Mapping):
        raise TemplateDnaUnavailable(
            f"template {key!r} version {version!r} has no Store Appearance DNA"
        )
    try:
        validated = validate_store_appearance_manifest(
            preset.store_appearance, require_complete=True
        )
    except InvalidStoreAppearanceContract as exc:
        raise TemplateDnaUnavailable(str(exc)) from exc
    primitive = manifest_to_primitive(validated.manifest)
    return dict(primitive["selections"]), dict(primitive.get("settings", {}))


def return_to_template_dna(draft, candidate: DesignLabCandidate) -> DesignLabCandidate:
    """«بازگشت به سبک اولیه» (Studio) — restore the Candidate's seven design
    families to the canonical DNA of the Draft's CURRENT exact Ready Template
    version.

    Independent of locks (locked families are restored too; the lock set itself
    is kept), preserves the Candidate's current Theme, never touches page
    composition (``layout``) or any non-design family, and keeps the original
    Base + ``draft_id`` + ``base_revision`` binding. Pure: no Draft/history/
    revision write. Raises :class:`TemplateDnaUnavailable` (fail closed).
    """
    dna_selections, dna_settings = _exact_template_dna(draft)
    new_selections = dict(candidate.candidate_selections)
    new_settings = _deep_freeze_settings(candidate.candidate_settings or {})
    for family in DESIGN_LAB_RANDOMIZABLE_FAMILIES:
        if family not in dna_selections:
            continue
        new_selections[family] = dna_selections[family]
        if family in dna_settings:
            new_settings[family] = dna_settings[family]
        else:
            new_settings.pop(family, None)
    return _with_candidate_state(
        candidate, candidate_selections=new_selections, candidate_settings=new_settings
    )


def set_candidate_theme(
    candidate: DesignLabCandidate, *, theme_component_key: str, intensity: str
) -> DesignLabCandidate:
    """Transient occasion Theme inside the experiment (Studio «مناسبت»).

    Validates the component through the canonical component registry (it must
    exist AND belong to the ``theme`` family) and the intensity through the
    canonical W2 theme contract. The no-op theme delegates to
    :func:`remove_theme` (a no-op occasion never carries an intensity — the
    same rule the persisted ``apply_theme`` owner follows). Only the Candidate's
    theme selection/settings change; Base, every other family, locks, seed and
    the Draft/revision binding are preserved. Pure: no write of any kind — the
    ONLY persistence boundary stays ``design_lab.apply_candidate``.

    Raises ``ValueError`` for an invalid component or intensity (fail closed —
    never falls back to another Theme).
    """
    from .. import theme_catalog

    if not isinstance(theme_component_key, str) or not theme_component_key:
        raise ValueError("invalid_theme_component")
    component = get_component(theme_component_key)
    if component is None or component.family_key != "theme":
        raise ValueError("invalid_theme_component")
    if theme_component_key == THEME_NONE_COMPONENT_KEY:
        return remove_theme(candidate)
    if not isinstance(intensity, str) or not theme_catalog.is_valid_intensity(intensity):
        raise ValueError("invalid_theme_intensity")
    new_selections = dict(candidate.candidate_selections)
    new_selections["theme"] = theme_component_key
    new_settings = _deep_freeze_settings(candidate.candidate_settings or {})
    theme_settings = dict(new_settings.get("theme") or {})
    theme_settings["intensity"] = intensity
    new_settings["theme"] = theme_settings
    return _with_candidate_state(
        candidate, candidate_selections=new_selections, candidate_settings=new_settings
    )


# ---------------------------------------------------------------------------
# Stale / tenant binding (§14, §15) — real-flow preflight
# ---------------------------------------------------------------------------
def candidate_is_stale(draft, candidate: DesignLabCandidate) -> bool:
    """True IFF the candidate was generated against a different Draft or an
    older revision than the currently-active Draft.

    Binds the transient candidate to ``draft_id`` + ``base_revision`` recorded at
    generation time. The Design Lab endpoint uses this as a preflight so a stale
    candidate is rejected BEFORE an Apply mutation is even produced. It is not
    the final enforcement — the canonical ``apply_mutation`` boundary still
    performs the authoritative transactional stale-write check (never rebased).
    """
    if candidate.draft_id is not None and candidate.draft_id != getattr(draft, "pk", None):
        return True
    if (
        candidate.base_revision is not None
        and candidate.base_revision != getattr(draft, "edit_revision", None)
    ):
        return True
    return False


# ---------------------------------------------------------------------------
# Explicit Apply -> ONE canonical atomic mutation payload (§13)
# ---------------------------------------------------------------------------
def candidate_apply_mutation(candidate: DesignLabCandidate, *, draft_id: int) -> dict:
    """Serialise a candidate into the ONE canonical ``design_lab.apply_candidate``
    mutation payload. The whole multi-family change is applied atomically inside
    ``r4_mutation_service.apply_mutation`` — one base_revision, one stale check,
    one transaction, one history entry.

    The payload carries the SIGNED ``candidate_token`` — never raw client-
    editable ``selections``/``theme_intensity`` (Architect IMPORTANT 1). The
    canonical mutation transaction decodes/re-validates the token and re-checks
    the candidate's OWN ``draft_id``/``base_revision`` against the currently
    locked Draft, so a candidate generated at revision N is rejected there even
    if the OUTER mutation envelope's ``base_revision`` was refreshed to N+1 by
    an intervening edit after the ``/design-lab/`` ``apply_payload`` preflight
    already passed at N (that preflight is a UX nicety only, never the
    enforcement).
    """
    return {
        "type": DESIGN_LAB_APPLY_MUTATION_TYPE,
        "draft_id": draft_id,
        "candidate_token": encode_candidate_token(candidate),
    }


# ---------------------------------------------------------------------------
# Transient candidate token for the existing Preview route (§11)
# ---------------------------------------------------------------------------
#: The token carries correctness-critical Base + generation-revision + draft
#: identity, so it is integrity-protected with Django's own signing primitive
#: (``django.core.signing``, HMAC over SECRET_KEY). It is a bounded, tamper-
#: evident transport — NEVER a source of truth for component validity: the
#: server ALWAYS re-validates every component key against the canonical registry
#: when resolving/applying. The signature only guarantees the Base/revision/
#: draft-id truth was server-issued and not client-edited.
_TOKEN_SALT = "storefront_builder.design_lab.candidate.v1"
#: Bounded token lifetime (a Design Lab session is short-lived; a very old token
#: is stale anyway and re-checked against the live revision at Apply).
_TOKEN_MAX_AGE_SECONDS = 60 * 60 * 6


def encode_candidate_token(candidate: DesignLabCandidate) -> str:
    """Encode a candidate into a bounded, signed token for the existing
    ``storefront_preview`` route's ``?design_lab=`` param and the Design Lab
    endpoint. Integrity-protected (HMAC) so the Base/revision/draft-id it carries
    cannot be edited by the client. Not an authority for component validity —
    the server re-validates selections/settings through the canonical validator.
    """
    from django.core import signing

    payload = {
        "bs": dict(candidate.base_selections),
        "bt": _deep_freeze_settings(candidate.base_settings),
        "cs": dict(candidate.candidate_selections),
        "ct": _deep_freeze_settings(candidate.candidate_settings),
        "locked": sorted(candidate.locked_families),
        "seed": candidate.seed,
        "rev": candidate.base_revision,
        "did": candidate.draft_id,
    }
    return signing.dumps(payload, salt=_TOKEN_SALT, compress=True)


def decode_candidate_token(token: str) -> DesignLabCandidate:
    """Decode + verify a signed ``design_lab`` token into a candidate.

    Raises ``ValueError`` on a missing/malformed/tampered/expired token (a bad
    HMAC signature is a ``signing.BadSignature`` which we surface as ``ValueError``
    so callers uniformly return a controlled 400). Validates shape/types. Does
    NOT validate component keys against the registry — the caller resolves
    through ``resolve_candidate_appearance`` / ``validate_store_appearance_manifest``
    which fail closed on bad keys.

    ``signing.SignatureExpired`` is a SUBCLASS of ``signing.BadSignature``, so it
    MUST be caught first — an ``except BadSignature`` clause ahead of it would
    silently swallow every expiry as a "tampered" verdict and never reach the
    expiry branch (MINOR, Architect review).
    """
    from django.core import signing

    if not isinstance(token, str) or not token:
        raise ValueError("empty design_lab token")
    try:
        payload = signing.loads(
            token, salt=_TOKEN_SALT, max_age=_TOKEN_MAX_AGE_SECONDS
        )
    except signing.SignatureExpired as exc:
        raise ValueError("malformed or expired design_lab token") from exc
    except signing.BadSignature as exc:
        raise ValueError("tampered or invalid design_lab token") from exc
    except (ValueError, TypeError) as exc:
        raise ValueError("malformed or expired design_lab token") from exc
    if not isinstance(payload, dict):
        raise ValueError("malformed design_lab token")

    base_selections = payload.get("bs")
    base_settings = payload.get("bt", {})
    candidate_selections = payload.get("cs")
    candidate_settings = payload.get("ct", {})
    locked = payload.get("locked", [])
    if not isinstance(base_selections, dict) or not isinstance(candidate_selections, dict):
        raise ValueError("malformed design_lab token: selections")
    if not isinstance(base_settings, dict) or not isinstance(candidate_settings, dict):
        raise ValueError("malformed design_lab token: settings")
    if not isinstance(locked, list):
        raise ValueError("malformed design_lab token: locked")
    rev = payload.get("rev")
    did = payload.get("did")
    if rev is not None and not isinstance(rev, int):
        raise ValueError("malformed design_lab token: rev")
    if did is not None and not isinstance(did, int):
        raise ValueError("malformed design_lab token: did")

    return DesignLabCandidate(
        base_selections=base_selections,
        base_settings=base_settings,
        candidate_selections=candidate_selections,
        candidate_settings=candidate_settings,
        locked_families=frozenset(f for f in locked if isinstance(f, str)),
        seed=payload.get("seed"),
        base_revision=rev,
        draft_id=did,
    )
