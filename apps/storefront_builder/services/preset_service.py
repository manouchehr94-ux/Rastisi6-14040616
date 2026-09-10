"""Preset Application Service — Phase 6: اعمالِ یک ``LayoutPresetDefinition``
(``layout_preset_registry.py``) روی یک Draft.

قوانینِ معماریِ الزامی (طبقِ Phase 6 Audit):

- همیشه یک Draftِ صریح می‌گیرد (هرگز خودش «Draftِ جاری» را resolve
  نمی‌کند) — دقیقاً همان الگویِ ``bootstrap_service.apply_family_default_sections``.
  ``published_version`` هرگز از این ماژول قابلِ‌دسترس نیست.
- تراکنشی است: تمامِ اعتبارسنجی پیش از هر نوشتنی انجام می‌شود؛ اگر هرچیزی
  نامعتبر باشد، Draft کاملاً دست‌نخورده می‌ماند (نه نیمه‌اعمال‌شده).
- فقط ``StorefrontSection``هایِ صفحاتی که خودِ Preset صراحتاً پوشش داده
  حذف/بازسازی می‌شوند — صفحه‌ای که Preset آن را ذکر نکرده دست‌نخورده
  می‌ماند (طبقِ الزامِ صریحِ کار: «A preset may omit a page deliberately»).
- رنگ هرگز توسطِ این ماژول تغییر نمی‌کند مگر مرچنت هنوز هیچ Paletteای
  انتخاب نکرده باشد (فقط آنگاه پیشنهادِ Preset اعمال می‌شود) — Palette
  همیشه مستقل/آزاد می‌ماند (تصمیمِ مالک).
- هیچ محتوایِ کسب‌وکاریِ مرچنت (رسانه، محصول/دسته/کالکشنِ انتخابی، متنِ
  اعلانِ هدر) توسطِ این ماژول نوشته/پاک نمی‌شود — فقط section composition
  و تنظیماتِ ساختاری/بصری (طبقِ تفکیکِ صریحِ کار: STRUCTURAL/VISUAL در
  برابرِ MERCHANT CONTENT)."""

from __future__ import annotations

from django.db import transaction

from .. import global_region_registry, layout_preset_registry, section_registry
from ..layout_preset_registry import LayoutPresetDefinition
from ..models import StorefrontContainer, StorefrontLayoutVersion, StorefrontSection
from ..variant_contract import build_template_provenance, validate_template_provenance
from . import appearance_authority_service, container_service, layout_service


class InvalidPresetError(Exception):
    """یک Preset (تعریف یا اعمال) نامعتبر است — Draft نباید تغییر کند."""


class UnknownPresetError(InvalidPresetError):
    """کلیدِ Preset درخواست‌شده در ``LAYOUT_PRESET_REGISTRY`` وجود ندارد."""


class BaselineResetError(Exception):
    """Acceptance Batch 2 (post-U11) — پایه‌یِ خطاهایِ عملیاتِ بازنشانیِ
    granular (field/component/section/page/header/footer) — جدا از
    ``InvalidPresetError`` چون این‌ها خطاهایِ *اعمالِ یک Preset* نیستند،
    بلکه خطاهایِ *بازنشانیِ چیزی که از قبل روی Draft هست* هستند."""


class NotABaselineSectionError(BaselineResetError):
    """این section هرگز از یک Ready Template baseline نیامده
    (``template_slot_key`` خالی است) — یک section کاملاً دستیِ مرچنت را
    نمی‌توان «بازنشانی به قالب» کرد، چون هیچ baselineای برایش وجود ندارد."""


class BaselineSlotNotFoundError(BaselineResetError):
    """``template_slot_key``ِ این section در عکسِ baselineِ فعلاً ذخیره‌شده
    پیدا نشد — مثلاً بعد از اینکه یک Ready Template *دیگر* رویِ همین Draft
    اعمال شده و یک عکسِ کاملاً جدید جایگزینِ قبلی شده."""


class BaselineFieldNotFoundError(BaselineResetError):
    """کلیدِ فیلدِ درخواست‌شده در baselineِ ثبت‌شده (نه section، نه ظاهر)
    وجود ندارد."""


class UnknownBaselinePageError(BaselineResetError):
    """این نوع صفحه بخشی از baselineِ Ready Templateِ اعمال‌شده روی این
    Draft نیست — Presetها می‌توانند عمداً یک صفحه را پوشش ندهند."""


class NoHeaderBaselineError(BaselineResetError):
    """Ready Templateِ اعمال‌شده هیچ overrideِ هدری تعریف نکرده — چیزی
    برایِ بازنشانیِ هدر به baseline وجود ندارد."""


class NoFooterBaselineError(BaselineResetError):
    """معادلِ ``NoHeaderBaselineError`` برایِ فوتر."""


class LockedSectionsPresentError(InvalidPresetError):
    """Phase 1 correction (spec §37 — Lock): یک/چند section از صفحاتی که
    این Preset صریحاً می‌خواهد جایگزین کند قفل هستند. اعمالِ Preset
    یعنی حذفِ کاملِ sectionهایِ آن صفحه و ساختِ فهرستِ تازه — این دقیقاً
    همان «حذفِ یک section قفل‌شده» است که ``storefront_section_remove``
    از مسیرِ تک‌section از قبل رد می‌کند؛ یک «مسیرِ جایگزین» (Preset) نباید
    بتواند همان محافظت را دور بزند. ``InvalidPresetError`` را ارث‌بری
    می‌کند تا کدِ ویوِ موجود (``except InvalidPresetError``) بدونِ تغییر
    این خطا را هم درست نشان دهد."""


def _validate_appearance_overlay(base_config: dict, overlay: dict) -> dict:
    """اعتبارسنجیِ زیرمجموعه‌ی ساختاریِ ``appearance`` یک Preset — رویِ
    یک پیکربندیِ پایه (پیش‌فرضِ خنثی یا پیکربندیِ واقعیِ یک Draft) قرار
    می‌گیرد و از همان اعتبارسنجِ رسمیِ ادیتور
    (``layout_service.validate_appearance_config``) عبور می‌کند — پس هر
    قاعده‌ای که آن ادیتور اعمال می‌کند (enum بسته، بازه‌ی عدد، ...) اینجا
    هم رعایت می‌شود، بدونِ تکرارِ منطق."""
    merged = {**base_config, **overlay}
    return layout_service.validate_appearance_config(merged)


def _validate_header_overlay(base_config: dict, overlay: dict | None) -> dict | None:
    if overlay is None:
        return None
    merged = {**base_config, **overlay}
    return layout_service.validate_header_config(merged)


def _validate_footer_overlay(base_config: dict, overlay: dict | None) -> dict | None:
    if overlay is None:
        return None
    merged = {**base_config, **overlay}
    return layout_service.validate_footer_config(merged)


def validate_layout_preset(preset: LayoutPresetDefinition) -> None:
    """اعتبارسنجیِ کاملِ یک تعریفِ Preset، مستقل از هر Draftِ واقعی —
    همان چیزی که تستِ Presetهایِ درون‌ساخت باید پیش از هر اجرا تضمین
    کند (طبقِ الزامِ صریحِ کار: «Invalid built-in Presets should fail
    tests/startup validation rather than fail at runtime for a
    merchant»). بخشِ section/page از قبل در زمانِ import توسطِ
    ``layout_preset_registry._validate_page_composition_shape`` چک شده؛
    اینجا فقط appearance/header/footer (که به ``layout_service`` نیاز
    دارند) روی یک پایه‌ی خنثی (پیش‌فرض‌هایِ پلتفرم) چک می‌شود."""
    from ..models import APPEARANCE_CONFIG_DEFAULTS, FOOTER_CONFIG_DEFAULTS, HEADER_CONFIG_DEFAULTS

    try:
        _validate_appearance_overlay(dict(APPEARANCE_CONFIG_DEFAULTS), dict(preset.appearance))
        _validate_header_overlay(dict(HEADER_CONFIG_DEFAULTS), preset.header)
        _validate_footer_overlay(dict(FOOTER_CONFIG_DEFAULTS), preset.footer)
        for page_type, entries in preset.pages.items():
            _container_settings_for_entries(
                entries, preset_key=preset.key, page_type=page_type
            )
    except (
        layout_service.AppearanceConfigValidationError,
        layout_service.HeaderConfigValidationError,
        layout_service.FooterConfigValidationError,
    ) as exc:
        raise InvalidPresetError(f"Preset «{preset.key}» نامعتبر است: {exc}") from exc

    if preset.default_palette_slug is not None:
        from .. import appearance_registry
        if appearance_registry.get_palette(preset.default_palette_slug) is None:
            raise InvalidPresetError(
                f"Preset «{preset.key}»: پالتِ پیشنهادیِ «{preset.default_palette_slug}» در دسترس نیست"
            )


def _entry_runs(entries, *, row_key=lambda e: e.row_key):
    """Group entries exactly like Container legacy-row reconstruction.

    ``row_key`` extracts the row-grouping key from one entry — defaults to
    attribute access (``PresetSectionEntry``); Acceptance Batch 2 (post-U11)
    passes ``lambda e: e["row_key"]`` to run the exact same grouping over a
    ``template_baseline_snapshot``'s plain-dict section entries, so the
    snapshot's per-run Container settings can be derived without a second,
    possibly-diverging grouping implementation."""
    entries = list(entries)
    i = 0
    while i < len(entries):
        first = entries[i]
        key = row_key(first) or ""
        if not key:
            yield [first]
            i += 1
            continue
        run = [first]
        i += 1
        while i < len(entries) and (row_key(entries[i]) or "") == key:
            run.append(entries[i])
            i += 1
        yield run


def _broadcast_container_settings_to_entries(entries, prepared_container_settings: list[dict]) -> list[dict]:
    """Acceptance Batch 2 (post-U11) — ``prepared_container_settings`` has
    one entry per contiguous ``row_key`` run (see ``_entry_runs``); this
    repeats each run's settings once per member entry, in entry order, so
    every individual section can carry its own (necessarily identical
    within a run — already enforced by ``_container_settings_for_entries``)
    Container settings inside ``template_baseline_snapshot``."""
    broadcasted = []
    for run, settings in zip(_entry_runs(entries), prepared_container_settings):
        broadcasted.extend([settings] * len(run))
    return broadcasted


def _container_settings_from_snapshot_sections(section_entries: list[dict]) -> list[dict]:
    """Inverse of the broadcast above — used when rebuilding Containers
    from an already-normalized ``template_baseline_snapshot`` (no
    re-validation needed; this data was validated once, at the original
    ``apply_preset`` call that produced the snapshot)."""
    return [
        run[0]["container_settings"]
        for run in _entry_runs(section_entries, row_key=lambda e: e["row_key"])
    ]


def _clean_preset_container_settings(raw, *, preset_key: str, page_type: str) -> dict:
    if raw is None:
        return container_service.effective_container_settings(None)

    cleaned = container_service.effective_container_settings(raw)
    # Built-in preset data must fail loudly rather than relying on runtime
    # fail-safe normalization.
    for key, value in raw.items():
        comparable = value
        if key == "gap":
            try:
                comparable = int(value)
            except (TypeError, ValueError) as exc:
                raise InvalidPresetError(
                    f"Preset «{preset_key}» / {page_type}: فاصله‌ی Container نامعتبر است"
                ) from exc
        if cleaned.get(key) != comparable:
            raise InvalidPresetError(
                f"Preset «{preset_key}» / {page_type}: تنظیم Container «{key}» نامعتبر است"
            )
    return cleaned


def _container_settings_for_entries(entries, *, preset_key: str, page_type: str) -> list[dict]:
    prepared = []
    for run in _entry_runs(entries):
        explicit = [
            _clean_preset_container_settings(
                entry.container_settings,
                preset_key=preset_key,
                page_type=page_type,
            )
            for entry in run
            if entry.container_settings is not None
        ]
        if explicit:
            first = explicit[0]
            if any(item != first for item in explicit[1:]):
                raise InvalidPresetError(
                    f"Preset «{preset_key}» / {page_type}: اعضای یک ردیف تنظیمات Container ناسازگار دارند"
                )
            prepared.append(first)
        else:
            prepared.append(container_service.effective_container_settings(None))
    return prepared


def _template_slot_key(preset: LayoutPresetDefinition, page_type: str, index: int) -> str:
    """Acceptance Batch 2 (post-U11) — a stable identity for this section's
    *position within the Template's authored page composition*, not the
    section's own ``stable_id`` (which tracks "same logical section across
    versions", unrelated) and not its current ``order`` (which a merchant
    freely changes by reordering). Deterministic and store-independent: two
    Drafts that both applied the same Template version get the exact same
    slot keys, and a merchant reordering/inserting/deleting sections never
    changes this value for the sections that survive."""
    return f"{preset.key}:v{preset.version}:{page_type}:{index}"


def _build_sections_for_page(page, entries, *, preset: LayoutPresetDefinition, page_type: str) -> list[StorefrontSection]:
    rows = []
    for order, entry in enumerate(entries):
        definition = section_registry.get_definition(entry.section_key)
        if entry.settings is None:
            settings = definition.default_settings()
        else:
            settings = definition.validate_settings(entry.settings)
        rows.append(StorefrontSection(
            page=page, section_key=entry.section_key, order=order, settings=settings,
            row_key=entry.row_key, row_span=entry.row_span,
            template_slot_key=_template_slot_key(preset, page_type, order),
        ))
    return rows


@transaction.atomic
def apply_preset(
    draft: StorefrontLayoutVersion, preset: LayoutPresetDefinition, *, _record_baseline_snapshot: bool = True,
) -> None:
    """Preset را روی ``draft`` اعمال می‌کند — Draft-only (فراخوان مسئولِ
    عبورِ یک نسخه‌یِ واقعاً Draft است، دقیقاً همان قراردادِ
    ``apply_family_default_sections``؛ این تابع خودش هرگز
    ``layout.published_version`` را resolve/لمس نمی‌کند).

    ترتیبِ عملیات عمداً «همه‌چیز را اول اعتبارسنجی کن، بعد بنویس» است —
    اگر هرکدام از appearance/header/footer/هر صفحه نامعتبر باشد، هیچ
    نوشتنی (نه روی Section، نه روی خودِ نسخه) اتفاق نمی‌افتد. علاوه‌براین
    خودِ تابع در یک تراکنشِ دیتابیسی (``@transaction.atomic``) پیچیده شده
    تا حتی یک خطایِ غیرمنتظره‌یِ سطحِ دیتابیس هم Draft را نیمه‌اعمال‌شده
    رها نکند.

    ``_record_baseline_snapshot`` (فقط داخلی — هرگز از بیرونِ این ماژول
    صدا زده نشود): پستِ‌دمو hardening pass، Issue 4. تنها فراخوانِ
    مشروعِ ``False`` مسیرِ سازگاریِ عقب‌رویِ ``reset_storefront_to_baseline``
    است — جایی که محتوایِ Registryِ *فعلی* صرفاً برایِ یک بازنشانیِ
    best-effort روی Draftی بدونِ عکسِ baselineِ واقعی خوانده می‌شود، نه
    به‌عنوانِ اعمالِ صریحِ یک Template. چون تطابقِ شماره‌یِ نسخه هرگز اثباتِ
    قطعیِ «محتوایِ فعلیِ Registry دقیقاً همان چیزی است که آن‌زمان روی این
    Draft اعمال شد» نیست (نگاه کنید به توضیحِ خودِ آن مسیر)، نوشتنِ آن
    به‌عنوانِ یک عکسِ «دقیق» در ``template_baseline_snapshot`` یک تاریخِ
    ساختگی می‌سازد که granular reset (که به یک عکسِ واقعاً دقیق نیاز دارد)
    را برایِ چنین Draftی به‌اشتباه فعال می‌کند. با ``False``، این تابع
    هم‌چنان appearance/header/footer/صفحات را می‌نویسد (خودِ رفتارِ
    بازنشانی)، اما ``template_baseline_snapshot`` را دست‌نخورده
    (خالی/غایب) رها می‌کند."""
    # --- ۱) اعتبارسنجی/آماده‌سازیِ appearance/header/footer (بدونِ نوشتن) ---
    current_appearance = draft.effective_appearance_config()
    overlay = dict(preset.appearance)
    # Acceptance Batch 1 (post-U11) — correction of the original Phase 6
    # "palette is only ever a suggestion" rule: that rule was written for
    # applying a *legacy* Preset as a one-time content suggestion. A U7/U10
    # Ready Template is a full baseline (composition + appearance + default
    # palette + global variants + provenance) — explicitly applying one is
    # a deliberate merchant action that must replace the *entire* previous
    # baseline, including palette, exactly like it already replaces section
    # composition and header/footer variant below. Leaving a stale palette
    # active after an explicit Template switch produced a real, reported
    # bug (dense_marketplace/dark_digital rendering with whatever palette
    # the store happened to have before). The palette remains a completely
    # free merchant override *after* this point — this only fires at the
    # moment of an explicit apply/reset, never on its own.
    if preset.default_palette_slug is not None:
        overlay["palette_slug"] = preset.default_palette_slug
        # Part 2B (ibolak Home rebuild) — merchant-reported bug: the U7/U10
        # fix above already replaces a stale ``palette_slug``, but
        # ``color_overrides`` is a *separate* dict that takes precedence
        # over the palette's own colors at render time (see
        # ``appearance_registry.resolve_colors``); leaving it untouched let
        # a Store's bootstrap-mirrored ShopSettings colors (see
        # ``bootstrap_service.bootstrap_appearance_config`` —
        # migration-safety carryover, never a deliberate in-editor choice)
        # silently defeat every Ready Template's intended palette forever.
        # Only clear it when it is NOT a genuine merchant customization
        # (``color_overrides_customized`` is set exclusively by the
        # dashboard's own color-editing view — see ``views.py``); a real
        # merchant color choice made *after* bootstrap is respected here
        # exactly like the palette itself is afterward, per this
        # function's own established rule.
        if not current_appearance.get("color_overrides_customized"):
            overlay["color_overrides"] = {}
    overlay["layout_preset_key"] = preset.key
    try:
        cleaned_appearance = _validate_appearance_overlay(current_appearance, overlay)
    except layout_service.AppearanceConfigValidationError as exc:
        raise InvalidPresetError(f"Preset «{preset.key}» نامعتبر است: {exc}") from exc

    try:
        cleaned_header = _validate_header_overlay(draft.effective_header_config(), preset.header)
    except layout_service.HeaderConfigValidationError as exc:
        raise InvalidPresetError(f"Preset «{preset.key}» نامعتبر است: {exc}") from exc

    # Mobile navigation is a global storefront region stored inside the
    # existing footer-config JSON.  Ready Templates are full visual baselines:
    # switching away from a Template that opted into a mobile nav must not let
    # that nav leak into the next Ready Template merely because the older
    # recipe predates this region and therefore has no selector key.  Reset the
    # new region to its registered safe default before applying a Ready
    # Template footer overlay; an explicitly authored selector (dark_digital
    # v2 today, any future Template tomorrow) still wins through the overlay.
    # Non-Ready structural presets keep the historical overlay semantics and
    # therefore preserve a merchant's chosen mobile navigation.
    footer_base = draft.effective_footer_config()
    if preset.is_ready_template and preset.footer is not None:
        footer_base[global_region_registry.GLOBAL_MOBILE_NAV_REGION.variant_setting_key] = (
            global_region_registry.GLOBAL_MOBILE_NAV_REGION.default_variant
        )
    try:
        cleaned_footer = _validate_footer_overlay(footer_base, preset.footer)
    except layout_service.FooterConfigValidationError as exc:
        raise InvalidPresetError(f"Preset «{preset.key}» نامعتبر است: {exc}") from exc

    # --- ۲) آماده‌سازیِ ردیف‌هایِ هر صفحه (بدونِ نوشتن — فقط ساختِ آبجکت) ---
    pages_to_replace = {}
    snapshot_pages = {}
    for page_type, entries in preset.pages.items():
        page = draft.get_page(page_type)
        # Phase 1 correction (spec §37 — Lock): این صفحه به‌طورِ کامل
        # جایگزین می‌شود (زیر را نگاه کنید) — اگر یکی از sectionهایِ فعلی‌اش
        # قفل باشد، اعمالِ Preset باید کاملاً رد شود، نه اینکه بی‌صدا آن
        # section را هم مثلِ بقیه حذف کند.
        if page.sections.filter(is_locked=True).exists():
            raise LockedSectionsPresentError(
                f"Preset «{preset.key}» قابلِ اعمال نیست — صفحه‌ی "
                f"«{page.get_page_type_display()}» بخشِ قفل‌شده دارد؛ ابتدا قفل آن را باز کنید"
            )
        rows = _build_sections_for_page(page, entries, preset=preset, page_type=page_type)
        prepared_container_settings = _container_settings_for_entries(
            entries, preset_key=preset.key, page_type=page_type
        )
        pages_to_replace[page] = (rows, prepared_container_settings)
        container_settings_per_section = _broadcast_container_settings_to_entries(
            entries, prepared_container_settings,
        )
        # Acceptance Batch 2 (post-U11) — the immutable per-page baseline
        # record: exactly what got written to each StorefrontSection below,
        # keyed by the stable slot identity above — this (not a re-read of
        # ``preset.pages`` from the live registry) is what a later granular
        # or whole-storefront reset restores from.
        snapshot_pages[page_type] = [
            {
                "slot_key": row.template_slot_key,
                "section_key": row.section_key,
                "settings": row.settings,
                "row_key": row.row_key,
                "row_span": row.row_span,
                "container_settings": container_settings,
            }
            for row, container_settings in zip(rows, container_settings_per_section)
        ]

    # --- ۳) نوشتن — فقط پس از موفقیتِ کاملِ بخشِ اعتبارسنجی ---
    draft.appearance_config = cleaned_appearance
    # U7 — records exactly which Ready Template baseline (key + version)
    # this Draft was just built from, so a later reset can restore that
    # *recorded* version specifically, not "whatever this preset key
    # currently means" if its Python definition changes in a future release.
    draft.template_provenance = build_template_provenance(
        template_key=preset.key, template_version=preset.version,
    )
    update_fields = ["appearance_config", "template_provenance"]
    if cleaned_header is not None:
        draft.header_config = cleaned_header
        update_fields.append("header_config")
    if cleaned_footer is not None:
        draft.footer_config = cleaned_footer
        update_fields.append("footer_config")
    draft.save(update_fields=update_fields)

    # Phase 4 (Task 1, authority convergence) — a non-Ready structural preset's
    # explicit header_variant/footer_variant overlay must update the typed
    # Store Appearance manifest through the canonical authority primitives,
    # not just the legacy header_config/footer_config mirror written above.
    # The manifest — not header_config/footer_config directly — is the actual
    # render authority (storefront_context_service derives
    # header_variant_template/footer_variant_template from
    # resolve_store_appearance_render_state), so leaving it unsynced meant a
    # merchant's explicit non-Ready preset choice was silently ignored by the
    # rendered storefront. Ready Templates are exempt here: their COMPLETE
    # declared manifest is applied authoritatively below, which already
    # supersedes any per-field sync and must remain the single write for that
    # case (routing both through the same two authority calls would just be
    # redundant, not wrong, but this keeps each preset kind's write path to
    # exactly one canonical call).
    if not preset.store_appearance:
        if preset.header is not None and "header_variant" in preset.header:
            appearance_authority_service.apply_header_variant(
                version=draft, header_variant=cleaned_header["header_variant"],
            )
        footer_variant = None
        mobile_nav_variant = None
        if preset.footer is not None:
            if "footer_variant" in preset.footer:
                footer_variant = cleaned_footer["footer_variant"]
            if "mobile_nav_variant" in preset.footer:
                mobile_nav_variant = cleaned_footer["mobile_nav_variant"]
        if footer_variant is not None or mobile_nav_variant is not None:
            appearance_authority_service.apply_footer_variant(
                version=draft,
                footer_variant=footer_variant,
                mobile_nav_variant=mobile_nav_variant,
            )

    # Phase 1 (Task 5, A02 closure) — persist the Ready Template's COMPLETE
    # declared typed Store Appearance manifest through the canonical authority
    # service. This runs inside apply_preset's own @transaction.atomic
    # boundary (the authority service intentionally owns no transaction), so a
    # later failure still rolls the whole apply back. It is persisted AFTER the
    # ordinary appearance/header/footer writes above so its compatibility
    # mirrors (header/footer/bottom_nav/motion) are the authoritative final
    # selector state and cannot be left stale. Ready Templates always declare a
    # complete manifest; non-Ready presets may omit it, so guard on presence.
    if preset.store_appearance:
        appearance_authority_service.apply_store_appearance_manifest(
            version=draft, manifest=preset.store_appearance
        )

    if _record_baseline_snapshot:
        # Acceptance Batch 2 (post-U11) — Issue 2: an immutable, normalized
        # snapshot of the *exact* baseline just applied — independent of the
        # registry's live ``LayoutPresetDefinition`` for this key, which could
        # (bug or future edit) change its contents without bumping ``version``.
        # See the model field's own docstring for the full motivating risk.
        #
        # Task 5 — the snapshot is built AFTER the complete typed manifest has
        # been persisted above, so ``appearance``/``header_config``/
        # ``footer_config`` capture the manifest-synced state (including the
        # reserved ``store_appearance`` key and its mirrors). This keeps
        # reset-to-baseline returning to the fully-applied recipe DNA rather
        # than reintroducing A02 on reset, and keeps ``_draft_already_matches_preset``
        # (which compares ``appearance_config`` to ``snapshot["appearance"]``) correct.
        draft.template_baseline_snapshot = {
            "template_key": preset.key,
            "template_version": preset.version,
            "default_palette_slug": preset.default_palette_slug,
            "appearance": dict(draft.appearance_config or {}),
            "header_config": dict(draft.header_config) if cleaned_header is not None else None,
            "footer_config": dict(draft.footer_config) if cleaned_footer is not None else None,
            "pages": snapshot_pages,
        }
        draft.save(update_fields=["template_baseline_snapshot"])

    for page, (rows, prepared_container_settings) in pages_to_replace.items():
        # Container/Cell is the new layout layer.  Deleting the page sections
        # leaves old Cells empty via SET_NULL, so replace those Containers too
        # and mirror the Preset's legacy row metadata into fresh placements.
        page.containers.all().delete()
        page.sections.all().delete()
        StorefrontSection.objects.bulk_create(rows)
        container_service.rebuild_page_from_legacy_rows(page)

        containers = list(page.containers.order_by("order", "id"))
        if len(containers) != len(prepared_container_settings):
            raise InvalidPresetError(
                f"Preset «{preset.key}»: تعداد Containerهای ساخته‌شده با داده‌ی Preset هم‌خوان نیست"
            )
        for container, container_settings in zip(containers, prepared_container_settings):
            container.settings = container_settings
        if containers:
            StorefrontContainer.objects.bulk_update(containers, ["settings"])


def apply_preset_by_key(draft: StorefrontLayoutVersion, key: str) -> LayoutPresetDefinition:
    """میان‌بُرِ راحت برایِ لایه‌ی ویو — کلیدِ ناشناخته را قبل از هر تغییری
    fail-closed رد می‌کند."""
    preset = layout_preset_registry.get_layout_preset(key)
    if preset is None:
        raise UnknownPresetError(f"پیش‌تنظیمِ «{key}» یافت نشد")
    apply_preset(draft, preset)
    return preset


class NoTemplateBaselineError(InvalidPresetError):
    """U7 — این Draft هرگز یک Ready Template اعمال‌شده ندارد (هیچ
    ``template_provenance``ای ثبت نشده) — بازنشانی به baseline بی‌معناست
    و هرگز نباید بی‌صدا یک Presetِ دلخواه را حدس بزند."""


class TemplateBaselineVersionChangedError(InvalidPresetError):
    """U7 — کلیدِ Ready Template ثبت‌شده هنوز در Registry هست، اما نسخه‌یِ
    فعلیِ آن (``LayoutPresetDefinition.version``) با نسخه‌یِ ثبت‌شده روی
    این Draft یکی نیست. بازنشانی هرگز بی‌صدا نسخه‌یِ *فعلی* را جایگزینِ
    نسخه‌ای که مرچنت واقعاً روی آن بود نمی‌کند — طبقِ الزامِ صریحِ کارِ U7
    («Reset must restore the selected template VERSION baseline»)."""


def reset_storefront_to_baseline(draft: StorefrontLayoutVersion) -> LayoutPresetDefinition | None:
    """U7 — کلِ فروشگاه (Draft) را به baselineِ همان Ready Template/نسخه‌ای
    که آخرین‌بار رویش اعمال شده بازمی‌گرداند (``draft.template_provenance``).

    Acceptance Batch 2 (post-U11) — Issue 2: منبعِ حقیقتِ محتوا اکنون
    ``draft.template_baseline_snapshot`` است (نه دوباره‌خوانیِ Presetِ
    *فعلی* از Registry) — دقیقاً همان الزامِ صریحِ کار: تغییرِ بعدیِ تعریفِ
    پایتونیِ یک Preset (حتی بدونِ افزایشِ نسخه) دیگر نمی‌تواند نتیجه‌ی
    بازنشانیِ یک Draftِ از‌قبل‌اعمال‌شده را عوض کند. ``layout_preset_registry``
    فقط برایِ *metadata* (مقدارِ برگشتی — نامِ Persianِ Template برایِ پیام
    به کاربر) صدا زده می‌شود، هرگز برایِ خودِ محتوا.

    مسیرِ سازگاریِ عقب‌رو (Draftهایِ ساخته‌شده پیش از این Batch — فقط
    ``template_provenance`` دارند، بدونِ ``template_baseline_snapshot``):
    دوباره‌خوانیِ Preset از Registryِ زنده با چکِ نسخه
    (``TemplateBaselineVersionChangedError`` اگر عوض شده باشد) — همان
    رفتارِ *قبل از این Batch*.

    پستِ‌دمو hardening pass (Issue 4) — تصحیحِ صریح: تطابقِ شماره‌یِ نسخه
    فقط یک سیاستِ سازگاریِ قابل‌قبول است، نه اثباتِ این‌که محتوایِ *فعلیِ*
    Registry دقیقاً همان چیزی است که آن‌زمان رویِ این Draft اعمال شد
    (تعریفِ پایتونیِ همین نسخه می‌توانست، به‌اشتباه/بدونِ افزایشِ نسخه،
    تغییر کرده باشد). به همین دلیل این مسیر دیگر عکسِ بازسازی‌شده از
    Registryِ فعلی را به‌عنوانِ یک ``template_baseline_snapshot`` «دقیق»
    persist نمی‌کند (نگاه کنید به ``apply_preset(..., _record_baseline_snapshot=False)``)
    — این Draft همچنان بدونِ عکسِ baseline می‌ماند، granular reset برایش
    (درست) غیرفعال باقی می‌ماند، و بازنشانیِ *بعدیِ* همین Draft دوباره از
    همین مسیرِ سازگاریِ safe عبور می‌کند، نه این‌که یک تاریخِ ساختگی را
    به‌عنوانِ واقعی بپذیرد.

    Scope (مستندشده، نه یک محدودیتِ پنهان): این تابع خودش هرگز چک‌پوینت/
    تاریخچه نمی‌سازد و همیشه رویِ همان شیءِ ``draft`` که گرفته درجا کار
    می‌کند — نگاه کنید به ``reset_storefront_with_checkpoint`` برایِ
    نقطه‌ی ورودِ مرچنت‌محورِ کامل (چک‌پوینتِ پیش از بازنشانی)."""
    provenance = validate_template_provenance(draft.template_provenance)
    template_key = provenance["template"]["key"]
    template_version = provenance["template"]["version"]
    if not template_key:
        raise NoTemplateBaselineError(
            "این Draft هرگز یک Ready Template اعمال‌شده ندارد — چیزی برای بازنشانی وجود ندارد"
        )

    snapshot = draft.template_baseline_snapshot
    if (
        snapshot
        and snapshot.get("template_key") == template_key
        and snapshot.get("template_version") == template_version
    ):
        apply_baseline_snapshot(draft, snapshot)
        return layout_preset_registry.get_layout_preset(template_key)

    # R4 Task 8 (final-review fix, CRITICAL-1) — a snapshot that EXISTS but
    # does not match this Draft's current provenance is a genuinely
    # different situation than "this Draft never had an accurate snapshot
    # at all" (the legacy-compatibility fallback below). It arises from
    # ``switch_template_preserving_content``: a content-preserving Template
    # Switch deliberately updates ``template_provenance`` to the new
    # Template WITHOUT rebuilding ``template_baseline_snapshot`` (see that
    # function's own docstring — rebuilding it would mean fabricating an
    # exact historical baseline for composition this operation never
    # actually applied). Before this fix, that mismatch fell straight into
    # the fallback below, which re-fetches the new Template from the LIVE
    # registry and does a full ``apply_preset`` — silently wiping every
    # page's composition, including the exact content a content-preserving
    # switch just went out of its way to preserve. A Draft with NO
    # snapshot at all (``snapshot`` falsy) is unaffected by this check and
    # still takes the legacy best-effort path exactly as before.
    if snapshot:
        raise TemplateBaselineVersionChangedError(
            f"عکسِ baselineِ ذخیره‌شده‌یِ این Draft برایِ «{snapshot.get('template_key')}» است، نه «{template_key}» — "
            f"بازنشانیِ خودکارِ کلِ فروشگاه برایِ این وضعیت (مثلاً پس از تعویضِ محتوا-محفوظِ قالب) پشتیبانی نمی‌شود"
        )

    preset = layout_preset_registry.get_layout_preset(template_key)
    if preset is None:
        raise UnknownPresetError(f"Ready Templateِ «{template_key}» دیگر در Registry موجود نیست")
    if preset.version != template_version:
        raise TemplateBaselineVersionChangedError(
            f"نسخه‌ی ثبت‌شده‌ی «{template_version}» برایِ «{template_key}» با نسخه‌ی فعلیِ "
            f"«{preset.version}» یکی نیست — بازنشانیِ خودکار به نسخه‌ای متفاوت مجاز نیست"
        )
    # Issue 4 (پستِ‌دمو hardening pass): این فقط یک بازنشانیِ سازگاریِ
    # best-effort است (Draftی که هرگز عکسِ baselineِ واقعی نداشته) — تطابقِ
    # شماره‌یِ نسخه ثابت نمی‌کند محتوایِ *فعلیِ* Registry دقیقاً همان چیزی
    # است که آن‌زمان اعمال شد؛ پس هرگز نباید به‌عنوانِ یک عکسِ «دقیقِ»
    # تاریخی نوشته/persist شود — طبقِ همان الزامِ صریح: «do NOT fabricate an
    # exact historical baseline». این Draft همچنان بدونِ عکسِ baseline
    # می‌ماند و granular reset برایش (درست) غیرفعال باقی می‌ماند.
    apply_preset(draft, preset, _record_baseline_snapshot=False)
    return preset


@transaction.atomic
def apply_baseline_snapshot(draft: StorefrontLayoutVersion, snapshot: dict) -> None:
    """Acceptance Batch 2 (post-U11) — دقیقاً همان بخشِ «نوشتن» (۳)
    ``apply_preset`` بالا، اما منبعِ حقیقتش عکسِ ذخیره‌شده‌یِ ``snapshot``
    است، نه یک ``LayoutPresetDefinition`` زنده از Registry — این تابع
    هرگز به Registryِ فعلی دست نمی‌زند (نه برایِ appearance/header/footer،
    نه برایِ ترکیبِ صفحات)، پس نتیجه‌اش از تغییرِ بعدیِ تعریفِ پایتونیِ
    همان Preset کاملاً مصون است (الزامِ Issue 2).

    فقط صفحاتی که ``snapshot["pages"]`` صریحاً پوشش می‌دهد بازنویسی
    می‌شوند؛ صفحاتِ دیگر دست‌نخورده می‌مانند — همان قراردادِ ``apply_preset``
    («a preset may omit a page deliberately»)."""
    for page_type in snapshot["pages"]:
        page = draft.get_page(page_type)
        if page.sections.filter(is_locked=True).exists():
            raise LockedSectionsPresentError(
                f"بازنشانی ممکن نیست — صفحه‌ی «{page.get_page_type_display()}» "
                f"بخشِ قفل‌شده دارد؛ ابتدا قفل آن را باز کنید"
            )

    draft.appearance_config = snapshot["appearance"]
    draft.template_provenance = build_template_provenance(
        template_key=snapshot["template_key"], template_version=snapshot["template_version"],
    )
    draft.template_baseline_snapshot = snapshot
    update_fields = ["appearance_config", "template_provenance", "template_baseline_snapshot"]
    if snapshot.get("header_config") is not None:
        draft.header_config = snapshot["header_config"]
        update_fields.append("header_config")
    if snapshot.get("footer_config") is not None:
        draft.footer_config = snapshot["footer_config"]
        update_fields.append("footer_config")
    draft.save(update_fields=update_fields)

    for page_type, section_entries in snapshot["pages"].items():
        page = draft.get_page(page_type)
        page.containers.all().delete()
        page.sections.all().delete()
        rows = [
            StorefrontSection(
                page=page, section_key=entry["section_key"], order=order,
                settings=entry["settings"], row_key=entry["row_key"], row_span=entry["row_span"],
                template_slot_key=entry["slot_key"],
            )
            for order, entry in enumerate(section_entries)
        ]
        StorefrontSection.objects.bulk_create(rows)
        container_service.rebuild_page_from_legacy_rows(page)

        containers = list(page.containers.order_by("order", "id"))
        prepared_container_settings = _container_settings_from_snapshot_sections(section_entries)
        if len(containers) != len(prepared_container_settings):
            raise InvalidPresetError("عکسِ baseline با ساختارِ Container هم‌خوان نیست")
        for container, container_settings in zip(containers, prepared_container_settings):
            container.settings = container_settings
        if containers:
            StorefrontContainer.objects.bulk_update(containers, ["settings"])


def _draft_already_matches_preset(draft: StorefrontLayoutVersion, preset: LayoutPresetDefinition) -> bool:
    """پستِ‌دمو hardening pass (Issue 6) — آیا دوباره‌اعمالِ همین دقیقاً
    Preset رویِ این Draft هیچ تغییرِ واقعی‌ای ایجاد می‌کند؟ فقط وقتی
    ``True`` برمی‌گرداند که بتوان با اطمینانِ کامل اثبات کرد — در غیرِ
    این‌صورت (از جمله Draftِ legacyِ بدونِ عکسِ دقیق — Issue 4) محافظه‌کارانه
    ``False`` برمی‌گرداند تا مسیرِ امنِ همیشگی (چک‌پوینت + اعمال) اجرا شود؛
    یک چک‌پوینتِ زائدِ اضافی هرگز خطرناک نیست، اما رد کردنِ یک تغییرِ
    واقعی به‌اشتباه (به‌عنوانِ no-op) می‌تواند تغییرِ دستیِ مرچنت را بدونِ
    چک‌پوینت از بین ببرد."""
    provenance = draft.template_provenance or {}
    template = provenance.get("template") or {}
    if template.get("key") != preset.key or template.get("version") != preset.version:
        return False

    snapshot = draft.template_baseline_snapshot
    if not snapshot or snapshot.get("template_key") != preset.key or snapshot.get("template_version") != preset.version:
        return False

    if draft.appearance_config != snapshot["appearance"]:
        return False
    if snapshot.get("header_config") is not None and draft.header_config != snapshot["header_config"]:
        return False
    if snapshot.get("footer_config") is not None and draft.footer_config != snapshot["footer_config"]:
        return False

    for page_type, entries in snapshot["pages"].items():
        page = draft.get_page(page_type)
        current_sections = list(page.sections.order_by("order", "id"))
        if len(current_sections) != len(entries):
            return False
        for section, entry in zip(current_sections, entries):
            if (
                section.section_key != entry["section_key"]
                or section.settings != entry["settings"]
                or section.row_key != entry["row_key"]
                or section.row_span != entry["row_span"]
                or section.template_slot_key != entry["slot_key"]
            ):
                return False
    return True


@transaction.atomic
def apply_preset_with_checkpoint(store, preset: LayoutPresetDefinition, *, user=None) -> StorefrontLayoutVersion:
    """Acceptance Batch 2 (post-U11) — Issue 1: نقطه‌ی ورودِ مرچنت‌محورِ
    اعمال/تعویضِ یک Ready Template. برخلافِ ``apply_preset`` (که همیشه
    رویِ یک Draftِ صریحاً‌گرفته‌شده درجا mutate می‌کند)، این تابع ابتدا
    محتوایِ *فعلیِ* Draft را (اگر واقعاً معنادار باشد) به‌عنوانِ یک
    چک‌پوینتِ قابل‌بازیابی در تاریخچه‌یِ نسخه‌ها نگه می‌دارد
    (``layout_service.checkpoint_draft_before_replacement``)، و تازه بعد
    از آن Presetِ جدید را رویِ Draftِ فعالِ (احتمالاً تازه) اعمال می‌کند.

    پستِ‌دمو hardening pass (Issue 6) — same-template no-op: اگر همین
    دقیقاً Preset (کلید+نسخه) از قبل، بدونِ هیچ انحرافی، رویِ همین Draft
    اعمال شده — یعنی دوباره اعمال‌کردنش هیچ تغییرِ واقعی‌ای نمی‌دهد —
    هیچ چک‌پوینت/Draftِ جدیدی ساخته نمی‌شود؛ همان Draftِ فعلی بدونِ
    تغییر برگردانده می‌شود. این فقط برایِ جلوگیری از شلوغیِ بی‌فایده‌یِ
    تاریخچه است، نه یک بهینه‌سازیِ کارایی — هرجا کوچک‌ترین ابهامی باشد
    (مثلاً Draftِ legacyِ بدونِ عکسِ دقیق)، مسیرِ همیشگیِ چک‌پوینت+اعمال
    اجرا می‌شود.

    نسخه‌ی منتشرشده هرگز لمس نمی‌شود؛ هرگز خودکار publish نمی‌کند — دقیقاً
    همان تضمینِ ``restore_version``."""
    current_draft = layout_service.get_or_create_draft(store, user=user)
    if _draft_already_matches_preset(current_draft, preset):
        return current_draft

    draft = layout_service.checkpoint_draft_before_replacement(
        store, reason_label=f"پیش از اعمال قالب «{preset.label_fa}»", user=user,
    )
    apply_preset(draft, preset)
    return draft


@transaction.atomic
def switch_template_preserving_content(store, preset: LayoutPresetDefinition, *, user=None) -> StorefrontLayoutVersion:
    """R4 Task 8 — content-preserving Template Switch: apply a Ready
    Template's appearance/DNA (ordinary appearance overlay, header/footer
    config, and the COMPLETE typed Store-Appearance manifest) WITHOUT
    replacing page composition at all.

    This is a genuinely different operation from ``apply_preset_with_
    checkpoint`` above (which replaces both DNA *and* composition for
    every page the preset's recipe covers) — it exists because a merchant
    who has already authored real content under one Template must be able
    to switch to another Template's *visual identity* without losing that
    work. It reuses, never re-implements, the two already-canonical
    primitives this needs:

    - ``layout_service.checkpoint_draft_before_replacement`` — same
      recoverable-checkpoint machinery ``apply_preset_with_checkpoint``/
      ``reset_page_with_checkpoint``/``reset_storefront_with_checkpoint``
      already use. It returns a FULL CLONE of the current Draft's content
      (all six pages, every Section/Container/Cell) as the new active
      Draft — this is precisely the content-preservation mechanism: we
      never touch composition, so the clone IS the preserved content.
    - ``appearance_authority_service.apply_ready_template_appearance`` —
      the canonical, already-tested Ready-Template DNA-application
      primitive (Phase 1, Task 2) that had zero production callers before
      this — explicitly documented as NOT replacing page composition,
      provenance, or baseline snapshots, which is exactly the contract
      this function needs.

    ``template_provenance`` IS updated (so the Template Gallery/R4 UI
    correctly shows the new Template as "current" and future switches
    compare against it) — but ``template_baseline_snapshot`` is
    deliberately left untouched: it is a record of which section-level
    content was actually baseline-applied and can be granularly reset to,
    and this function never applies Template B's composition, so writing
    a snapshot claiming otherwise would be exactly the kind of dishonest
    "fabricated baseline" ``apply_preset``'s own ``_record_baseline_
    snapshot=False`` path already goes out of its way to avoid. The
    practical consequence — granular reset-to-baseline after a content-
    preserving switch still restores a page/section to Template A's
    (still-accurate) recorded baseline, not Template B's — is a known,
    deliberate limitation, not an oversight: it never destroys anything,
    it only means "reset to baseline" continues to mean what it already
    recorded."""
    if not preset.is_ready_template:
        raise InvalidPresetError(
            f"«{preset.label_fa}» یک Ready Template نیست — تعویضِ محتوا-محفوظ فقط برایِ Ready Templateها معنادار است"
        )
    draft = layout_service.checkpoint_draft_before_replacement(
        store, reason_label=f"پیش از تعویضِ محتوا-محفوظِ قالب «{preset.label_fa}»", user=user,
    )
    appearance_authority_service.apply_ready_template_appearance(version=draft, preset=preset)
    draft.template_provenance = build_template_provenance(
        template_key=preset.key, template_version=preset.version,
    )
    draft.save(update_fields=["template_provenance", "updated_at"])
    return draft


@transaction.atomic
def reset_storefront_with_checkpoint(store, *, user=None) -> StorefrontLayoutVersion:
    """Acceptance Batch 2 (post-U11) — Issue 3، «RESET STOREFRONT» با
    یکپارچگیِ تاریخچه‌یِ الزامیِ همان بخش: پیش از بازنشانیِ کاملِ فروشگاه،
    وضعیتِ فعلی را چک‌پوینت می‌کند (اگر معنادار باشد)، سپس
    ``reset_storefront_to_baseline`` را رویِ Draftِ فعالِ (احتمالاً تازه)
    اجرا می‌کند."""
    current_draft = layout_service.get_or_create_draft(store, user=user)
    # Fail fast on "nothing to reset" *before* creating a checkpoint that
    # would then immediately become pointless.
    provenance = validate_template_provenance(current_draft.template_provenance)
    if not provenance["template"]["key"]:
        raise NoTemplateBaselineError(
            "این Draft هرگز یک Ready Template اعمال‌شده ندارد — چیزی برای بازنشانی وجود ندارد"
        )
    draft = layout_service.checkpoint_draft_before_replacement(
        store, reason_label="پیش از بازنشانیِ کل ظاهر فروشگاه به قالب", user=user,
    )
    reset_storefront_to_baseline(draft)
    return draft


@transaction.atomic
def reset_page_with_checkpoint(store, page_type: str, *, user=None) -> StorefrontLayoutVersion:
    """Acceptance Batch 2 (post-U11) — Issue 3، «RESET PAGE» با یکپارچگیِ
    تاریخچه‌یِ الزامیِ همان بخش — همان الگویِ ``reset_storefront_with_checkpoint``،
    محدود به یک صفحه‌یِ مشخص."""
    draft = layout_service.checkpoint_draft_before_replacement(
        store, reason_label=f"پیش از بازنشانیِ صفحه به قالب", user=user,
    )
    reset_page_to_baseline(draft, page_type)
    return draft


def _baseline_snapshot_or_raise(draft: StorefrontLayoutVersion) -> dict:
    snapshot = draft.template_baseline_snapshot
    if not snapshot:
        raise NoTemplateBaselineError(
            "این Draft عکسِ baselineِ ذخیره‌شده‌ای ندارد — یا هرگز یک Ready Template "
            "اعمال نشده، یا این Draft پیش از این Batch ساخته شده (بازنشانیِ granular "
            "برایِ آن پشتیبانی نمی‌شود، فقط بازنشانیِ کلِ فروشگاه با مسیرِ سازگاریِ عقب‌رو)"
        )
    return snapshot


def _find_baseline_section_entry(snapshot: dict, page_type: str, slot_key: str) -> dict | None:
    for entry in snapshot.get("pages", {}).get(page_type, []):
        if entry["slot_key"] == slot_key:
            return entry
    return None


def reset_section_to_baseline(draft: StorefrontLayoutVersion, section: StorefrontSection) -> None:
    """Issue 3 — RESET SECTION. این section را دقیقاً به
    section_key/settings/row_key/row_span ثبت‌شده در baseline بازمی‌گرداند
    — با ``template_slot_key`` (نه موقعیتِ فعلیِ section در فهرست) پیدا
    می‌شود، پس بعد از بازچینی/درج/حذفِ sectionهایِ دیگر هم درست کار
    می‌کند. ``is_active``/``is_locked``/``collapsed_in_editor`` (وضعیتِ
    ادیتور، نه محتوا) دست‌نخورده می‌مانند. هیچ section دیگری تغییر
    نمی‌کند.

    محدودیتِ شناخته‌شده و مستندشده (پستِ‌دمو hardening pass، Issue 7 —
    ممیزیِ صریح پیش از تغییر): این تابع عضویتِ فعلیِ section در
    Container/Cell (این‌که در کدام Cell/کدام Container قرار دارد،
    ``order``ِ آن در صفحه) را عمداً دست‌نخورده می‌گذارد — فقط row_key/
    row_span (که خودِ Cell/Containerِ فعلی از رویِ آن‌ها بازسازی می‌شود)
    را بازمی‌گرداند. دلیل: هر Container/Cell معمولاً چندین section را
    هم‌زمان در بر می‌گیرد (اعضایِ دیگرِ همان گروه‌بندی)، و هیچ راهِ امنی
    برایِ «فقط این یک section را به Cellِ baselineِ خودش برگردان» وجود
    ندارد بدونِ خطرِ دست‌کاریِ عضویتِ sectionهایِ دیگر (از جمله
    sectionهایِ کاملاً دستیِ مرچنت که ممکن است حالا در همان Container/Cell
    نشسته باشند) — دقیقاً همان الزامِ صریحِ کار: «Do NOT blindly rebuild
    the whole page for a single-section reset» و «preserve unrelated
    merchant-created sections». اگر مرچنت این section را به‌صورتِ دستی به
    Cell/Containerِ دیگری منتقل کرده باشد، بازنشانیِ این section محتوای
    آن را به baseline برمی‌گرداند اما آن را در همان Container/Cellِ
    فعلی‌اش نگه می‌دارد — این استثنایِ شناخته‌شده و پذیرفته‌شده است، نه
    یک باگ؛ بازگردانیِ کاملِ چیدمانِ Container/Cell فقط از طریقِ
    ``reset_page_to_baseline``/``reset_storefront_to_baseline`` (که کلِ
    صفحه/فروشگاه را عمداً بازمی‌سازند) ممکن است."""
    if not section.template_slot_key:
        raise NotABaselineSectionError(
            "این بخش هرگز از یک Ready Template baseline نیامده — محتوایِ کاملاً دستیِ "
            "مرچنت است؛ چیزی برایِ بازنشانی به قالب وجود ندارد"
        )
    snapshot = _baseline_snapshot_or_raise(draft)
    entry = _find_baseline_section_entry(snapshot, section.page.page_type, section.template_slot_key)
    if entry is None:
        raise BaselineSlotNotFoundError(
            "جایگاهِ baselineِ این بخش دیگر در عکسِ ذخیره‌شده موجود نیست — احتمالاً یک "
            "Ready Templateِ دیگر از آن پس اعمال شده"
        )
    section.section_key = entry["section_key"]
    section.settings = entry["settings"]
    section.row_key = entry["row_key"]
    section.row_span = entry["row_span"]
    section.save(update_fields=["section_key", "settings", "row_key", "row_span", "updated_at"])


def reset_section_setting_to_baseline(draft: StorefrontLayoutVersion, section: StorefrontSection, key: str) -> None:
    """Issue 3 — RESET FIELD / RESET COMPONENT for a section's own
    ``settings``. Both are the same operation in this architecture: a
    "component" (e.g. ``card``, ``responsive``, ``background``) is just a
    named, possibly-nested key inside ``settings`` — restoring it wholesale
    while leaving every sibling key (other fields, other components) alone
    is exactly what a scalar field-reset does too. Never touches any other
    section."""
    if not section.template_slot_key:
        raise NotABaselineSectionError(
            "این بخش هرگز از یک Ready Template baseline نیامده — چیزی برایِ بازنشانی وجود ندارد"
        )
    snapshot = _baseline_snapshot_or_raise(draft)
    entry = _find_baseline_section_entry(snapshot, section.page.page_type, section.template_slot_key)
    if entry is None:
        raise BaselineSlotNotFoundError(
            "جایگاهِ baselineِ این بخش دیگر در عکسِ ذخیره‌شده موجود نیست"
        )
    baseline_settings = entry["settings"]
    if key not in baseline_settings:
        raise BaselineFieldNotFoundError(f"فیلدِ «{key}» در baselineِ این بخش وجود ندارد")
    new_settings = dict(section.settings or {})
    new_settings[key] = baseline_settings[key]
    section.settings = new_settings
    section.save(update_fields=["settings", "updated_at"])


def reset_appearance_setting_to_baseline(draft: StorefrontLayoutVersion, key: str) -> None:
    """Issue 3 — RESET FIELD for a top-level ``appearance_config`` key
    (e.g. ``font``, ``density``, ``palette_slug``) — restores only that
    key to its Template baseline value, re-validated through the same
    ``validate_appearance_config`` every other appearance write goes
    through; every sibling appearance field is left exactly as the
    merchant last set it."""
    snapshot = _baseline_snapshot_or_raise(draft)
    baseline_appearance = snapshot.get("appearance") or {}
    if key not in baseline_appearance:
        raise BaselineFieldNotFoundError(f"فیلدِ «{key}» در baselineِ ظاهر وجود ندارد")
    new_appearance = dict(draft.effective_appearance_config())
    new_appearance[key] = baseline_appearance[key]
    cleaned = layout_service.validate_appearance_config(new_appearance)
    draft.appearance_config = cleaned
    draft.save(update_fields=["appearance_config", "updated_at"])


@transaction.atomic
def reset_page_to_baseline(draft: StorefrontLayoutVersion, page_type: str) -> None:
    """Issue 3 — RESET PAGE. Restores only ``page_type``'s baseline
    section composition (types, settings, ordering, Container layout) —
    an intentional full replacement of that one page, exactly like
    ``apply_preset``'s own per-page replacement, scoped to a single page.
    A merchant-created section added to this same page does NOT survive a
    page reset — this is the documented, explicit-confirmation-gated
    exception to "granular reset never touches merchant content" (see the
    execution ledger's Batch 2 entry). Other pages, and global header/
    footer, are never touched."""
    snapshot = _baseline_snapshot_or_raise(draft)
    section_entries = snapshot.get("pages", {}).get(page_type)
    if section_entries is None:
        raise UnknownBaselinePageError(
            f"صفحه‌ی «{page_type}» بخشی از baselineِ Ready Templateِ اعمال‌شده روی این Draft نیست"
        )
    page = draft.get_page(page_type)
    if page.sections.filter(is_locked=True).exists():
        raise LockedSectionsPresentError(
            f"بازنشانی ممکن نیست — صفحه‌ی «{page.get_page_type_display()}» بخشِ قفل‌شده دارد؛ "
            f"ابتدا قفل آن را باز کنید"
        )
    page.containers.all().delete()
    page.sections.all().delete()
    rows = [
        StorefrontSection(
            page=page, section_key=entry["section_key"], order=order,
            settings=entry["settings"], row_key=entry["row_key"], row_span=entry["row_span"],
            template_slot_key=entry["slot_key"],
        )
        for order, entry in enumerate(section_entries)
    ]
    StorefrontSection.objects.bulk_create(rows)
    container_service.rebuild_page_from_legacy_rows(page)

    containers = list(page.containers.order_by("order", "id"))
    prepared_container_settings = _container_settings_from_snapshot_sections(section_entries)
    if len(containers) != len(prepared_container_settings):
        raise InvalidPresetError("عکسِ baseline با ساختارِ Container هم‌خوان نیست")
    for container, container_settings in zip(containers, prepared_container_settings):
        container.settings = container_settings
    if containers:
        StorefrontContainer.objects.bulk_update(containers, ["settings"])


def reset_header_to_baseline(draft: StorefrontLayoutVersion) -> None:
    """Issue 3 — RESET HEADER. Never touches footer or any page."""
    snapshot = _baseline_snapshot_or_raise(draft)
    baseline_header = snapshot.get("header_config")
    if baseline_header is None:
        raise NoHeaderBaselineError("این Ready Template پیکربندیِ هدرِ مشخصی تعریف نکرده")
    draft.header_config = baseline_header
    draft.save(update_fields=["header_config", "updated_at"])


def reset_footer_to_baseline(draft: StorefrontLayoutVersion) -> None:
    """Issue 3 — RESET FOOTER. Never touches header or any page."""
    snapshot = _baseline_snapshot_or_raise(draft)
    baseline_footer = snapshot.get("footer_config")
    if baseline_footer is None:
        raise NoFooterBaselineError("این Ready Template پیکربندیِ فوترِ مشخصی تعریف نکرده")
    draft.footer_config = baseline_footer
    draft.save(update_fields=["footer_config", "updated_at"])
