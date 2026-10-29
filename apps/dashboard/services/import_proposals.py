"""مواردِ مرجعِ پیشنهادی در ورودِ اطلاعاتِ اکسل: برند، دسته‌بندی، زیردسته، ویژگی و مقدارِ ویژگی.

اصلِ طراحی (همان موتورِ واردات، بدونِ موتورِ دوم): ``import_xlsx`` / ``import_service`` همچنان تنها مسیرِ خواندن، اعتبارسنجی و
اعمالِ فایل‌اند. این ماژول فقط دو کار می‌کند:

1. **تشخیصِ هم‌ارزی** (``entity_key``/``ReferenceIndex``): نامی که در این Store از قبل هست — با هر تفاوتِ فارسی/عربیِ حروف،
   نیم‌فاصله/فاصله، شکلِ ارائه‌یِ حروف، نویسه‌هایِ نامرئی یا همان اسلاگ — «موجود» حساب می‌شود و پیشنهادی ثبت نمی‌شود (بدونِ تکرار).
2. **صفِ تأیید** (``ImportProposal``): نامِ واقعاً تازه هیچ‌وقت خودکار ساخته نمی‌شود؛ پیشنهادِ ``pending`` می‌شود و فقط با تأییدِ
   مدیرِ دارایِ مجوزِ همان موجودیت در جدولِ واقعیِ همان Store ساخته می‌شود (از همان سرویس‌هایِ برند/دسته/ویژگی). رد‌شدن چیزی
   نمی‌سازد؛ ردیف‌هایِ وابسته خطایِ قابل‌اصلاح می‌مانند و اجرا مسدود است. اجرایِ مجددِ همان فایل، چیزی را دوباره نمی‌سازد."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from django.db import transaction
from django.utils import timezone

from apps.catalog.models import Attribute, AttributeValue, Brand, Category
from apps.catalog.services import attribute_service, brand_service
from apps.core.models import ImportProposal
from apps.core.services.audit_service import record_audit_event
from apps.core.utils import normalize_text
from apps.dashboard.services.catalog_admin_service import generate_unique_slug
from apps.stores.authorization import ATTRIBUTE_MANAGE, BRAND_MANAGE, CATEGORY_MANAGE

K = ImportProposal.Kind
S = ImportProposal.Status

#: مجوزِ لازم برایِ تأیید/ردِ هر نوع (همان مجوزِ ساختنِ آن موجودیت در پنل).
KIND_PERMISSION = {
    K.BRAND: BRAND_MANAGE, K.CATEGORY: CATEGORY_MANAGE, K.SUBCATEGORY: CATEGORY_MANAGE,
    K.ATTRIBUTE: ATTRIBUTE_MANAGE, K.ATTRIBUTE_VALUE: ATTRIBUTE_MANAGE,
}

# ───────────────────────────── هم‌ارزیِ نام‌ها ─────────────────────────────

_INVISIBLE = dict.fromkeys(map(ord, "‌‍‎‏‪‫‬‭‮⁦⁧⁨⁩﻿ـ­"), None)
_FOLD = str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک", "ة": "ه", "ۀ": "ه", "أ": "ا", "إ": "ا", "ٱ": "ا", "ؤ": "و"})
_DIACRITICS = re.compile("[ً-ٰٟۖ-ۭ]")
_PUNCT = re.compile(r"[\s\-_‐‑–—./\\|·،,;:؛()\[\]{}'\"“”«»`~!?@#$%^&*+=<>٬]+")


def entity_key(text) -> str:
    """کلیدِ هم‌ارزیِ یک نامِ مرجع: ارقام→لاتین، ي/ك/ة…→فارسی، شکل‌هایِ ارائه (NFKC)، نیم‌فاصله/فاصله/نویسه‌هایِ نامرئی/
    اعراب/کشیده/نشانه‌گذاری حذف و حروفِ لاتین کوچک. «می‌شود» = «می شود» = «میشود»؛ «Nike» = «nike»؛ «ﻛﻮﺷﻲ» = «کوشی»."""
    value = normalize_text(text)
    value = unicodedata.normalize("NFKC", value).translate(_INVISIBLE)
    value = _DIACRITICS.sub("", value).translate(_FOLD).lower()
    return _PUNCT.sub("", value)


def display_name(text) -> str:
    """نامِ نمایشی/ذخیره‌شونده: ارقام و حروفِ عربی نرمال، نویسه‌هایِ نامرئیِ جهت‌دار حذف، نیم‌فاصله حفظ می‌شود."""
    value = unicodedata.normalize("NFKC", normalize_text(text))
    value = value.translate(dict.fromkeys(map(ord, "‎‏‪‫‬‭‮⁦⁧⁨⁩﻿­"), None))
    return re.sub(r"\s+", " ", value).strip()


_PATH_SPLIT = re.compile(r"\s*[>›»<‹«/\\|]\s*")


def split_category_path(text) -> list[str]:
    return [display_name(part) for part in _PATH_SPLIT.split(str(text or "")) if display_name(part)]


# ───────────────────────────── نمایه‌یِ مواردِ موجودِ Store ─────────────────────────────

@dataclass
class CategoryResolution:
    category: Category | None = None
    #: پیشنهادهایِ لازم: ``[(kind, name, parent_name)]`` به ترتیبِ ساخت (والد پیش از فرزند)
    proposals: list = field(default_factory=list)
    error: str = ""


class ReferenceIndex:
    """نمایه‌یِ برندها/دسته‌ها/ویژگی‌هایِ *همین Store* برایِ تشخیصِ مواردِ موجود (Store-scoped؛ بارگذاریِ تنبل و یک‌بار)."""

    def __init__(self, store):
        self.store = store
        self._brands = self._roots = self._children = self._attributes = self._values = None

    # --- برند
    def brand(self, text) -> Brand | None:
        if self._brands is None:
            self._brands = {}
            for b in Brand.objects.filter(store=self.store).order_by("-is_active", "pk"):
                for candidate in (b.name, b.slug, b.name_en):
                    key = entity_key(candidate)
                    if key:
                        self._brands.setdefault(key, b)
        return self._brands.get(entity_key(text))

    # --- دسته
    def _load_categories(self):
        if self._roots is not None:
            return
        self._roots, self._children = {}, {}
        for c in Category.objects.filter(store=self.store).order_by("pk"):
            for candidate in (c.name, c.slug):
                key = entity_key(candidate)
                if not key:
                    continue
                if c.parent_id is None:
                    self._roots.setdefault(key, c)
                else:
                    self._children.setdefault((c.parent_id, key), c)

    def root_category(self, text) -> Category | None:
        self._load_categories()
        return self._roots.get(entity_key(text))

    def child_category(self, parent: Category, text) -> Category | None:
        self._load_categories()
        return self._children.get((parent.pk, entity_key(text)))

    def resolve_category(self, path_text) -> CategoryResolution:
        """مسیرِ «اصلی > زیردسته» (یا سه سطح) را حل می‌کند. فقط زیردسته‌ها قابلِ انتخابِ کالا هستند؛ دسته‌یِ اصلیِ تنها خطاست."""
        parts = split_category_path(path_text)
        if not parts:
            return CategoryResolution(error="دسته‌بندی خالی است.")
        if len(parts) == 1:
            self._load_categories()
            key = entity_key(parts[0])
            leaves = {c.pk: c for (_pid, k), c in self._children.items() if k == key}
            if len(leaves) == 1:
                return CategoryResolution(category=next(iter(leaves.values())))
            if len(leaves) > 1:
                return CategoryResolution(error=f"نامِ دسته‌بندیِ «{parts[0]}» مبهم است؛ مسیرِ کامل را («اصلی > زیردسته») بنویسید.")
            if self.root_category(parts[0]) is not None:
                return CategoryResolution(error=f"«{parts[0]}» یک دسته‌یِ اصلی است؛ کالا باید در یک زیردسته باشد (مثلاً «{parts[0]} > …»).")
            return CategoryResolution(error=f"دسته‌بندیِ «{parts[0]}» پیدا نشد. برایِ پیشنهادِ دسته‌یِ تازه مسیرِ کامل را بنویسید: «دسته‌یِ اصلی > زیردسته».")
        node, depth = self.root_category(parts[0]), 0
        if node is not None:
            depth = 1
            while depth < len(parts):
                nxt = self.child_category(node, parts[depth])
                if nxt is None:
                    break
                node, depth = nxt, depth + 1
            if depth == len(parts):
                return CategoryResolution(category=node)
        if len(parts) == 2:
            if node is None:  # دسته‌یِ اصلی هم تازه است
                return CategoryResolution(proposals=[(K.CATEGORY, parts[0], ""), (K.SUBCATEGORY, parts[1], parts[0])])
            return CategoryResolution(proposals=[(K.SUBCATEGORY, parts[1], node.name)])
        return CategoryResolution(error=(
            f"مسیرِ دسته‌بندیِ «{' > '.join(parts)}» پیدا نشد؛ پیشنهادِ دسته‌یِ تازه فقط تا دو سطح («اصلی > زیردسته») پذیرفته می‌شود."
        ))

    # --- ویژگی
    def _load_attributes(self):
        if self._attributes is not None:
            return
        self._attributes, self._values = {}, {}
        for a in Attribute.objects.filter(store=self.store, is_active=True).order_by("pk"):
            for candidate in (a.label, a.code):
                key = entity_key(candidate)
                if key:
                    self._attributes.setdefault(key, a)
        for v in AttributeValue.objects.filter(attribute__store=self.store, is_active=True).select_related("attribute").order_by("pk"):
            for candidate in (v.label, v.value):
                key = entity_key(candidate)
                if key:
                    self._values.setdefault((v.attribute_id, key), v)

    def attribute(self, text) -> Attribute | None:
        self._load_attributes()
        return self._attributes.get(entity_key(text))

    def attribute_value(self, attribute: Attribute, text) -> AttributeValue | None:
        self._load_attributes()
        return self._values.get((attribute.pk, entity_key(text)))


# ───────────────────────────── دفترِ پیشنهادهایِ یک Job ─────────────────────────────

def proposal_ref(kind, name, parent_name="") -> dict:
    """مرجعِ سبکِ یک پیشنهاد که روی ``normalized_data_summary["awaiting"]`` ردیف نوشته می‌شود."""
    return {"kind": str(kind), "name": display_name(name), "parent": display_name(parent_name)}


class ProposalBook:
    """وضعیتِ پیشنهادهایِ *همین Job* برایِ اعتبارسنج‌ها (فقط خواندن)."""

    def __init__(self, job):
        self._by_key = {}
        if job is not None and job.pk:
            for p in ImportProposal.objects.filter(job=job):
                self._by_key[(p.kind, p.parent_key, p.name_key)] = p

    def get(self, kind, name, parent_name="") -> ImportProposal | None:
        return self._by_key.get((str(kind), entity_key(parent_name), entity_key(name)))


def sync_from_outcomes(job, outcomes) -> dict:
    """پیشنهادهایِ لازم برایِ پیش‌نمایشِ فعلی را ثبت/به‌روز می‌کند (فقط ``ImportProposal``؛ هیچ داده‌یِ کاتالوگ نوشته نمی‌شود).

    * هر ردیفِ دارایِ ``awaiting`` یک پیشنهادِ یکتا (job، نوع، والد، نام) می‌سازد و شماره‌ردیف‌ها جمع می‌شوند؛
    * پیشنهادِ ``pending`` که دیگر هیچ ردیفی به آن نیاز ندارد (فایل اصلاح شد) حذف می‌شود؛
    * پیشنهادِ ``approved`` که رکوردش بعداً پاک شده و دوباره لازم است، به ``pending`` برمی‌گردد."""
    wanted: dict = {}
    for outcome in outcomes:
        for ref in (outcome.normalized_data_summary or {}).get("awaiting", []):
            key = (ref["kind"], entity_key(ref.get("parent", "")), entity_key(ref["name"]))
            entry = wanted.setdefault(key, {"ref": ref, "rows": set()})
            entry["rows"].add(outcome.row_number)
    existing = {(p.kind, p.parent_key, p.name_key): p for p in ImportProposal.objects.filter(job=job)}
    created = updated = removed = 0
    for key, entry in wanted.items():
        rows, ref = sorted(entry["rows"]), entry["ref"]
        proposal = existing.get(key)
        if proposal is None:
            ImportProposal.objects.create(
                store=job.store, job=job, kind=ref["kind"], name=ref["name"][:150], name_key=key[2][:160],
                parent_name=ref.get("parent", "")[:150], parent_key=key[1][:160], source_rows=rows,
                source_filename=job.original_filename, requested_by=job.requested_by,
            )
            created += 1
            continue
        fields = []
        if proposal.source_rows != rows:
            proposal.source_rows = rows
            fields.append("source_rows")
        if proposal.status == S.APPROVED:
            proposal.status, proposal.decided_by, proposal.decided_at = S.PENDING, None, None
            proposal.created_object_type, proposal.created_object_id = "", None
            fields += ["status", "decided_by", "decided_at", "created_object_type", "created_object_id"]
        if fields:
            proposal.save(update_fields=fields + ["updated_at"])
            updated += 1
    for key, proposal in existing.items():
        if key not in wanted and proposal.status == S.PENDING:
            proposal.delete()
            removed += 1
    return {"created": created, "updated": updated, "removed": removed, "pending": len(wanted)}


# ───────────────────────────── تصمیم: تأیید / رد ─────────────────────────────

class ProposalError(Exception):
    """تصمیم ممکن نیست — پیام برایِ نمایش به مدیر امن است."""


class ProposalAlreadyDecided(ProposalError):
    """این پیشنهاد قبلاً تصمیم‌گیری شده؛ تکرارِ تأیید هیچ رکوردِ دومی نمی‌سازد (idempotent)."""


def _lock_store(store):
    from apps.stores.models import Store

    Store.objects.select_for_update().get(pk=store.pk)  # ساختِ هم‌زمانِ موارد در یک Store پشتِ هم می‌نشیند (PostgreSQL)


def _materialize(proposal: ImportProposal, actor):
    """رکوردِ واقعی را می‌سازد — یا اگر همان نام (به‌معنایِ ``entity_key``) از قبل هست، همان را برمی‌گرداند. فقط داخلِ تراکنش."""
    store, index = proposal.store, ReferenceIndex(proposal.store)
    try:
        if proposal.kind == K.BRAND:
            return index.brand(proposal.name) or brand_service.create_brand(store, name=proposal.name), "Brand"
        if proposal.kind == K.CATEGORY:
            existing = index.root_category(proposal.name)
            if existing is not None:
                return existing, "Category"
            return Category.objects.create(
                store=store, name=proposal.name, icon="📁", slug=generate_unique_slug(Category, proposal.name, store=store),
            ), "Category"
        if proposal.kind == K.SUBCATEGORY:
            parent = index.root_category(proposal.parent_name)
            if parent is None:
                parent_proposal = ImportProposal.objects.select_for_update().filter(
                    job=proposal.job, kind=K.CATEGORY, name_key=proposal.parent_key,
                ).first()
                if parent_proposal is None or parent_proposal.status == S.REJECTED:
                    raise ProposalError(f"دسته‌یِ اصلیِ «{proposal.parent_name}» وجود ندارد یا رد شده است؛ ابتدا آن را تأیید کنید.")
                _decide_approve(parent_proposal, actor)
                parent = index.root_category(proposal.parent_name) or Category.objects.get(pk=parent_proposal.created_object_id)
            existing = index.child_category(parent, proposal.name)
            if existing is not None:
                return existing, "Category"
            return Category.objects.create(
                store=store, name=proposal.name, icon="📁", parent=parent,
                slug=generate_unique_slug(Category, proposal.name, store=store),
            ), "Category"
        if proposal.kind == K.ATTRIBUTE:
            return index.attribute(proposal.name) or attribute_service.create_attribute(store, label=proposal.name), "Attribute"
        if proposal.kind == K.ATTRIBUTE_VALUE:
            attribute = index.attribute(proposal.parent_name)
            if attribute is None:
                raise ProposalError(f"ویژگیِ «{proposal.parent_name}» وجود ندارد؛ ابتدا آن را در بخشِ ویژگی‌ها بسازید.")
            return index.attribute_value(attribute, proposal.name) or attribute_service.create_attribute_value(attribute, label=proposal.name), "AttributeValue"
    except (brand_service.BrandError, attribute_service.AttributeError_) as exc:
        raise ProposalError(str(exc)) from exc
    raise ProposalError("نوعِ پیشنهاد پشتیبانی نمی‌شود.")


def _decide_approve(proposal: ImportProposal, actor) -> ImportProposal:
    if proposal.status == S.APPROVED:
        raise ProposalAlreadyDecided("این مورد قبلاً تأیید شده است.")
    if proposal.status == S.REJECTED:
        raise ProposalAlreadyDecided("این مورد رد شده است؛ فایل را اصلاح و دوباره بارگذاری کنید.")
    obj, object_type = _materialize(proposal, actor)
    proposal.status, proposal.decided_by, proposal.decided_at = S.APPROVED, actor, timezone.now()
    proposal.created_object_type, proposal.created_object_id = object_type, obj.pk
    proposal.save(update_fields=["status", "decided_by", "decided_at", "created_object_type", "created_object_id", "updated_at"])
    record_audit_event(
        store=proposal.store, actor=actor, action_code="import.proposal_approved",
        object_type="ImportProposal", object_id=str(proposal.pk), object_label=proposal.path_label,
        after={"kind": proposal.kind, "created": f"{object_type}#{obj.pk}", "rows": proposal.source_rows},
        metadata={"job": proposal.job_id, "file": proposal.source_filename}, request_id=f"proposal-{proposal.pk}-approve",
    )
    return proposal


@transaction.atomic
def approve(proposal_id: int, *, store, actor) -> ImportProposal:
    _lock_store(store)
    proposal = ImportProposal.objects.select_for_update().select_related("store", "job").get(pk=proposal_id, store=store)
    return _decide_approve(proposal, actor)


@transaction.atomic
def reject(proposal_id: int, *, store, actor, note: str = "") -> ImportProposal:
    proposal = ImportProposal.objects.select_for_update().select_related("store", "job").get(pk=proposal_id, store=store)
    if proposal.status != S.PENDING:
        raise ProposalAlreadyDecided("این مورد قبلاً تصمیم‌گیری شده است.")
    proposal.status, proposal.decided_by, proposal.decided_at = S.REJECTED, actor, timezone.now()
    proposal.decision_note = (note or "").strip()[:300]
    proposal.save(update_fields=["status", "decided_by", "decided_at", "decision_note", "updated_at"])
    record_audit_event(
        store=store, actor=actor, action_code="import.proposal_rejected",
        object_type="ImportProposal", object_id=str(proposal.pk), object_label=proposal.path_label,
        after={"kind": proposal.kind, "rows": proposal.source_rows, "note": proposal.decision_note},
        metadata={"job": proposal.job_id, "file": proposal.source_filename}, request_id=f"proposal-{proposal.pk}-reject",
    )
    return proposal


def proposal_summary(job) -> dict:
    """شمارشِ پیشنهادهایِ یک Job برایِ صفحه‌یِ پیش‌نمایش و قفلِ اجرا."""
    counts = {S.PENDING: 0, S.APPROVED: 0, S.REJECTED: 0}
    for status in ImportProposal.objects.filter(job=job).values_list("status", flat=True):
        counts[status] = counts.get(status, 0) + 1
    return {"pending": counts[S.PENDING], "approved": counts[S.APPROVED], "rejected": counts[S.REJECTED], "total": sum(counts.values())}
