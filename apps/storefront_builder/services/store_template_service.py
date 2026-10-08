"""Store-level Ready Template orchestration used by owner onboarding (and any caller that must
choose/inspect a Store's Ready Template WITHOUT the Merchant Admin request context).

This module owns NO catalog and NO application algorithm. It only decides which existing
canonical authority to call:

* first-ever application on an untouched bootstrap Draft → ``preset_service.apply_preset`` (the
  documented initial-apply primitive: the Store receives EXACTLY the chosen template, never a hybrid
  with the legacy bootstrap content);
* any later change (or a Draft the merchant already touched) →
  ``r4_mutation_service.switch_template_current`` (the preservation-first Ready Template switch).

Section/appearance/provenance/baseline writes all stay inside those services.
"""

from dataclasses import dataclass

from django.db import transaction

from .. import layout_preset_registry
from ..models import StorefrontLayout, StorefrontLayoutVersion
from ..variant_contract import UnsupportedEngineSchemaVersionError, validate_template_provenance
from . import layout_service, preset_service, r4_mutation_service


class ReadyTemplateSelectionError(Exception):
    """A controlled, user-presentable refusal (``code`` is a stable machine reason)."""

    def __init__(self, code: str, message: str = ""):
        self.code = code
        super().__init__(message or code)


@dataclass(frozen=True)
class AppliedTemplate:
    """The Ready Template a Store currently carries, by exact provenance identity."""

    key: str
    version: str
    preset: object  # the exact registered LayoutPresetDefinition (any official version)
    is_current_version: bool  # == the latest merchant-facing catalog version
    location: str  # "draft" | "published"


def resolve_current_ready_template(template_key):
    """The CURRENT merchant-facing Ready Template for ``template_key`` — resolved ONLY from
    ``layout_preset_registry.list_ready_templates()``. Unknown key, a non-Ready structural preset
    and a historical version all resolve to ``None``."""
    if not isinstance(template_key, str) or not template_key:
        return None
    return next((p for p in layout_preset_registry.list_ready_templates() if p.key == template_key), None)


def _identity_from_provenance(raw):
    try:
        template = validate_template_provenance(raw)["template"]
    except UnsupportedEngineSchemaVersionError:
        return None, None
    return template.get("key"), template.get("version")


def get_applied_template(store) -> AppliedTemplate | None:
    """Read-only: which exact registered Ready Template does this Store carry? The active Draft is
    authoritative; when there is no Draft, the Published version is. ``None`` when nothing valid is
    applied (no provenance, unknown key/version, or a non-Ready preset). Never creates anything."""
    layout = (
        StorefrontLayout.objects.select_related("draft_version", "published_version").filter(store=store).first()
    )
    if layout is None:
        return None
    draft = layout.draft_version
    if draft is not None and draft.status == StorefrontLayoutVersion.Status.DRAFT:
        version, location = draft, "draft"
    elif layout.published_version is not None:
        version, location = layout.published_version, "published"
    else:
        return None
    key, template_version = _identity_from_provenance(version.template_provenance)
    if not (key and template_version):
        return None
    preset = layout_preset_registry.get_layout_preset_version(key, template_version)
    if preset is None or not preset.is_ready_template:
        return None
    current = resolve_current_ready_template(key)
    return AppliedTemplate(
        key=key, version=template_version, preset=preset,
        is_current_version=bool(current is not None and current.version == template_version),
        location=location,
    )


def _is_untouched_bootstrap(layout, draft) -> bool:
    """True only for the very first Draft of a Store that has never been published, that came
    straight from the legacy bootstrap, carries no template identity and was never edited."""
    key, _version = _identity_from_provenance(draft.template_provenance)
    return bool(
        not key
        and layout.published_version_id is None
        and draft.source == StorefrontLayoutVersion.Source.LEGACY_BOOTSTRAP
        and draft.edit_revision == 0
    )


@dataclass(frozen=True)
class SelectionResult:
    draft: StorefrontLayoutVersion
    preset: object
    action: str  # "initial" | "switched" | "unchanged"


@transaction.atomic
def select_ready_template(*, store, actor, template_key) -> SelectionResult:
    """Server-authoritative Ready Template selection for ``store``.

    ``template_key`` is the ONLY client-supplied value: the version, label, appearance and manifest
    are always resolved from the canonical catalog. Transactional; a refusal mutates nothing."""
    preset = resolve_current_ready_template(template_key)
    if preset is None:
        raise ReadyTemplateSelectionError(
            "unknown_template", "قالبِ انتخاب‌شده معتبر نیست؛ یکی از قالب‌هایِ فهرست را انتخاب کنید.",
        )

    draft = layout_service.get_or_create_draft(store, user=actor)
    layout = StorefrontLayout.objects.select_for_update().get(store=store)
    draft = StorefrontLayoutVersion.objects.select_for_update().get(pk=layout.draft_version_id)

    current_key, current_version = _identity_from_provenance(draft.template_provenance)
    if current_key == preset.key and current_version == preset.version:
        return SelectionResult(draft=draft, preset=preset, action="unchanged")

    if _is_untouched_bootstrap(layout, draft):
        try:
            preset_service.apply_preset(draft, preset)
        except preset_service.InvalidPresetError as exc:
            raise ReadyTemplateSelectionError("invalid_template", str(exc)) from exc
        return SelectionResult(draft=draft, preset=preset, action="initial")

    try:
        draft = r4_mutation_service.switch_template_current(
            store=store, actor=actor, template_key=preset.key, template_version=preset.version,
        )
    except (r4_mutation_service.R4MutationError, preset_service.InvalidPresetError) as exc:
        raise ReadyTemplateSelectionError("invalid_template", str(exc)) from exc
    return SelectionResult(draft=draft, preset=preset, action="switched")
