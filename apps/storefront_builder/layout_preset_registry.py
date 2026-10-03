"""Layout Preset Registry — Phase 6: پیش‌تنظیمِ چندصفحه‌ایِ سازنده‌ی V2.

**این ماژول جایگزین/گسترشِ ``preset_registry.py`` نیست.** طبقِ تصمیمِ
مالک ۸ (``docs/architecture/STOREFRONT_BUILDER_V2_REUSE_MATRIX.md:35``)،
``preset_registry.py``/``family_registry.py`` منجمدند — هیچ ورودیِ تازه‌ای
به آن‌ها اضافه نمی‌شود. آن سیستم یک بسته‌یِ توکن *درونِ یک Family خاص*
است (``PresetDefinition.family_slug`` الزامی) و فقط صفحه‌ی اصلی را
می‌پوشاند. این ماژول یک مفهومِ کاملاً جدا و مستقل از Family است — یک
``LayoutPresetDefinition`` روی موتورِ یکتای Universal (همان چیزی که
Phaseهای ۰.۵ تا ۵ ساختند) کار می‌کند، هر ۶ نوع صفحه را می‌تواند بپوشاند،
و هرگز به یک Family خاص قفل نمی‌شود (طبقِ الزامِ صریحِ کار: «Preset X
should not automatically become Family X»).

Preset **داده** است، نه یک Renderer/Family جدید (spec §5.7: «A preset is
data, not a new family implementation»). اعمالِ آن هرگز:

- رنگ را تغییر نمی‌دهد (``palette_slug``/``color_overrides`` مستقلِ کاملاً
  جدا می‌مانند — تصمیمِ مالک: «Palette همیشه Global می‌ماند»؛ اینجا فقط
  یک Paletteِ *پیشنهادی* حمل می‌شود، نه یک قفل)؛
- شناسه‌ی محصول/دسته/کالکشنِ مشخصی را در جایی ذخیره نمی‌کند (طبقِ الزامِ
  صریحِ کار «Reference Safety» — نگاه کنید به Phase 6 Audit، بخشِ ۲۱)؛
- خارج از Draft چیزی را لمس نمی‌کند (اعمال، کاملاً وظیفه‌ی
  ``services/preset_service.py`` است، نه اینجا).

الگویِ این فایل عمداً همانِ الگویِ ``section_registry.py``/
``family_registry.py``/``appearance_registry.py``/``preset_registry.py``
است: یک دیکشنریِ ثابتِ پایتونی، Store-agnostic، بدونِ وابستگی به مدل/
دیتابیس (پس امن است در هر لحظه‌ای import شود، حتی پیش از آماده‌شدنِ
اپ‌هایِ Django) — طراحی‌شده/بازبینی‌شده توسطِ تیمِ پلتفرم، نه چیزی که
مرچنت بسازد.

اعتبارسنجیِ **شکلِ ترکیبِ section/page** (که فقط به ``section_registry``ی
کاملاً خالص وابسته است) همین‌جا، در زمانِ import انجام می‌شود — دقیقاً
همان فلسفه‌ی ``_finalize_registry``. اعتبارسنجیِ header/footer/appearance
(که به ``services/layout_service`` و از آن‌جا به مدل‌هایِ Django وابسته
است) عمداً اینجا انجام نمی‌شود — در ``services/preset_service.validate_layout_preset``
است، هم برایِ جلوگیری از هرگونه وابستگیِ چرخه‌ای، هم چون همان لایه دقیقاً
همان اعتبارسنج‌هایی را دارد که ادیتورِ Header/Footer/Appearance از قبل
مصرف می‌کند."""

from __future__ import annotations

import dataclasses
import re

from . import section_registry
from .storefront_appearance.validation import validate_store_appearance_manifest


class InvalidLayoutPresetError(Exception):
    """یک ``LayoutPresetDefinition`` ساخته‌شده (کدِ پلتفرم، نه ورودیِ مرچنت)
    شکلِ نامعتبر دارد — همیشه در زمانِ import رخ می‌دهد، هرگز در زمانِ
    اجرا برایِ یک مرچنتِ واقعی (طبقِ الزامِ صریحِ کار: «Invalid built-in
    Presets should fail tests/startup validation rather than fail at
    runtime»)."""


@dataclasses.dataclass(frozen=True)
class PresetSectionEntry:
    """یک ردیفِ چیدمانِ پیشنهادیِ Preset برایِ یک section — دقیقاً همان شکلِ
    خروجیِ ``bootstrap_service.build_default_non_home_sections`` (بدونِ
    ``order`` صریح؛ ترتیب همانِ ترتیبِ فهرست است)."""

    section_key: str
    #: None یعنی «از ``default_settings()`` خودِ این نوع section استفاده
    #: کن» — اکثرِ Presetهای ساخته‌شده در این فاز از همین حالت استفاده
    #: می‌کنند (طبقِ الزامِ صریحِ کار: هرگز ID فروشگاه‌محور را در یک
    #: Preset سراسری Hard-code نکن). فقط اگر واقعاً لازم باشد یک مقدارِ
    #: enum-محورِ خنثی (مثلاً ``data_source: "newest"``) تغییر کند، یک
    #: دیکشنریِ *جزئی* اینجا می‌آید — ``validate_settings`` خودِ آن نوع،
    #: کلیدهایِ غایب را با پیش‌فرضِ امنِ خودشان پر می‌کند.
    settings: dict | None = None
    #: Phase 3 (Universal Storefront — V5 Golden Homepage) — عضویتِ ردیفِ
    #: ترکیبی (``row_service``/Phase 1 معماری). خالی (پیش‌فرض) یعنی
    #: section مستقل/عرضِ کامل — دقیقاً همان معنایی که خودِ مدل دارد؛ یک
    #: Preset که هرگز از ردیفِ ترکیبی استفاده نمی‌کند (اکثریتِ Presetهای
    #: قبل از این فاز) بدونِ هیچ تغییری همچنان معتبر می‌ماند.
    row_key: str = ""
    row_span: int = 12
    #: Optional generic settings for the Container created for this standalone
    #: entry or contiguous row run. Presets stay pure data; no Store IDs or
    #: renderer-specific hooks belong here.
    container_settings: dict | None = None
    #: Architecture Convergence / Phase 1 — cross-template SEMANTIC identity of
    #: this recipe row. Pure recipe metadata (NO database field/model/migration/
    #: separate registry): it is the one canonical way to decide that two rows in
    #: two *different* Ready Templates represent the same merchant concept (e.g.
    #: ``hero.primary``), independent of section_key and independent of the
    #: positional ``template_slot_key`` (``key:vN:page:index``). ``None`` (default)
    #: is legitimate for legacy/non-Ready structural presets; every Ready Template
    #: row must carry an explicit, non-empty, per-page-unique role — enforced at
    #: registration time (see ``_validate_semantic_slot_keys``). The canonical
    #: token→role / (page,section)→role mapping lives with the A8 recipe
    #: construction authority (``a8_ready_templates``); it is never reproduced in
    #: a service.
    semantic_slot_key: str | None = None


@dataclasses.dataclass(frozen=True)
class LayoutPresetDefinition:
    key: str
    label_fa: str
    description_fa: str
    #: U7 — Ready Template baseline version. A ``LayoutPresetDefinition`` is
    #: itself the "versioned recipe" the master contract calls a Ready
    #: Template (page composition + appearance + header/footer overlay,
    #: already the exact same shape U10's 8 Ready Templates need) — this
    #: field is the missing piece that lets ``preset_service.apply_preset``
    #: record *which* baseline a Draft is currently built from
    #: (``variant_contract.build_template_provenance``), so a later reset
    #: can restore that exact recorded version rather than "whatever this
    #: preset key currently means" (which could have changed under a store
    #: if the preset's own Python definition is edited in a future release).
    #: A plain string (not int) to match ``build_template_provenance``'s
    #: existing ``template_version: str | None`` contract.
    version: str = "1"
    #: Acceptance Batch 1 (post-U11) — the explicit registry-level
    #: distinction the master contract asked for: ``True`` only for
    #: official Ready Template recipe keys. ``False`` (default) for
    #: the 5 historical/internal presets (``clean_minimal``/
    #: ``editorial_story``/``dense_catalog``/``premium_boutique``/
    #: ``v5_golden_homepage``) — they remain fully registered and
    #: applicable (Advanced mode, `apply-preset` endpoint, tests), just not
    #: surfaced on the normal merchant-facing Ready Template Gallery. A
    #: plain boolean rather than a separate second registry/file, so a
    #: future Ready Template only ever needs this one flag, not a parallel
    #: structure to keep in sync.
    is_ready_template: bool = False
    #: A8 — the complete, typed Store Appearance recipe applied with a Ready
    #: Template. Every official identity, including retained history, carries
    #: a strict schema-v1 manifest.
    store_appearance: dict | None = None
    #: فقط کلیدهایِ ساختاریِ ``appearance_config`` (هرگز رنگ) — زیرمجموعه‌ای
    #: از: font/radius/button_radius/density/motion/type_scale/button_style/
    #: image_fit/image_hover/card_image_crossfade/card_image_zoom. کلیدِ
    #: غایب یعنی «دست‌نخورده بماند» (نه بازنشانی به پیش‌فرضِ پلتفرم) —
    #: منطقِ merge در ``preset_service.apply_preset`` است.
    appearance: dict = dataclasses.field(default_factory=dict)
    #: Acceptance Batch 1 (post-U11) correction — this is the Ready
    #: Template's *default baseline* palette, applied unconditionally by
    #: ``preset_service.apply_preset`` whenever an explicit apply/reset
    #: happens (see that function's own docstring for why the older
    #: "only if the merchant has no palette yet" rule was wrong for an
    #: explicit Template switch). The merchant remains completely free to
    #: change the palette afterward — this only ever fires at apply/reset
    #: time, never on its own.
    default_palette_slug: str | None = None
    #: کلیدهایِ جزئیِ ``header_config``/``footer_config`` — دقیقاً همان
    #: قراردادِ ``layout_service.validate_header_config``/
    #: ``validate_footer_config``؛ کلیدِ غایب یعنی دست‌نخورده بماند
    #: (شاملِ ``announcement_text`` — یک Preset هرگز متنِ تبلیغاتیِ
    #: مرچنت را می‌نویسد/پاک نمی‌کند).
    header: dict | None = None
    footer: dict | None = None
    #: چیدمانِ پیشنهادیِ هرکدام از (حداکثر) شش نوع صفحه — کلیدهایِ
    #: ``section_registry.ALL_PAGE_TYPES``. یک ``page_type`` غایب یعنی
    #: «این Preset عمداً این صفحه را دست‌نخورده می‌گذارد» (طبقِ الزامِ
    #: صریحِ کار: «A preset may omit a page deliberately»).
    pages: dict[str, tuple[PresetSectionEntry, ...]] = dataclasses.field(default_factory=dict)
    #: ``None`` یعنی «با هر فروشگاهی روی پوسته‌ی Universal (V2) سازگار
    #: است» — Familyهای قدیمی هرگز از موتورِ V2 عبور نمی‌کنند، پس اصلاً
    #: مشمولِ این فهرست نیستند (طبقِ الزامِ صریحِ کار: «Preset X should
    #: not automatically become Family X» — اینجا هیچ کوپلینگِ ۱:۱ای
    #: با Family تعریف نشده، برخلافِ ``preset_registry.PresetDefinition``یِ
    #: منجمد).
    compatible_families: frozenset[str] | None = None


LAYOUT_PRESET_REGISTRY: dict[str, LayoutPresetDefinition] = {}
LAYOUT_PRESET_VERSION_REGISTRY: dict[tuple[str, str], LayoutPresetDefinition] = {}


_NUMERIC_VERSION_RE = re.compile(r"^[1-9][0-9]*$")

#: Architecture Convergence / Phase 1 — normalized ``semantic_slot_key`` syntax:
#: a lowercase ``<domain>.<qualifier>[.<qualifier>...]`` role, never a bare word
#: and never a positional/index-derived value.
_SEMANTIC_SLOT_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")


def authored_legacy_home(
    template_key: str, entries: tuple, logical_names: tuple[str, ...],
) -> tuple:
    """Explicitly stamp a retained pre-A8 hand-built Ready Template's HOME rows
    with UNRESOLVED-legacy semantic roles, authored here in recipe source.

    These eight recipes predate the ratified A8 composition-token mapping, so a
    row's cross-template semantic identity cannot be proved from an approved
    source. Rather than *infer* a role from ``section_key`` or list index (a
    heuristic — forbidden: UNKNOWN/AMBIGUOUS ⇒ PRESERVE, NEVER GUESS), each row
    is given an explicit ``legacy_unresolved.<template_key>.<logical_name>``
    role. The ``legacy_unresolved`` domain plus the embedded template identity
    guarantee such a role can never accidentally equal a ratified A8 role
    (e.g. ``hero.primary``) or another template's legacy role — so switching this
    content onto a ratified A8 Template resolves NO semantic match and the
    content is preserved (fail safe), never falsely aligned. ``logical_names``
    is authored, per-recipe, per-page-unique source data (never index/section_key
    derived); this helper only pairs it with the rows in order and validates the
    lengths match — it never manufactures a missing name.
    """
    entries = tuple(entries)
    if len(entries) != len(logical_names):
        raise InvalidLayoutPresetError(
            f"Ready Template «{template_key}»: تعداد نام‌های منطقیِ اسلات با ردیف‌های "
            f"صفحه‌ی اصلی هم‌خوان نیست ({len(logical_names)} != {len(entries)})"
        )
    return tuple(
        dataclasses.replace(entry, semantic_slot_key=f"legacy_unresolved.{template_key}.{name}")
        for entry, name in zip(entries, logical_names)
    )


def _validate_semantic_slot_keys(definition: "LayoutPresetDefinition") -> None:
    """Ready Template validation for the cross-template semantic contract.

    Runs only for ``is_ready_template`` definitions (legacy/non-Ready structural
    presets may legitimately keep ``None`` roles). Every row must carry a
    non-empty, syntactically valid role, and a role must be unique within one
    page — a duplicate semantic role on a single page is a fail-closed
    registration error, exactly like every other built-in-preset shape error in
    this module (never a runtime error for a real merchant).
    """
    if not definition.is_ready_template:
        return
    for page_type, entries in definition.pages.items():
        seen: dict[str, int] = {}
        for index, entry in enumerate(entries):
            role = entry.semantic_slot_key
            if role is None or not str(role).strip():
                raise InvalidLayoutPresetError(
                    f"Ready Template «{definition.key}»: ردیفِ «{entry.section_key}» "
                    f"در صفحه‌ی «{page_type}» باید semantic_slot_key صریح داشته باشد"
                )
            if not _SEMANTIC_SLOT_KEY_RE.fullmatch(str(role)):
                raise InvalidLayoutPresetError(
                    f"Ready Template «{definition.key}»: semantic_slot_key «{role}» "
                    f"نحوِ نامعتبر دارد (باید <domain>.<qualifier> باشد)"
                )
            if role in seen:
                raise InvalidLayoutPresetError(
                    f"Ready Template «{definition.key}»: نقشِ معناییِ تکراری «{role}» "
                    f"در صفحه‌ی «{page_type}» (ایندکس {seen[role]} و {index})"
                )
            seen[role] = index


def _complete_store_appearance(
    *, header: str, hero: str, layout: str, product_view: str, card: str,
    badge: str, motion: str, footer: str, bottom_nav: str,
) -> dict:
    """Complete DNA for the retained pre-A8 official recipe versions."""

    return {
        "schema_version": 1,
        "selections": {
            "header": f"header.{header}.v1",
            "mega_menu": "mega_menu.none.v1",
            "hero": f"hero.{hero}.v1",
            "layout": f"layout.{layout}.v1",
            "product_view": f"product_view.{product_view}.v1",
            "card": f"card.{card}.v1",
            "badge": f"badge.{badge}.v1",
            "motion": f"motion.{motion}.v1",
            "footer": f"footer.{footer}.v1",
            "bottom_nav": f"bottom_nav.{bottom_nav}.v1",
            # P5-W2 — Theme is now a known family; a complete manifest must
            # carry it. Retained recipes never auto-assign an occasion.
            "theme": "theme.none.v1",
        },
        "settings": {},
    }


def register_layout_preset(definition: LayoutPresetDefinition) -> None:
    # Every Ready Template must carry EXPLICIT, per-page-unique semantic roles
    # authored in recipe source (A8 recipes via the ratified token/page mapping;
    # retained hand-built recipes via ``authored_legacy_home`` + the ratified
    # non-home mapping). Registration validation fails closed on any missing or
    # duplicate role — it never manufactures semantic metadata.
    _validate_page_composition_shape(definition)
    _validate_ready_template_store_appearance(definition)
    _validate_semantic_slot_keys(definition)

    identity = (definition.key, definition.version)
    if identity in LAYOUT_PRESET_VERSION_REGISTRY:
        raise InvalidLayoutPresetError(
            f"Preset «{definition.key}»: version «{definition.version}» قبلاً ثبت شده است"
        )

    # Mutate only after every validation and duplicate check has succeeded:
    # exact historical recipes remain immutable even if a later import fails.
    LAYOUT_PRESET_VERSION_REGISTRY[identity] = definition
    current = LAYOUT_PRESET_REGISTRY.get(definition.key)
    if current is None or _version_number(definition.version) > _version_number(current.version):
        LAYOUT_PRESET_REGISTRY[definition.key] = definition


def get_layout_preset(key: str) -> LayoutPresetDefinition | None:
    return LAYOUT_PRESET_REGISTRY.get(key)


def get_layout_preset_version(key: str, version: str) -> LayoutPresetDefinition | None:
    """Return exactly one immutable registered Ready Template/preset version."""
    return LAYOUT_PRESET_VERSION_REGISTRY.get((key, version))


def list_layout_presets() -> list[LayoutPresetDefinition]:
    return list(LAYOUT_PRESET_REGISTRY.values())


def list_ready_templates() -> list[LayoutPresetDefinition]:
    """Return the latest version of every merchant-facing official recipe.

    Historical/internal presets remain fully registered and applicable, but
    are not surfaced here. Exact historical official versions stay available
    through ``get_layout_preset_version``.
    """
    return [preset for preset in list_layout_presets() if preset.is_ready_template]


def _validate_page_composition_shape(definition: LayoutPresetDefinition) -> None:
    """اعتبارسنجیِ بخشِ section/page در زمانِ import — تنها به
    ``section_registry`` (کاملاً خالص) وابسته است، پس اینجا امن است.
    اعتبارسنجیِ appearance/header/footer در ``preset_service`` است (به
    ``layout_service`` نیاز دارد — نگاه کنید به docstring بالایِ فایل)."""
    if not isinstance(definition.version, str) or not _NUMERIC_VERSION_RE.fullmatch(definition.version):
        raise InvalidLayoutPresetError(
            f"Preset «{definition.key}»: version باید یک رشته‌ی عددیِ مثبت باشد"
        )
    for page_type, entries in definition.pages.items():
        if page_type not in section_registry.ALL_PAGE_TYPES:
            raise InvalidLayoutPresetError(
                f"Preset «{definition.key}»: نوعِ صفحه‌ی «{page_type}» ناشناخته است"
            )
        for entry in entries:
            if not section_registry.is_valid_section_key(entry.section_key):
                raise InvalidLayoutPresetError(
                    f"Preset «{definition.key}»: نوعِ section «{entry.section_key}» ناشناخته است"
                )
            if not section_registry.is_section_allowed_on_page(entry.section_key, page_type):
                raise InvalidLayoutPresetError(
                    f"Preset «{definition.key}»: section «{entry.section_key}» روی صفحه‌ی "
                    f"«{page_type}» مجاز نیست"
                )
            definition_obj = section_registry.get_definition(entry.section_key)
            try:
                if entry.settings is None:
                    definition_obj.default_settings()
                else:
                    definition_obj.validate_settings(entry.settings)
            except Exception as exc:  # noqa: BLE001 — هر نوع خطایِ اعتبارسنجیِ خودِ section اینجا یکسان گزارش می‌شود
                raise InvalidLayoutPresetError(
                    f"Preset «{definition.key}»: تنظیماتِ section «{entry.section_key}» نامعتبر است: {exc}"
                ) from exc
            if entry.container_settings is not None:
                if not isinstance(entry.container_settings, dict):
                    raise InvalidLayoutPresetError(
                        f"Preset «{definition.key}»: container_settings باید دیکشنری باشد"
                    )
                allowed_container_keys = {
                    "gap", "mobile_mode", "content_width", "vertical_align",
                    "height_mode", "background_mode", "background_color",
                    "background_pattern",
                }
                unknown = set(entry.container_settings) - allowed_container_keys
                if unknown:
                    raise InvalidLayoutPresetError(
                        f"Preset «{definition.key}»: کلیدهای ناشناخته‌ی Container: {sorted(unknown)}"
                    )

        # Phase 3 — عضویتِ ردیفِ ترکیبی (``row_key``/``row_span``) هم در
        # زمانِ import اعتبارسنجی می‌شود — همان ``row_service`` که
        # مسیرهایِ نوشتنِ Section استفاده می‌کنند (duck-typing: فقط به
        # ``row_key``/``row_span``/``section_key`` نیاز دارد، هرگز به
        # مدلِ Django — پس اینجا هم امن است).
        from .services import row_service

        try:
            row_service.validate_page_row_layout(entries)
        except row_service.RowAssignmentError as exc:
            raise InvalidLayoutPresetError(
                f"Preset «{definition.key}»: ترکیبِ ردیفِ صفحه‌ی «{page_type}» نامعتبر است: {exc}"
            ) from exc


def _version_number(version: str) -> int:
    """Validated numeric versions have a stable, import-order-independent order."""
    return int(version)


def _validate_ready_template_store_appearance(definition: LayoutPresetDefinition) -> None:
    if not definition.is_ready_template:
        return
    if definition.store_appearance is None:
        raise InvalidLayoutPresetError(
            f"Ready Template «{definition.key}» باید Store Appearance DNA کامل داشته باشد"
        )
    if not isinstance(definition.store_appearance, dict):
        raise InvalidLayoutPresetError(
            f"Ready Template «{definition.key}»: Store Appearance DNA باید دیکشنری باشد"
        )
    try:
        validate_store_appearance_manifest(definition.store_appearance, require_complete=True)
    except Exception as exc:  # validator owns the typed, allowlisted contract
        raise InvalidLayoutPresetError(
            f"Ready Template «{definition.key}»: Store Appearance DNA نامعتبر است: {exc}"
        ) from exc


# ==================================================================
# چهار Preset درون‌ساختِ نماینده — طبقِ الزامِ صریحِ کار: «3-5 clearly
# different data presets... differ through composition, spacing/
# density, typography, motion, Header/Footer settings — not merely
# color». هر Preset حتماً پالتِ خودش را با یک Preset دیگر به اشتراک
# نمی‌گذارد (تا در پیش‌نمایش هم بصراحت متفاوت به‌نظر برسند)، اما این
# مستقل از دلیلِ اصلیِ تفاوتشان است.
# ==================================================================

register_layout_preset(LayoutPresetDefinition(
    key="clean_minimal",
    label_fa="ساده و مینیمال",
    description_fa="چیدمانِ کم‌جزئیات با تراکمِ فشرده، بدونِ حرکت، مناسبِ فروشگاه‌هایی که می‌خواهند تمرکز کامل روی محصول باشد.",
    appearance={
        "font": "Vazirmatn", "radius": 8, "button_radius": 6,
        "density": "compact", "motion": "none", "type_scale": "compact",
        "button_style": "outline", "image_fit": "cover", "image_hover": "none",
        "card_image_crossfade": False, "card_image_zoom": False,
    },
    default_palette_slug="mono",
    # U7 — header/footer *variant* selection (U2A/U2B global regions), not
    # just the boolean toggles already here: makes this genuinely a
    # composed Ready Template (page composition + appearance + global
    # component variants), not composition-only.
    header={"announcement_enabled": False, "sticky": True, "header_variant": "legacy_default"},
    footer={"show_newsletter": False, "footer_variant": "legacy_default"},
    pages={
        "home": (
            PresetSectionEntry("hero_banner"),
            PresetSectionEntry("newest_products"),
            PresetSectionEntry("category_grid"),
            PresetSectionEntry("trust_features"),
        ),
        "product_detail": (
            PresetSectionEntry("product_main"),
            PresetSectionEntry("product_description"),
        ),
        "listing": (PresetSectionEntry("product_listing"),),
        "collection": (
            PresetSectionEntry("collection_header"),
            PresetSectionEntry("collection_products"),
        ),
        "search": (PresetSectionEntry("product_listing"),),
        "cart": (
            PresetSectionEntry("cart_items"),
            PresetSectionEntry("cart_summary"),
        ),
    },
))

register_layout_preset(LayoutPresetDefinition(
    key="editorial_story",
    label_fa="روایت‌محور",
    description_fa="چیدمانِ محتوامحور با تایپوگرافیِ بزرگ‌تر، تراکمِ بازتر و حرکتِ ملایم — مناسبِ برندهایی که با روایت/تصویر می‌فروشند.",
    appearance={
        "font": "Georgia", "radius": 4, "button_radius": 4,
        "density": "relaxed", "motion": "subtle", "type_scale": "large",
        "button_style": "soft", "image_fit": "cover", "image_hover": "zoom",
        "card_image_crossfade": True, "card_image_zoom": True,
    },
    default_palette_slug="terracotta",
    header={"sticky": True, "announcement_enabled": True, "header_variant": "boutique_centered"},
    footer={"footer_variant": "boutique_editorial"},
    pages={
        "home": (
            PresetSectionEntry("story_rail"),
            PresetSectionEntry("hero_banner"),
            PresetSectionEntry("image_text"),
            PresetSectionEntry("featured_products"),
            PresetSectionEntry("testimonials"),
            PresetSectionEntry("newsletter"),
        ),
        "product_detail": (
            PresetSectionEntry("product_main"),
            PresetSectionEntry("product_description"),
            PresetSectionEntry("product_video"),
            PresetSectionEntry("related_products"),
        ),
        "listing": (PresetSectionEntry("product_listing"),),
        "collection": (
            PresetSectionEntry("collection_header"),
            PresetSectionEntry("collection_products"),
        ),
        "search": (PresetSectionEntry("product_listing"),),
        "cart": (
            PresetSectionEntry("cart_items"),
            PresetSectionEntry("cart_summary"),
        ),
    },
))

register_layout_preset(LayoutPresetDefinition(
    key="dense_catalog",
    label_fa="کاتالوگ فشرده",
    description_fa="چیدمانِ پرتراکم با چند ردیفِ گریدِ محصول پشتِ‌سرِهم — مناسبِ فروشگاه‌هایی با تعدادِ زیادِ کالا که می‌خواهند حداکثرِ محصول را زود نشان دهند.",
    appearance={
        "font": "Vazirmatn", "radius": 6, "button_radius": 6,
        "density": "compact", "motion": "none", "type_scale": "compact",
        "button_style": "filled", "image_fit": "cover", "image_hover": "none",
        "card_image_crossfade": False, "card_image_zoom": False,
    },
    default_palette_slug="slate",
    header={"sticky": True, "announcement_enabled": False, "header_variant": "marketplace_search_first"},
    footer={"show_newsletter": False, "footer_variant": "marketplace_dense"},
    pages={
        "home": (
            PresetSectionEntry("category_grid"),
            PresetSectionEntry("newest_products"),
            PresetSectionEntry("best_sellers"),
            PresetSectionEntry("discounted_products"),
            PresetSectionEntry("amazing_offers"),
            PresetSectionEntry("brand_carousel"),
            PresetSectionEntry("trust_features"),
        ),
        "product_detail": (
            PresetSectionEntry("product_main"),
            PresetSectionEntry("product_description"),
            PresetSectionEntry("related_products"),
        ),
        "listing": (PresetSectionEntry("product_listing"),),
        "collection": (
            PresetSectionEntry("collection_header"),
            PresetSectionEntry("collection_products"),
        ),
        "search": (PresetSectionEntry("product_listing"),),
        "cart": (
            PresetSectionEntry("cart_items"),
            PresetSectionEntry("cart_summary"),
        ),
    },
))

register_layout_preset(LayoutPresetDefinition(
    key="premium_boutique",
    label_fa="پرمیوم بوتیک",
    description_fa="چیدمانِ لوکس با تراکمِ باز، حرکتِ محسوس‌تر و تأکیدِ بازاریابی — مناسبِ برندهایی با موضعِ قیمتیِ بالا.",
    appearance={
        "font": "Georgia", "radius": 20, "button_radius": 18,
        "density": "relaxed", "motion": "dynamic", "type_scale": "large",
        "button_style": "filled", "image_fit": "cover", "image_hover": "zoom",
        "card_image_crossfade": True, "card_image_zoom": True,
    },
    default_palette_slug="luxury-black",
    header={"sticky": True, "announcement_enabled": True, "header_variant": "premium_three_column"},
    footer={"show_trust_badges": True, "show_payment_logos": True, "show_newsletter": True, "footer_variant": "premium_columns"},
    pages={
        "home": (
            PresetSectionEntry("hero_banner"),
            PresetSectionEntry("brand_carousel"),
            PresetSectionEntry("featured_products"),
            PresetSectionEntry("story_rail"),
            PresetSectionEntry("promo_cards"),
            PresetSectionEntry("testimonials"),
            PresetSectionEntry("trust_features"),
            PresetSectionEntry("newsletter"),
        ),
        "product_detail": (
            PresetSectionEntry("product_main"),
            PresetSectionEntry("product_description"),
            PresetSectionEntry("product_video"),
            PresetSectionEntry("related_products"),
        ),
        "listing": (PresetSectionEntry("product_listing"),),
        "collection": (
            PresetSectionEntry("collection_header"),
            PresetSectionEntry("collection_products"),
        ),
        "search": (PresetSectionEntry("product_listing"),),
        "cart": (
            PresetSectionEntry("cart_items"),
            PresetSectionEntry("cart_summary"),
        ),
    },
))


# ==================================================================
# Golden dense-commerce homepage preset — PURE DATA.
#
# This preset intentionally mirrors the approved dense marketplace reference
# using only reusable Universal blocks.  No renderer knows this key and no
# section stores tenant-specific IDs.  Visual variety comes from composition,
# row spans, responsive columns, reusable banner variants and generic product
# sources (newest / discounted / best_sellers / most_viewed).
# ==================================================================
register_layout_preset(LayoutPresetDefinition(
    key="v5_golden_homepage",
    label_fa="فروشگاه رنگی و کاتالوگی — مرجع",
    description_fa=(
        "شروع نزدیک به صفحه مرجع تأییدشده: هدر جستجو-محور، Hero و پیشنهاد جانبی، "
        "دسته‌بندی تصویری، بنرهای تبلیغاتی، ردیف‌های رنگی محصول، ترکیب‌های دو ستونه "
        "و فوتر کامل. بعد از اعمال، همه بخش‌ها و پس‌زمینه‌ها آزادانه قابل ویرایش‌اند."
    ),
    appearance={
        "font": "Vazirmatn", "radius": 7, "button_radius": 4,
        "density": "compact", "motion": "none", "type_scale": "normal",
        "button_style": "filled", "image_fit": "contain", "image_hover": "none",
        "card_image_crossfade": False, "card_image_zoom": False,
        "content_width": 1500, "grid_density": 6,
        "card_shadow": "none", "card_hover": "none", "hero_style": "wide",
    },
    default_palette_slug="catalog-colorful",
    header={
        "sticky": False, "announcement_enabled": True,
        "show_search": True, "show_account": True, "show_wishlist": True, "show_cart": True,
        "extra_blocks": [{"type": "tagline"}],
    },
    footer={
        "show_about": True, "show_contact": True, "show_categories": True,
        "show_quick_links": True, "show_social": True,
        "show_trust_badges": True, "show_payment_logos": True,
        "show_newsletter": False, "show_copyright": True,
        "extra_blocks": [
            {"type": "custom_text", "title": "خدمات فروشگاه", "text": "ارسال سریع • ضمانت اصالت • امکان مرجوعی • پشتیبانی خرید"},
        ],
    },
    pages={
        "home": (
            PresetSectionEntry(
                "product_section", row_key="golden-hero-row", row_span=3,
                container_settings={
                    "gap": 8, "mobile_mode": "stack",
                    "vertical_align": "start", "height_mode": "equal",
                },
                settings={
                    "title": "پیشنهاد لحظه‌ای", "data_source": "discounted", "item_limit": 4,
                    "display_mode": "carousel", "show_view_all": False,
                    "carousel_autoplay": True, "carousel_interval_ms": 3500,
                    "carousel_show_arrows": True, "header_position": "inside",
                    "responsive": {"desktop_columns": 1, "tablet_columns": 1, "mobile_columns": 1},
                    "card": {
                        "card_style": "compact", "show_brand": False, "show_rating": False,
                        "show_wishlist": False, "show_quick_add": False, "show_badge": True,
                        "show_price": True, "card_border": True, "image_ratio": "square",
                        "quick_add_reveal": "always",
                    },
                    "spacing": {"vertical_spacing": "small"},
                },
            ),
            PresetSectionEntry(
                "hero_banner", row_key="golden-hero-row", row_span=9,
                settings={
                    "text_position": "start",
                    "layout": {"height": "standard"},
                    "spacing": {"vertical_spacing": "small"},
                },
            ),
            PresetSectionEntry(
                "category_grid",
                settings={
                    "title": "", "display_mode": "image_strip", "category_ids": [], "item_limit": 7,
                    "spacing": {"vertical_spacing": "small"},
                },
            ),
            PresetSectionEntry(
                "trust_features",
                settings={
                    "items": [
                        {"icon": "↙", "title": "تضمین بهترین قیمت", "subtitle": "خرید مطمئن"},
                        {"icon": "◎", "title": "ضمانت اصالت کالا", "subtitle": "کالای اصل"},
                        {"icon": "▣", "title": "پرداخت امن", "subtitle": "درگاه و کارت"},
                        {"icon": "⌂", "title": "تحویل حضوری", "subtitle": "دریافت آسان"},
                        {"icon": "⇢", "title": "ارسال سریع", "subtitle": "به سراسر کشور"},
                    ],
                    "spacing": {"vertical_spacing": "small"},
                },
            ),
            PresetSectionEntry(
                "multi_banner",
                settings={
                    "item_limit": 4, "offset": 0, "layout_variant": "promo-4",
                    "responsive": {"desktop_columns": 4, "tablet_columns": 2, "mobile_columns": 2},
                    "spacing": {"vertical_spacing": "small"},
                },
            ),
            PresetSectionEntry(
                "product_section",
                settings={
                    "title": "پرفروش‌ترین‌های هفته", "data_source": "most_viewed", "item_limit": 6,
                    "display_mode": "carousel", "show_view_all": True,
                    "responsive": {"desktop_columns": 6, "tablet_columns": 3, "mobile_columns": 2},
                    "card": {
                        "card_style": "compact", "show_brand": False, "show_rating": False,
                        "show_wishlist": False, "show_quick_add": True, "show_badge": True,
                        "show_price": True, "card_border": True, "image_ratio": "square",
                        "quick_add_reveal": "always",
                    },
                    "background": {"mode": "palette_pattern", "pattern_slug": "commerce-doodle", "palette_role": "tone-1"},
                    "spacing": {"vertical_spacing": "small"},
                },
            ),
            PresetSectionEntry(
                "amazing_offers",
                settings={
                    "item_limit": 4, "deadline_hours": 8, "title": "پیشنهاد شگفت‌انگیز برایتو",
                    "spacing": {"vertical_spacing": "small"},
                },
            ),
            PresetSectionEntry(
                "product_section",
                settings={
                    "title": "ترندهای این هفته", "data_source": "discounted", "item_limit": 6,
                    "display_mode": "carousel", "show_view_all": True,
                    "responsive": {"desktop_columns": 6, "tablet_columns": 3, "mobile_columns": 2},
                    "card": {
                        "card_style": "compact", "show_brand": False, "show_rating": False,
                        "show_wishlist": False, "show_quick_add": True, "show_badge": True,
                        "show_price": True, "card_border": True, "image_ratio": "square",
                        "quick_add_reveal": "always",
                    },
                    "background": {"mode": "palette_pattern", "pattern_slug": "commerce-doodle", "palette_role": "tone-2"},
                    "spacing": {"vertical_spacing": "small"},
                },
            ),
            PresetSectionEntry(
                "multi_banner", row_key="golden-banner-pair-a", row_span=6,
                container_settings={"gap": 10, "mobile_mode": "stack", "height_mode": "equal"},
                settings={
                    "item_limit": 1, "offset": 4, "layout_variant": "wide-single",
                    "responsive": {"desktop_columns": 1, "tablet_columns": 1, "mobile_columns": 1},
                    "spacing": {"vertical_spacing": "small"},
                },
            ),
            PresetSectionEntry(
                "multi_banner", row_key="golden-banner-pair-a", row_span=6,
                settings={
                    "item_limit": 1, "offset": 5, "layout_variant": "wide-single",
                    "responsive": {"desktop_columns": 1, "tablet_columns": 1, "mobile_columns": 1},
                    "spacing": {"vertical_spacing": "small"},
                },
            ),
            PresetSectionEntry(
                "product_section",
                settings={
                    "title": "تازه‌های فروشگاه", "data_source": "newest", "item_limit": 6,
                    "display_mode": "carousel", "show_view_all": True,
                    "responsive": {"desktop_columns": 6, "tablet_columns": 3, "mobile_columns": 2},
                    "card": {
                        "card_style": "compact", "show_brand": False, "show_rating": False,
                        "show_wishlist": False, "show_quick_add": True, "show_badge": True,
                        "show_price": True, "card_border": True, "image_ratio": "square",
                        "quick_add_reveal": "always",
                    },
                    "background": {"mode": "palette_pattern", "pattern_slug": "commerce-doodle", "palette_role": "tone-3"},
                    "spacing": {"vertical_spacing": "small"},
                },
            ),
            PresetSectionEntry(
                "multi_banner", row_key="golden-banner-pair-b", row_span=6,
                container_settings={"gap": 10, "mobile_mode": "stack", "height_mode": "equal"},
                settings={
                    "item_limit": 1, "offset": 6, "layout_variant": "wide-single",
                    "responsive": {"desktop_columns": 1, "tablet_columns": 1, "mobile_columns": 1},
                    "spacing": {"vertical_spacing": "small"},
                },
            ),
            PresetSectionEntry(
                "multi_banner", row_key="golden-banner-pair-b", row_span=6,
                settings={
                    "item_limit": 1, "offset": 7, "layout_variant": "wide-single",
                    "responsive": {"desktop_columns": 1, "tablet_columns": 1, "mobile_columns": 1},
                    "spacing": {"vertical_spacing": "small"},
                },
            ),
            PresetSectionEntry(
                "product_section", row_key="golden-compact-row-a", row_span=6,
                container_settings={"gap": 10, "mobile_mode": "stack", "height_mode": "equal"},
                settings={
                    "title": "پیشنهادهای منتخب", "data_source": "newest", "item_limit": 3,
                    "display_mode": "grid", "show_view_all": True,
                    "responsive": {"desktop_columns": 3, "tablet_columns": 3, "mobile_columns": 1},
                    "card": {
                        "card_style": "compact", "show_brand": False, "show_rating": False,
                        "show_wishlist": False, "show_quick_add": True, "show_badge": True,
                        "show_price": True, "card_border": True, "image_ratio": "square",
                        "quick_add_reveal": "always",
                    },
                    "spacing": {"vertical_spacing": "small"},
                },
            ),
            PresetSectionEntry(
                "product_section", row_key="golden-compact-row-a", row_span=6,
                settings={
                    "title": "محبوب‌ترین انتخاب‌ها", "data_source": "most_viewed", "item_limit": 3,
                    "display_mode": "grid", "show_view_all": True,
                    "responsive": {"desktop_columns": 3, "tablet_columns": 3, "mobile_columns": 1},
                    "card": {
                        "card_style": "compact", "show_brand": False, "show_rating": False,
                        "show_wishlist": False, "show_quick_add": True, "show_badge": True,
                        "show_price": True, "card_border": True, "image_ratio": "square",
                        "quick_add_reveal": "always",
                    },
                    "spacing": {"vertical_spacing": "small"},
                },
            ),
            PresetSectionEntry(
                "product_section",
                settings={
                    "title": "پیشنهادهای ویژه", "data_source": "most_viewed", "item_limit": 6,
                    "display_mode": "carousel", "show_view_all": True,
                    "responsive": {"desktop_columns": 6, "tablet_columns": 3, "mobile_columns": 2},
                    "card": {
                        "card_style": "compact", "show_brand": False, "show_rating": False,
                        "show_wishlist": False, "show_quick_add": True, "show_badge": True,
                        "show_price": True, "card_border": True, "image_ratio": "square",
                        "quick_add_reveal": "always",
                    },
                    "background": {"mode": "palette_pattern", "pattern_slug": "commerce-doodle", "palette_role": "tone-4"},
                    "spacing": {"vertical_spacing": "small"},
                },
            ),
            PresetSectionEntry(
                "product_section", row_key="golden-compact-row-b", row_span=6,
                container_settings={"gap": 10, "mobile_mode": "stack", "height_mode": "equal"},
                settings={
                    "title": "انتخاب روز", "data_source": "discounted", "item_limit": 3,
                    "display_mode": "grid", "show_view_all": True,
                    "responsive": {"desktop_columns": 3, "tablet_columns": 3, "mobile_columns": 1},
                    "card": {
                        "card_style": "compact", "show_brand": False, "show_rating": False,
                        "show_wishlist": False, "show_quick_add": True, "show_badge": True,
                        "show_price": True, "card_border": True, "image_ratio": "square",
                        "quick_add_reveal": "always",
                    },
                    "spacing": {"vertical_spacing": "small"},
                },
            ),
            PresetSectionEntry(
                "product_section", row_key="golden-compact-row-b", row_span=6,
                settings={
                    "title": "بیشتر دیده‌شده‌ها", "data_source": "most_viewed", "item_limit": 3,
                    "display_mode": "grid", "show_view_all": True,
                    "responsive": {"desktop_columns": 3, "tablet_columns": 3, "mobile_columns": 1},
                    "card": {
                        "card_style": "compact", "show_brand": False, "show_rating": False,
                        "show_wishlist": False, "show_quick_add": True, "show_badge": True,
                        "show_price": True, "card_border": True, "image_ratio": "square",
                        "quick_add_reveal": "always",
                    },
                    "spacing": {"vertical_spacing": "small"},
                },
            ),
            PresetSectionEntry(
                "multi_banner",
                settings={
                    "item_limit": 4, "offset": 8, "layout_variant": "mini-4",
                    "responsive": {"desktop_columns": 4, "tablet_columns": 2, "mobile_columns": 2},
                    "spacing": {"vertical_spacing": "small"},
                },
            ),
            PresetSectionEntry(
                "product_section",
                settings={
                    "title": "محبوب‌های فروشگاه", "data_source": "newest", "item_limit": 6,
                    "display_mode": "carousel", "show_view_all": True,
                    "responsive": {"desktop_columns": 6, "tablet_columns": 3, "mobile_columns": 2},
                    "card": {
                        "card_style": "compact", "show_brand": False, "show_rating": False,
                        "show_wishlist": False, "show_quick_add": True, "show_badge": True,
                        "show_price": True, "card_border": True, "image_ratio": "square",
                        "quick_add_reveal": "always",
                    },
                    "background": {"mode": "palette_pattern", "pattern_slug": "commerce-doodle", "palette_role": "tone-5"},
                    "spacing": {"vertical_spacing": "small"},
                },
            ),
            PresetSectionEntry(
                "multi_banner",
                settings={
                    "item_limit": 1, "offset": 12, "layout_variant": "strip",
                    "responsive": {"desktop_columns": 1, "tablet_columns": 1, "mobile_columns": 1},
                    "spacing": {"vertical_spacing": "small"},
                },
            ),
            PresetSectionEntry(
                "product_section",
                settings={
                    "title": "منتخب برای شما", "data_source": "discounted", "item_limit": 6,
                    "display_mode": "carousel", "show_view_all": True,
                    "responsive": {"desktop_columns": 6, "tablet_columns": 3, "mobile_columns": 2},
                    "card": {
                        "card_style": "compact", "show_brand": False, "show_rating": False,
                        "show_wishlist": False, "show_quick_add": True, "show_badge": True,
                        "show_price": True, "card_border": True, "image_ratio": "square",
                        "quick_add_reveal": "always",
                    },
                    "spacing": {"vertical_spacing": "small"},
                },
            ),
        ),
    },
))


# ==================================================================
# U10 — the 8 required Ready Template recipe keys. Each is built purely
# from the Universal Storefront Engine already completed in U1-U9: real
# global header/footer variants (U2A/U2B), real registered section
# variants including U4's additions (hero_style/tile_style/image_position/
# display_mode), real appearance tokens/palettes, real product_section
# card settings — never a new renderer, never a store-specific ID, never
# fabricated commercial copy (no invented discounts/guarantees/stock
# claims — sections read real store data at render time as always).
#
# Difference between templates comes from *combinations* of: home
# composition, header/footer variant, density/typography/motion, palette,
# and product-card presentation — exactly the axes the master contract
# names, not duplicated code. product_detail/listing/collection/search/
# cart intentionally share one composition across all 8 (see
# ``_u10_standard_non_home_pages`` below) — the same, already-established
# pattern the 5 pre-U10 presets already use; real product/cart data drives
# those pages far more than section arrangement does, so bespoke
# per-template composition there would be difference for its own sake,
# not a real one.
# ==================================================================

# Non-home rows carry their RATIFIED cross-template semantic role explicitly
# (the approved (page_type, section_key) mapping — identical to the canonical
# ``a8_ready_templates.NON_HOME_SECTION_SEMANTIC_ROLE`` values). ``listing`` and
# ``search`` both compose a single ``product_listing`` row but resolve to
# DISTINCT ratified roles (products.listing vs products.search), so they use
# separate constants rather than sharing one.
_U10_STANDARD_PRODUCT_DETAIL_PAGE = (
    PresetSectionEntry("product_main", semantic_slot_key="product.main"),
    PresetSectionEntry("product_description", semantic_slot_key="product.description"),
    PresetSectionEntry("related_products", semantic_slot_key="product.related"),
)
_U10_STANDARD_LISTING_PAGE = (
    PresetSectionEntry("product_listing", semantic_slot_key="products.listing"),
)
_U10_STANDARD_SEARCH_PAGE = (
    PresetSectionEntry("product_listing", semantic_slot_key="products.search"),
)
_U10_STANDARD_COLLECTION_PAGE = (
    PresetSectionEntry("collection_header", semantic_slot_key="collection.header"),
    PresetSectionEntry("collection_products", semantic_slot_key="collection.products"),
)
_U10_STANDARD_CART_PAGE = (
    PresetSectionEntry("cart_items", semantic_slot_key="cart.items"),
    PresetSectionEntry("cart_summary", semantic_slot_key="cart.summary"),
)


def _u10_standard_non_home_pages() -> dict:
    return {
        "product_detail": _U10_STANDARD_PRODUCT_DETAIL_PAGE,
        "listing": _U10_STANDARD_LISTING_PAGE,
        "collection": _U10_STANDARD_COLLECTION_PAGE,
        "search": _U10_STANDARD_SEARCH_PAGE,
        "cart": _U10_STANDARD_CART_PAGE,
    }


#: Beraito is the dense-commerce reference family.  The internal
#: ``v5_golden_homepage`` preset above was already built and regression-tested
#: as a generic, Store-agnostic dense-commerce composition for that exact
#: reference language (hero + side offer, image-strip discovery, service
#: strip, promotional banners and alternating coloured six-card rows).  Reuse
#: that *pure data* composition here instead of duplicating 20+ section
#: entries or adding a Ready-Template-specific renderer branch.
_DENSE_MARKETPLACE_BERAITO_GOLDEN_HOME = tuple(
    dataclasses.replace(
        entry,
        settings={**entry.settings, "data_source": "best_sellers"},
    )
    if (
        entry.section_key == "product_section"
        and entry.settings
        and entry.settings.get("title") == "پرفروش‌ترین‌های هفته"
    )
    else entry
    for entry in get_layout_preset("v5_golden_homepage").pages["home"]
)

_DENSE_MARKETPLACE_BERAITO_HOME_V2 = (
    *_DENSE_MARKETPLACE_BERAITO_GOLDEN_HOME,
    # Beraito closes with brand discovery and editorial content before its
    # dense commercial footer.  Both are existing generic Storefront blocks:
    # brands resolve from the current Store and blog posts from the platform
    # blog feed, so there are no tenant IDs or Ready-Template branches.
    PresetSectionEntry(
        "brand_carousel",
        settings={
            "title": "برترین برندها",
            "display_mode": "grid",
            "show_view_all": False,
            "brand_ids": [],
        },
    ),
    PresetSectionEntry(
        "blog_posts",
        settings={"title": "مجله فروشگاه", "item_limit": 6},
    ),
)

register_layout_preset(LayoutPresetDefinition(
    key="dense_marketplace",
    version="2",
    is_ready_template=True,
    store_appearance=_complete_store_appearance(
        header="marketplace_search_first", hero="legacy_default", layout="quarters",
        product_view="carousel", card="marketplace_price", badge="sale", motion="none",
        footer="marketplace_dense", bottom_nav="hidden",
    ),
    label_fa="بازارگاه پرتراکم",
    description_fa="بازارگاه کاتالوگیِ رنگی و جستجو-محور با Hero تبلیغاتی، میانبرهای تصویری، ردیف‌های فشرده محصول و فوتر تجاری کامل.",
    appearance={
        "font": "Vazirmatn", "radius": 7, "button_radius": 4,
        "density": "compact", "motion": "none", "type_scale": "normal",
        "button_style": "filled", "image_fit": "contain", "image_hover": "none",
        "card_image_crossfade": False, "card_image_zoom": False,
        "content_width": 1500, "grid_density": 6,
        "card_shadow": "none", "card_hover": "none", "hero_style": "wide",
    },
    default_palette_slug="marketplace-spectrum",
    header={
        "sticky": True, "announcement_enabled": True,
        "show_search": True, "show_account": True, "show_wishlist": False, "show_cart": True,
        "header_variant": "marketplace_search_first",
    },
    footer={
        "show_about": True, "show_contact": True, "show_categories": True,
        "show_quick_links": True, "show_social": True,
        "show_trust_badges": True, "show_payment_logos": True,
        "show_newsletter": False, "show_copyright": True,
        "footer_variant": "marketplace_dense",
    },
    pages={
        "home": authored_legacy_home("dense_marketplace", _DENSE_MARKETPLACE_BERAITO_HOME_V2, ("offer_flash", "hero", "categories", "trust", "banner_a", "products_bestsellers", "amazing_offers", "products_trending", "banner_pair_a1", "banner_pair_a2", "products_newest", "banner_pair_b1", "banner_pair_b2", "products_curated", "products_popular_compact", "products_special", "products_day_pick", "products_most_viewed_compact", "banner_mini", "products_store_favorites", "banner_strip", "products_for_you", "brands", "blog")),
        **_u10_standard_non_home_pages(),
    },
))

_CHOCOLATE_RETAIL_CARD = {
    "card_style": "chocolate_retail",
    "image_ratio": "square",
    "show_quick_add": True,
}
_CHOCOLATE_PRODUCT_ROW = {
    "responsive": {"desktop_columns": 4, "tablet_columns": 3, "mobile_columns": 2},
}


def _chocolate_product_row(title: str, data_source: str) -> PresetSectionEntry:
    return PresetSectionEntry("product_section", settings={
        "title": title, "data_source": data_source, "display_mode": "carousel",
        "item_limit": 12, "card": _CHOCOLATE_RETAIL_CARD, **_CHOCOLATE_PRODUCT_ROW,
    })


register_layout_preset(LayoutPresetDefinition(
    key="premium_leather",
    version="2",
    is_ready_template=True,
    store_appearance=_complete_store_appearance(
        header="chocolate_centered_search", hero="chocolate_carousel", layout="quarters",
        product_view="carousel", card="standard", badge="none", motion="subtle",
        footer="chocolate_dark_columns", bottom_nav="hidden",
    ),
    label_fa="فروشگاه پرمیوم",
    description_fa="چیدمان فروشگاهی خانه و سبک زندگی با زمینه روشن، هدر شکلاتی، میانبرهای تصویری و کارت‌های محصول گرم و کاربردی.",
    appearance={
        "font": "Vazirmatn", "radius": 12, "button_radius": 10,
        "density": "normal", "motion": "subtle", "type_scale": "normal",
        "button_style": "filled", "image_fit": "contain", "image_hover": "zoom",
        "card_image_crossfade": True, "card_image_zoom": True,
        "content_width": 1500,
    },
    default_palette_slug="chocolate-ice",
    header={
        "sticky": True, "announcement_enabled": False, "show_search": True,
        "show_account": True, "show_wishlist": False, "show_cart": True,
        "header_variant": "chocolate_centered_search",
    },
    footer={
        "show_newsletter": False, "show_trust_badges": True,
        "show_payment_logos": True, "footer_variant": "chocolate_dark_columns",
    },
    pages={
        "home": authored_legacy_home("premium_leather", (
            # Reference first-fold discovery row.  This is a registered
            # category presentation variant (Store-scoped runtime data), not
            # reference content or a Ready Template branch.  It also keeps the
            # demo visually complete when no explicit StoryRailItem media has
            # been authored yet.
            PresetSectionEntry("category_grid", settings={
                "title": "", "display_mode": "chocolate_story",
                "item_limit": 10,
            }),
            PresetSectionEntry("hero_banner", settings={
                "hero_style": "chocolate_carousel", "text_position": "start",
                "autoplay": True, "interval_ms": 4800,
                "show_arrows": True, "show_dots": True,
            }),
            PresetSectionEntry("category_grid", settings={
                "title": "", "display_mode": "chocolate_badges",
                "item_limit": 12,
            }),
            PresetSectionEntry("multi_banner", settings={
                "item_limit": 1, "offset": 0, "layout_variant": "wide-single",
                "responsive": {"desktop_columns": 1, "tablet_columns": 1, "mobile_columns": 1},
            }),
            _chocolate_product_row("محصولات محبوب", "best_sellers"),
            PresetSectionEntry("multi_banner", settings={
                "item_limit": 4, "offset": 1, "layout_variant": "promo-4",
                "responsive": {"desktop_columns": 4, "tablet_columns": 2, "mobile_columns": 2},
            }),
            _chocolate_product_row("جدیدترین محصولات", "newest"),
            PresetSectionEntry("multi_banner", settings={
                "item_limit": 1, "offset": 5, "layout_variant": "wide-single",
                "responsive": {"desktop_columns": 1, "tablet_columns": 1, "mobile_columns": 1},
            }),
            _chocolate_product_row("پیشنهادهای فروشگاه", "discounted"),
            PresetSectionEntry("category_grid", settings={
                "title": "انتخاب بر اساس دسته‌بندی", "display_mode": "chocolate_badges",
                "item_limit": 6,
            }),
            _chocolate_product_row("محصولات پربازدید", "most_viewed"),
            PresetSectionEntry("blog_posts"),
            PresetSectionEntry("trust_features"),
        ), ("categories_story", "hero", "categories_badges", "banner_wide", "products_popular", "banner_promo", "products_newest", "banner_wide_2", "products_offers", "categories_by_group", "products_most_viewed", "blog", "trust")),
        **_u10_standard_non_home_pages(),
    },
))


#: laleRokh reference family — reusable cosmetics/beauty retail card.
#: All price/discount/quick-add semantics still come from product_card_data;
#: this preset selects only presentation settings.
_BEAUTY_RETAIL_CARD = {
    "card_style": "beauty_retail", "image_ratio": "square",
    "show_brand": False, "show_rating": True, "show_wishlist": False, "show_quick_add": True,
    "quick_add_reveal": "always", "card_border": True,
}
_BEAUTY_RETAIL_ROW = {"responsive": {"desktop_columns": 4, "tablet_columns": 2, "mobile_columns": 2}}
_BEAUTY_WALL_ROW = {"responsive": {"desktop_columns": 5, "tablet_columns": 3, "mobile_columns": 2}}
_RETAIL_LIST_CARD = {
    "card_style": "retail_list", "image_ratio": "square",
    "show_brand": False, "show_rating": False, "show_wishlist": False,
    "show_badge": False, "show_quick_add": False, "card_border": False,
}


def _beauty_retail_row(
    title: str, data_source: str, *, background: dict | None = None, campaign: bool = False
) -> PresetSectionEntry:
    settings = {
        "title": title, "data_source": data_source,
        "display_mode": "campaign_band" if campaign else "carousel",
        "item_limit": 4 if campaign else 12, "card": _BEAUTY_RETAIL_CARD, **_BEAUTY_RETAIL_ROW,
    }
    if background:
        settings["background"] = background
    return PresetSectionEntry("product_section", settings=settings)


register_layout_preset(LayoutPresetDefinition(
    key="warm_boutique",
    # Reference-driven rebuild: v1 was the original generic centered-boutique
    # skeleton.  v2 changes the visible Home composition, palette, global
    # header/footer variants, category treatment and product card treatment.
    version="2",
    is_ready_template=True,
    store_appearance=_complete_store_appearance(
        header="beauty_search_nav", hero="beauty_editorial", layout="quarters",
        product_view="carousel", card="beauty_glass", badge="none", motion="subtle",
        footer="beauty_retail_columns", bottom_nav="hidden",
    ),
    label_fa="بوتیکِ گرم",
    description_fa="فروشگاه زیبایی و بوتیک با جستجوی برجسته، دسته‌بندی تصویری و ردیف‌های فروشگاهی رنگی — مناسب آرایشی، مراقبتی، عطر و سبک زندگی.",
    appearance={
        "font": "Vazirmatn", "radius": 10, "button_radius": 6,
        "density": "normal", "motion": "subtle", "type_scale": "normal",
        "button_style": "filled", "image_fit": "contain", "image_hover": "zoom",
        "card_image_crossfade": True, "card_image_zoom": True,
        "content_width": 1500,
    },
    default_palette_slug="beauty-magenta",
    header={"sticky": True, "announcement_enabled": False, "show_search": True, "show_account": True, "show_wishlist": False, "show_cart": True, "header_variant": "beauty_search_nav"},
    footer={"show_newsletter": False, "show_trust_badges": True, "show_payment_logos": True, "footer_variant": "beauty_retail_columns"},
    pages={
        "home": authored_legacy_home("warm_boutique", (
            # Wide, short, image-first campaign hero using the Store's own
            # HeroSlide records; no reference merchant image/logo is embedded.
            PresetSectionEntry("hero_banner", settings={
                "hero_style": "beauty_editorial", "text_position": "end",
                "autoplay": True, "interval_ms": 4500,
                "show_arrows": False, "show_dots": False,
            }),
            # Six compact visual discovery shortcuts, resolved from the
            # current Store's real top-level categories and representative media.
            PresetSectionEntry("category_grid", settings={
                "title": "دسته‌بندی محصولات", "display_mode": "beauty_icons", "item_limit": 6,
            }),
            # Two high-signal campaign bands mirror the reference's magenta
            # then green retail moments while retaining real product semantics.
            _beauty_retail_row("شگفت‌انگیزهای فروشگاه", "discounted", campaign=True, background={
                "mode": "palette_pattern", "palette_role": "tone-1", "pattern_slug": "commerce-doodle",
            }),
            PresetSectionEntry("multi_banner", settings={
                # laleRokh's first post-campaign banner moment is a true four-card
                # visual grid, not the tiny strip used by dense-marketplace
                # families.  ``promo-4`` is an existing generic variant.
                "item_limit": 4, "offset": 0, "layout_variant": "promo-4",
                "responsive": {"desktop_columns": 4, "tablet_columns": 2, "mobile_columns": 2},
            }),
            _beauty_retail_row("جدیدترین‌های فروشگاه", "newest", campaign=True, background={
                "mode": "palette", "palette_role": "tone-3",
            }),
            PresetSectionEntry("brand_carousel", settings={
                "title": "محبوب‌ترین برندها", "display_mode": "beauty_tabs", "show_view_all": False,
            }),
            # The reference's dark category-special block is represented by a
            # generic catalog-wall structural variant: three current-Store
            # groups, three real products per group, compact list cards.
            PresetSectionEntry("catalog_product_wall", settings={
                "title": "فروش ویژه محصولات بر اساس دسته‌بندی",
                "layout_mode": "group_columns",
                "source_mode": "categories_then_collections", "max_groups": 3,
                "products_per_group": 3, "minimum_products": 2, "skip_empty_groups": True,
                "show_view_all": True, "card": _RETAIL_LIST_CARD,
                "background": {"mode": "palette_pattern", "palette_role": "tone-2", "pattern_slug": "commerce-doodle"},
            }),
            # Second merchant-banner moment, matching the reference's paired
            # mid-page beauty banners without carrying any fixed banner ID.
            PresetSectionEntry("multi_banner", settings={
                "item_limit": 2, "offset": 4, "layout_variant": "wide-single",
                "responsive": {"desktop_columns": 2, "tablet_columns": 2, "mobile_columns": 1},
            }),
            # A separate collection-resolved row avoids coupling this later
            # merchandising moment to the earlier category group columns.  If a
            # Store has no active collections it fails closed by rendering none.
            PresetSectionEntry("catalog_product_wall", settings={
                "title": "دسته‌بندی محصولات پیشنهادی",
                "layout_mode": "featured_row",
                "source_mode": "visible_collections", "max_groups": 1,
                "products_per_group": 10, "minimum_products": 3, "skip_empty_groups": True,
                "show_view_all": True, "card": _BEAUTY_RETAIL_CARD, **_BEAUTY_WALL_ROW,
                "background": {"mode": "palette_pattern", "palette_role": "tone-2", "pattern_slug": "commerce-doodle"},
            }),
            # The reference closes merchandising with a light final product
            # discovery moment before newsletter/footer.  We do not fake a
            # shopper-specific "recently viewed" history; ``most_viewed`` is
            # the existing honest Store-wide semantic closest to that role.
            PresetSectionEntry("product_section", settings={
                "title": "محصولات پربازدید", "data_source": "most_viewed",
                "display_mode": "carousel", "item_limit": 10,
                "card": _BEAUTY_RETAIL_CARD, **_BEAUTY_WALL_ROW,
            }),
            PresetSectionEntry("newsletter", settings={
                "title": "از تازه‌های فروشگاه باخبر شوید",
                "subtitle": "ایمیل خود را ثبت کنید تا پیشنهادها و محصولات تازه را از دست ندهید.",
                "button_label": "عضویت",
                "background": {"mode": "color", "color": "#F6F6F6"},
            }),
        ), ("hero", "categories", "products_campaign_discounted", "banner_promo4", "products_campaign_newest", "brands", "wall_category_groups", "banner_pair", "wall_collections", "products_most_viewed", "newsletter")),
        **_u10_standard_non_home_pages(),
    },
))

#: Site-target-overhaul (ibolak reference) — the reusable card presentation
#: this Ready Template opts into: the ``fashion_sale`` card style (see
#: ``section_registry.CARD_STYLE_CHOICES``), a portrait product photo
#: (already a registered ``image_ratio`` choice), and no quick-add bar —
#: ibolak's own listing/home cards never offer a one-click add, since a
#: real color/size choice is required first; hiding it here is an honest
#: match, not a fabricated capability.
_FASHION_PROMO_CARD = {"card_style": "fashion_sale", "image_ratio": "portrait", "show_quick_add": False}
#: Part 2B (ibolak Home rebuild) — 5 cards per row on desktop, matching
#: the reference's dense product-wall rhythm (an already-registered
#: ``responsive.desktop_columns`` choice, see ``section_registry.
#: DESKTOP_COLUMN_CHOICES`` — no new primitive needed for this axis).
_FASHION_PROMO_ROW = {"responsive": {"desktop_columns": 5}}


def _fashion_promo_row(title: str, data_source: str) -> PresetSectionEntry:
    return PresetSectionEntry("product_section", settings={
        "title": title, "data_source": data_source, "display_mode": "carousel",
        "item_limit": 14, "card": _FASHION_PROMO_CARD, **_FASHION_PROMO_ROW,
    })

register_layout_preset(LayoutPresetDefinition(
    key="fashion_promo_catalog",
    # Part 2C (ibolak Home precision pass) — merchant visual QA #2: the
    # Part 2B structural rebuild was approved as an architecture, but the
    # macro geometry (hero height, category moments, density, background,
    # content width) still diverged materially from the reference. Bumped
    # again from "2" for the same reason "2" was bumped from "1": the Home
    # composition's real content changed (two category moments instead of
    # one, a shorter/wider hero, denser product rows), so a Draft that
    # already recorded a "2" baseline snapshot must be recognized as
    # *not* matching this new content on reapply.
    #
    # Part 2D (final Home fidelity pass) — bumped again: the Home
    # composition now also includes the new ``catalog_product_wall``
    # section (several additional real category/collection product rows),
    # for the same "content genuinely changed" reason as every prior bump.
    #
    # Micro-fix pass — bumped again: fashion_lifestyle_hero's settings now
    # carry a real ``slides`` list (auto-rotating campaign slider, new
    # composite images), a real content change for the same reason as
    # every prior bump.
    #
    # Second micro-fix pass — bumped again: the category mosaic now reads
    # a real per-product cover image (via the new
    # ``resolve_category_representative_media`` resolver) instead of
    # ``category.image``, and the promo header's main row is a real CSS
    # Grid layout instead of flex — both genuinely change what a merchant
    # sees, for the same reason as every prior bump.
    #
    # Final storefront-polish pass — bumped again: the public header no
    # longer renders the admin-panel shortcut, the promo header's cart
    # control now carries a visible "سبد خرید" label, and every public
    # storefront page now shows the global RastiSi attribution line —
    # all genuinely visible changes, for the same reason as every prior
    # bump.
    version="7",
    is_ready_template=True,
    store_appearance=_complete_store_appearance(
        header="promo_search_nav", hero="split", layout="quarters",
        product_view="campaign_band", card="price_first", badge="sale", motion="dynamic",
        footer="promo_columns", bottom_nav="hidden",
    ),
    label_fa="کاتالوگِ پوشاک و پیشنهادها",
    description_fa="چیدمانِ کاتالوگ‌محور با بنرهایِ تبلیغاتیِ متعدد — مناسبِ پوشاک/مدی که مرتب کمپین/تخفیف اجرا می‌کند.",
    appearance={
        "font": "Vazirmatn", "radius": 14, "button_radius": 999,
        "density": "normal", "motion": "dynamic", "type_scale": "normal",
        "button_style": "filled", "image_fit": "cover", "image_hover": "zoom",
        "card_image_crossfade": True, "card_image_zoom": True,
        # Part 2C — the reference's product wall/hero/category mosaic reads
        # as nearly full-bleed at a 1440 viewport (~14px gutters), not a
        # classic centered ~1200-1320 container. ``content_width`` is an
        # existing, generic, already-registered structural appearance field
        # (``appearance_registry.SITE_CONTENT_WIDTH_CHOICES``) that flows
        # straight into ``--sfb-content-width`` via ``apply_preset``'s
        # existing ``overlay = dict(preset.appearance)`` copy — no new
        # mechanism, and no other Ready Template sets this key, so the
        # other 7 keep whatever their own Draft/CSS default already is.
        # 1500 is the largest registered choice; combined with the existing
        # ``.wrap{width:min(var(--sfb-content-width),calc(100% - 28px))}``
        # rule it resolves to ~1412px at a 1440 viewport — a ~14px gutter,
        # matching the reference's measured content width almost exactly.
        "content_width": 1500,
    },
    default_palette_slug="magenta-pop",
    header={"sticky": True, "announcement_enabled": True, "header_variant": "promo_search_nav"},
    footer={"footer_variant": "promo_columns"},
    pages={
        # Part 2B (ibolak Home rebuild) — the old ``hero_banner``/
        # ``promo_cards``/``amazing_offers``/``brand_carousel`` mix left
        # too much of the shared generic RastiSi Home rhythm (large
        # colored promo blocks, a brand-name pill row) that has no
        # equivalent in the reference at all. Real merchant data behind
        # those sections is untouched — a merchant can still add any of
        # them back in the editor.
        #
        # Part 2C (precision pass) — the reference actually has TWO
        # distinct category moments, not one: a compact circular shortcut
        # rail close to the header (``fashion_flat``, moved here BEFORE the
        # hero — it used to render after it), and a larger post-hero
        # category mosaic (the new ``fashion_mosaic`` display_mode). Both
        # reuse ``category_grid``'s existing empty-``category_ids``
        # auto-pick behavior (real, active top-level Store categories —
        # never a hardcoded Store-specific ID, safe for any merchant who
        # applies this Ready Template). The product wall stays on the 4
        # ID-free, Store-agnostic data sources (``PRODUCT_SECTION_
        # DATA_SOURCES``'s "category"/"collection"/"brand" all require a
        # real per-Store numeric ``source_id`` — hardcoding one of
        # rasti-mode-demo's own here would either leak that Store's ID into
        # every other merchant's copy of this Ready Template or silently
        # render empty for them; neither is acceptable for an official,
        # reusable Ready Template) — each row's ``item_limit`` raised for a
        # visibly denser, longer carousel per section.
        #
        # Part 2D (final Home fidelity pass) — merchant visual QA measured
        # the Home page at only ~41% of the reference's merchandising
        # length and asked for a GENERIC, ID-free fix rather than accepting
        # that as a ceiling. ``catalog_product_wall`` is that fix: it never
        # stores a category/collection id at all — at render time it
        # resolves whichever real categories/collections the CURRENT Store
        # actually has (the Store-agnostic auto-pick, see that section's
        # own registration comment) and renders one compact product row per
        # real, non-empty group it finds, up to ``max_groups``. Combined
        # with the 4 explicit ID-free rows above, this brings the total
        # merchandising-row count into the reference's own range without
        # ever hardcoding a Store-specific id or duplicating identical
        # product groups under different headings.
        "home": authored_legacy_home("fashion_promo_catalog", (
            PresetSectionEntry("category_grid", settings={"display_mode": "fashion_flat", "item_limit": 12}),
            # Micro-fix pass — merchant: "hero must auto-slide". Three
            # slides, each a real deterministic Pillow composite of
            # different brand-free Rasti Mode Demo product photos (own
            # distinct headline/subtitle copy per slide) -- reuses the
            # section's existing ``slides`` list support (see
            # fashion_lifestyle_hero.html), never a new section type.
            PresetSectionEntry("fashion_lifestyle_hero", settings={"slides": [
                {
                    "image": "campaign_hero.webp", "eyebrow": "کالکشن تازه",
                    "title": "وقت تخفیف ویژه‌ی راستی مد!",
                    "subtitle": "جدیدترین پوشاک و کیف و کفش فصل — با تخفیف‌های ویژه، همین امروز کشف کن.",
                    "cta_label": "مشاهده کالکشن",
                },
                {
                    "image": "campaign_hero_2.webp", "eyebrow": "پیشنهاد ویژه",
                    "title": "استایل پاییزی، قیمت شگفت‌انگیز!",
                    "subtitle": "ژاکت و شلوار جین منتخب فصل — همین حالا با بهترین قیمت سفارش بده.",
                    "cta_label": "مشاهده محصولات",
                },
                {
                    "image": "campaign_hero_3.webp", "eyebrow": "تازه‌های فروشگاه",
                    "title": "کالکشن جدید کاپشن رسید!",
                    "subtitle": "طرح‌ها و رنگ‌بندی‌های تازه — برای هر سبک، یک انتخاب مناسب.",
                    "cta_label": "مشاهده کالکشن",
                },
            ]}),
            PresetSectionEntry("category_grid", settings={"display_mode": "fashion_mosaic", "item_limit": 8}),
            _fashion_promo_row("تخفیف‌های ویژه", "discounted"),
            _fashion_promo_row("جدیدترین‌ها", "newest"),
            _fashion_promo_row("پرفروش‌ترین‌ها", "best_sellers"),
            _fashion_promo_row("پربازدیدترین‌ها", "most_viewed"),
            PresetSectionEntry("catalog_product_wall", settings={
                "source_mode": "categories_then_collections", "max_groups": 8,
                "products_per_group": 14, "minimum_products": 3, "skip_empty_groups": True,
                "show_view_all": True, "card": _FASHION_PROMO_CARD, **_FASHION_PROMO_ROW,
            }),
        ), ("categories_flat", "hero", "categories_mosaic", "products_discounted", "products_newest", "products_bestsellers", "products_most_viewed", "wall_groups")),
        **{
            **_u10_standard_non_home_pages(),
            # Site-target-overhaul — the master contract's shared
            # listing/product_detail *composition* (which sections, in
            # which order) is intentionally unchanged (still exactly
            # ``_U10_STANDARD_LISTING_PAGE``/``_U10_STANDARD_PRODUCT_DETAIL_PAGE``'s
            # one ``product_listing``/(``product_main``, ``product_description``,
            # ``related_products``) section list) -- only each entry's own
            # ``settings.layout_variant``/``settings.card`` differ, exactly
            # the same axis ``card_style`` already varies on. No other Ready
            # Template's ``pages[...]`` is touched by this override.
            "listing": (PresetSectionEntry("product_listing", semantic_slot_key="products.listing", settings={
                "layout_variant": "sidebar_dense", "card": _FASHION_PROMO_CARD,
            }),),
            "search": (PresetSectionEntry("product_listing", semantic_slot_key="products.search", settings={
                "layout_variant": "sidebar_dense", "card": _FASHION_PROMO_CARD,
            }),),
            "product_detail": (
                PresetSectionEntry("product_main", semantic_slot_key="product.main", settings={"layout_variant": "fashion"}),
                PresetSectionEntry("product_description", semantic_slot_key="product.description"),
                PresetSectionEntry("related_products", semantic_slot_key="product.related", settings={"card": _FASHION_PROMO_CARD}),
            ),
        },
    },
))

register_layout_preset(LayoutPresetDefinition(
    key="playful_lifestyle",
    is_ready_template=True,
    store_appearance=_complete_store_appearance(
        header="boutique_centered", hero="split", layout="quarters",
        product_view="carousel", card="soft_capsule", badge="none", motion="dynamic",
        footer="boutique_editorial", bottom_nav="hidden",
    ),
    label_fa="سبکِ زندگیِ شاد",
    description_fa="چیدمانِ رنگی و پرحرکت با گوشه‌هایِ گرد — مناسبِ برندهایِ سبکِ زندگی/کودک/سرگرمی.",
    appearance={
        "font": "Vazirmatn", "radius": 20, "button_radius": 20,
        "density": "relaxed", "motion": "dynamic", "type_scale": "normal",
        "button_style": "soft", "image_fit": "cover", "image_hover": "zoom",
        "card_image_crossfade": True, "card_image_zoom": True,
    },
    default_palette_slug="mint",
    header={"sticky": True, "announcement_enabled": True, "header_variant": "boutique_centered"},
    footer={"show_newsletter": True, "footer_variant": "boutique_editorial"},
    pages={
        "home": authored_legacy_home("playful_lifestyle", (
            PresetSectionEntry("story_rail"),
            PresetSectionEntry("hero_banner", settings={"hero_style": "split"}),
            PresetSectionEntry("category_grid", settings={"display_mode": "circular"}),
            PresetSectionEntry("product_section", settings={
                "title": "تازه‌های فروشگاه", "data_source": "newest", "display_mode": "carousel",
                "item_limit": 8, "card": {"card_style": "standard"},
            }),
            PresetSectionEntry("testimonials"),
        ), ("story", "hero", "categories", "products_newest", "testimonials")),
        **_u10_standard_non_home_pages(),
    },
))

register_layout_preset(LayoutPresetDefinition(
    key="utility_catalog",
    is_ready_template=True,
    store_appearance=_complete_store_appearance(
        header="legacy_default", hero="none", layout="quarters",
        product_view="grid", card="technical_spec", badge="none", motion="none",
        footer="legacy_default", bottom_nav="hidden",
    ),
    label_fa="کاتالوگِ ابزار و صنعتی",
    description_fa="چیدمانِ ساده و کارکردی، بدونِ حرکت/تزیینِ اضافه — مناسبِ ابزار/قطعات/کالایِ صنعتی که تمرکز باید کاملاً رویِ مشخصات و پیدا کردنِ سریعِ کالا باشد.",
    appearance={
        "font": "Arial", "radius": 4, "button_radius": 4,
        "density": "compact", "motion": "none", "type_scale": "compact",
        "button_style": "outline", "image_fit": "contain", "image_hover": "none",
        "card_image_crossfade": False, "card_image_zoom": False,
    },
    default_palette_slug="navy",
    header={"sticky": True, "announcement_enabled": False, "header_variant": "legacy_default"},
    footer={"show_newsletter": False, "footer_variant": "legacy_default"},
    pages={
        "home": authored_legacy_home("utility_catalog", (
            PresetSectionEntry("category_grid", settings={"display_mode": "grid"}),
            PresetSectionEntry("product_section", settings={
                "title": "جدیدترین کالاها", "data_source": "newest", "display_mode": "grid",
                "item_limit": 12, "card": {"card_style": "compact", "show_rating": False},
            }),
            PresetSectionEntry("best_sellers"),
            PresetSectionEntry("trust_features"),
        ), ("categories", "products_newest", "best_sellers", "trust")),
        **_u10_standard_non_home_pages(),
    },
))

register_layout_preset(LayoutPresetDefinition(
    key="editorial_jewelry",
    version="2",
    is_ready_template=True,
    store_appearance=_complete_store_appearance(
        header="atelier_nav", hero="atelier_triptych", layout="quarters",
        product_view="grid", card="editorial_minimal", badge="none", motion="subtle",
        footer="boutique_editorial", bottom_nav="hidden",
    ),
    label_fa="جواهراتِ مجله‌ای",
    description_fa="چیدمان آتلیه‌ای و تصویرمحور با سه‌قاب قوسی، موزاییک دسته‌بندی، کارت‌های مینیمال و فوتر بسیار سبک — مناسب جواهر، اکسسوری و محصولات هنری.",
    appearance={
        "font": "Vazirmatn", "radius": 4, "button_radius": 2,
        "density": "relaxed", "motion": "subtle", "type_scale": "large",
        "button_style": "outline", "image_fit": "cover", "image_hover": "zoom",
        "card_image_crossfade": False, "card_image_zoom": False,
        "content_width": 1320,
    },
    default_palette_slug="atelier-ivory",
    header={
        "sticky": True, "announcement_enabled": False,
        "show_search": True, "show_account": True, "show_wishlist": False, "show_cart": True,
        "header_variant": "atelier_nav",
    },
    footer={
        "show_about": False, "show_contact": False, "show_categories": False,
        "show_quick_links": False, "show_social": False,
        "show_trust_badges": False, "show_payment_logos": False,
        "show_newsletter": False, "show_copyright": True,
        "footer_variant": "boutique_editorial",
    },
    pages={
        "home": authored_legacy_home("editorial_jewelry", (
            # Store-owned HeroSlide photography is composed into a reusable
            # editorial triptych; no reference imagery or merchant IDs live
            # in the preset.
            PresetSectionEntry("hero_banner", settings={
                "hero_style": "atelier_triptych", "text_position": "end",
                "autoplay": False, "show_arrows": False, "show_dots": False,
            }),
            # Image-first category discovery from the current Store's real
            # active top-level categories and representative product media.
            PresetSectionEntry("category_grid", settings={
                "title": "", "display_mode": "atelier_mosaic", "item_limit": 12,
            }),
            # Two editorial campaign panels sourced from real merchant banners.
            PresetSectionEntry("multi_banner", settings={
                "item_limit": 2, "offset": 0, "layout_variant": "atelier-duo",
                "responsive": {"desktop_columns": 2, "tablet_columns": 2, "mobile_columns": 1},
            }),
            PresetSectionEntry("product_section", settings={
                "title": "جدیدترین محصولات", "data_source": "newest", "display_mode": "grid",
                "item_limit": 8, "show_view_all": False,
                "responsive": {"desktop_columns": 4, "tablet_columns": 2, "mobile_columns": 2},
                "card": {
                    "card_style": "minimal", "image_ratio": "square",
                    "show_brand": False, "show_rating": False, "show_wishlist": False,
                    "show_badge": False, "show_quick_add": False, "card_border": True,
                },
            }),
            PresetSectionEntry("product_section", settings={
                "title": "پرفروش‌ترین محصولات", "data_source": "best_sellers", "display_mode": "grid",
                "item_limit": 4, "show_view_all": False,
                "responsive": {"desktop_columns": 4, "tablet_columns": 2, "mobile_columns": 2},
                "card": {
                    "card_style": "minimal", "image_ratio": "square",
                    "show_brand": False, "show_rating": False, "show_wishlist": False,
                    "show_badge": False, "show_quick_add": False, "card_border": True,
                },
            }),
            # A second image-led story moment and one full-width informational
            # banner use the same Store-owned PromotionalBanner pool. Empty
            # merchant data simply renders nothing; no fake FAQ/size-guide
            # copy is inserted by the Ready Template.
            PresetSectionEntry("multi_banner", settings={
                "item_limit": 2, "offset": 2, "layout_variant": "atelier-duo",
                "responsive": {"desktop_columns": 2, "tablet_columns": 2, "mobile_columns": 1},
            }),
            PresetSectionEntry("multi_banner", settings={
                "item_limit": 1, "offset": 4, "layout_variant": "atelier-wide",
                "responsive": {"desktop_columns": 1, "tablet_columns": 1, "mobile_columns": 1},
            }),
        ), ("hero", "categories_mosaic", "banner_duo_a", "products_newest", "products_bestsellers", "banner_duo_b", "banner_wide")),
        **_u10_standard_non_home_pages(),
    },
))

register_layout_preset(LayoutPresetDefinition(
    key="dark_digital",
    version="2",
    is_ready_template=True,
    store_appearance=_complete_store_appearance(
        header="luxury_search", hero="luxury_showcase", layout="quarters",
        product_view="grid", card="luxury_dark", badge="sale", motion="subtle",
        footer="dark_tech", bottom_nav="luxury_floating_cart",
    ),
    label_fa="دیجیتالِ تیره لوکس",
    description_fa="فروشگاه تیره و پرمیوم با جستجوی برجسته، ویترین تصویری لوکس، میانبرهای دسته‌بندی، کارت‌های طلایی و ناوبری پایین موبایل.",
    appearance={
        "font": "Vazirmatn", "radius": 18, "button_radius": 14,
        "density": "normal", "motion": "subtle", "type_scale": "normal",
        "button_style": "filled", "image_fit": "cover", "image_hover": "zoom",
        "card_image_crossfade": True, "card_image_zoom": True,
        "content_width": 1320,
    },
    default_palette_slug="theme-black-gold",
    header={
        "sticky": True, "announcement_enabled": False,
        "show_search": True, "show_account": True, "show_wishlist": False, "show_cart": True,
        "header_variant": "luxury_search",
    },
    footer={
        "show_about": True, "show_contact": True, "show_categories": True,
        "show_quick_links": True, "show_social": True,
        "show_trust_badges": True, "show_payment_logos": True,
        "show_newsletter": False, "show_copyright": True,
        "footer_variant": "dark_tech",
        "mobile_nav_variant": "luxury_floating_cart",
    },
    pages={
        "home": authored_legacy_home("dark_digital", (
            PresetSectionEntry("hero_banner", settings={
                "hero_style": "luxury_showcase", "text_position": "end",
                "autoplay": False, "show_arrows": False, "show_dots": True,
            }),
            PresetSectionEntry("category_grid", settings={
                "title": "دسته‌بندی محصولات", "display_mode": "luxury_shortcuts", "item_limit": 5,
            }),
            PresetSectionEntry("product_section", settings={
                "title": "منتخب امروز", "data_source": "newest", "display_mode": "grid",
                "item_limit": 8, "show_view_all": True,
                "responsive": {
                    "desktop_columns": 4, "tablet_columns": 3, "mobile_columns": 2,
                    "hide_on_desktop": False, "hide_on_tablet": False, "hide_on_mobile": False,
                },
                "card": {
                    "card_style": "luxury_dark", "image_ratio": "square",
                    "show_brand": True, "show_price": True, "show_badge": True,
                    "show_wishlist": True, "show_quick_add": True, "show_rating": False,
                    "card_border": True, "quick_add_reveal": "always",
                },
            }),
            PresetSectionEntry("trust_features"),
            PresetSectionEntry("product_section", settings={
                "title": "پرفروش‌ترین‌ها", "data_source": "best_sellers", "display_mode": "carousel",
                "item_limit": 8, "show_view_all": True,
                "responsive": {
                    "desktop_columns": 4, "tablet_columns": 3, "mobile_columns": 2,
                    "hide_on_desktop": False, "hide_on_tablet": False, "hide_on_mobile": False,
                },
                "card": {
                    "card_style": "luxury_dark", "image_ratio": "square",
                    "show_brand": True, "show_price": True, "show_badge": True,
                    "show_wishlist": True, "show_quick_add": True, "show_rating": False,
                    "card_border": True, "quick_add_reveal": "always",
                },
            }),
        ), ("hero", "categories", "products_today", "trust", "products_bestsellers")),
        **_u10_standard_non_home_pages(),
    },
))


# Importing the data-only A8 catalog registers its material revisions only
# after all eight complete historical identities above have been retained.
from . import a8_ready_templates as _a8_ready_templates  # noqa: E402,F401
