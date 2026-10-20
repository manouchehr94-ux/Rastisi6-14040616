"""مدیریت اعضای تیم فروشگاه (Staff/Membership) — افزودن، تغییر نقش، لغو عضویت، انتقال مالکیت.

بر پایه‌ی مدل و پایاییِ ``StoreMembership`` (Phase 1B) و کلید مجوز
``STAFF_MANAGE`` در ``apps.stores.authorization`` بنا شده است — این ماژول
هیچ قید یا نقشِ تازه‌ای اضافه نمی‌کند، فقط لایه‌ی سرویسِ عملیاتی روی
مدلِ از پیش موجود است.

جریان دعوتِ توکنی/تأییدشده با پیامک (invited -> پذیرشِ خودِ کاربر) عمداً
پیاده‌سازی نشده: صاحبِ فروشگاه دارد یک عضوِ تیمِ خودش (شناخته‌شده، نه یک
غریبه‌ی ناشناس) را اضافه می‌کند، پس افزودن بلافاصله عضویتِ ACTIVE می‌سازد
(مشابه رفتار «افزودنِ عضو تیم» در اغلب پنل‌های ادمین ساده). این محدودیت در
گزارش تکمیل پنل مدیریت مستند شده است.
"""

import re
import unicodedata
from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core.phone import InvalidPhoneError, normalize_iranian_phone
from apps.core.services.audit_service import record_audit_event
from apps.stores.models import StoreMembership

User = get_user_model()

_INVISIBLE_RE = re.compile("[\u200b\u200d\u200e\u200f\u202a-\u202e\u2060\ufeff]")
NAME_MAX_LENGTH = 60

#: توضیحِ کوتاهِ هر نقش برایِ فرمِ افزودن/فهرست — فقط توضیح است؛ مرجعِ مجوز همچنان
#: ``apps.stores.authorization.ROLE_PERMISSIONS`` است (هیچ مجوزِ تازه‌ای این‌جا ساخته نمی‌شود).
ROLE_DESCRIPTIONS = {
    StoreMembership.Role.OWNER: "همهٔ دسترسی‌ها، از جمله مدیریت تیم، دامنه و اشتراک.",
    StoreMembership.Role.ADMINISTRATOR: "مدیریت عملیاتی کامل فروشگاه؛ بدون مدیریت تیم، دامنه، اشتراک و حذف فروشگاه.",
    StoreMembership.Role.CATALOG_MANAGER: "محصولات، دسته‌ها، برندها، موجودی و انبار.",
    StoreMembership.Role.ORDER_MANAGER: "سفارش‌ها، مرجوعی و بازپرداخت، مشتریان و ارسال.",
    StoreMembership.Role.CONTENT_EDITOR: "محتوا، رسانه، کالکشن‌ها و سازندهٔ فروشگاه.",
    StoreMembership.Role.ANALYST: "فقط مشاهدهٔ گزارش‌ها، سفارش‌ها و محصولات (بدون ویرایش).",
}

#: نقش‌هایی که از طریق این سرویس قابل‌واگذاری‌اند — OWNER عمداً حذف شده چون
#: این فروشگاه دقیقاً یک مالکِ فعال دارد (قید ``uniq_active_owner_per_store``)
#: و واگذاریِ آن باید از مسیرِ صریحِ ``transfer_ownership`` عبور کند، نه از
#: مسیرِ عمومیِ افزودن/تغییرِ نقش.
ASSIGNABLE_ROLES = tuple(
    (value, label) for value, label in StoreMembership.Role.choices
    if value != StoreMembership.Role.OWNER
)
_ASSIGNABLE_ROLE_VALUES = frozenset(value for value, _ in ASSIGNABLE_ROLES)


class MembershipError(Exception):
    """خطای قابل‌نمایش هنگام مدیریت اعضای تیم فروشگاه."""


class StaffInputError(MembershipError):
    """ورودیِ فرمِ افزودن عضو نامعتبر است؛ ``field_errors`` خطا را کنارِ فیلدِ مربوط نشان می‌دهد."""

    def __init__(self, field_errors: dict):
        self.field_errors = dict(field_errors)
        super().__init__("؛ ".join(self.field_errors.values()))


def _normalize_phone(phone: str) -> str:
    """مرجعِ واحدِ نرمال‌سازیِ موبایل (ارقامِ فارسی/عربی، ‎+98‎، ۰۰۹۸، بدونِ صفر) — همان که ورود/ثبت‌نام استفاده می‌کنند."""
    try:
        return normalize_iranian_phone(phone)
    except InvalidPhoneError as exc:
        raise StaffInputError({"phone": "; ".join(exc.messages)}) from exc


def _clean_name(raw: str) -> str:
    value = unicodedata.normalize("NFKC", str(raw or ""))
    value = _INVISIBLE_RE.sub("", value)
    value = " ".join(value.split())
    if len(value) > NAME_MAX_LENGTH:
        raise StaffInputError({"full_name": f"نام نباید بیشتر از {NAME_MAX_LENGTH} نویسه باشد."})
    return value


def _clean_email(raw: str) -> str:
    value = (raw or "").strip().lower()
    if not value:
        return ""
    try:
        validate_email(value)
    except ValidationError as exc:
        raise StaffInputError({"email": "ایمیل واردشده معتبر نیست؛ مثلاً name@example.com."}) from exc
    return value


def clean_member_input(*, phone: str, role: str, full_name: str = "", email: str = "") -> dict:
    """همهٔ خطاهای فرم را یک‌جا جمع می‌کند (تا کاربر هر بار فقط یک خطا نبیند) و مقادیرِ نرمال‌شده را برمی‌گرداند."""
    errors, cleaned = {}, {}
    for key, fn, raw in (("phone", _normalize_phone, phone), ("full_name", _clean_name, full_name), ("email", _clean_email, email)):
        try:
            cleaned[key] = fn(raw)
        except StaffInputError as exc:
            errors.update(exc.field_errors)
    if role not in _ASSIGNABLE_ROLE_VALUES:
        errors["role"] = "نقش انتخاب‌شده نامعتبر است." if role else "یک نقش انتخاب کنید."
    if errors:
        raise StaffInputError(errors)
    cleaned["role"] = role
    return cleaned


def _validate_assignable_role(role: str) -> None:
    if role not in _ASSIGNABLE_ROLE_VALUES:
        raise MembershipError("نقش انتخاب‌شده نامعتبر است.")


_STATUS_SORT_ORDER = {
    StoreMembership.MembershipStatus.ACTIVE: 0,
    StoreMembership.MembershipStatus.INVITED: 1,
    StoreMembership.MembershipStatus.REVOKED: 2,
}


def display_name(user) -> str:
    """نامِ نمایشیِ کاربر: نامِ ثبت‌شده روی حساب یا پروفایلِ مالک؛ وگرنه خالی (فهرست شماره را نشان می‌دهد)."""
    name = (user.get_full_name() or "").strip()
    if not name:
        profile = getattr(user, "owner_profile", None)
        name = (getattr(profile, "full_name", "") or "").strip()
    return name


def list_memberships(store, *, q: str = "", status: str = "", role: str = "") -> list[StoreMembership]:
    """اعضای این فروشگاه (و فقط این فروشگاه): فعال‌ها ابتدا، سپس دعوت‌شده‌ها، سپس لغوشده‌ها؛ درون هر گروه، جدیدترین‌ها بالاتر.

    ``q`` روی شماره/نام/ایمیل (بدونِ حساسیت به ارقامِ فارسی)، ``status``/``role`` روی مقدارِ دقیق فیلتر می‌کنند."""
    memberships = StoreMembership.objects.filter(store=store).select_related(
        "user", "user__owner_profile", "invited_by",
    )
    if status in StoreMembership.MembershipStatus.values:
        memberships = memberships.filter(status=status)
    if role in StoreMembership.Role.values:
        memberships = memberships.filter(role=role)
    rows = list(memberships)
    needle = unicodedata.normalize("NFKC", (q or "").strip()).translate(_FA_TO_ASCII).lower()
    if needle:
        def matches(m):
            haystack = " ".join((m.user.username, m.user.email or "", display_name(m.user))).translate(_FA_TO_ASCII).lower()
            return needle in haystack
        rows = [m for m in rows if matches(m)]
    return sorted(rows, key=lambda m: (_STATUS_SORT_ORDER.get(m.status, 9), -m.created_at.timestamp()))


_FA_TO_ASCII = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def summarize(store) -> dict:
    """شمارندهٔ اعضا بر حسبِ وضعیت (برایِ سرصفحهٔ صفحهٔ تیم)."""
    counts = {value: 0 for value in StoreMembership.MembershipStatus.values}
    for status in StoreMembership.objects.filter(store=store).values_list("status", flat=True):
        counts[status] = counts.get(status, 0) + 1
    return counts


STAFF_EVENT_LABELS = {
    "staff.added": "عضو اضافه شد",
    "staff.reactivated": "عضویت دوباره فعال شد",
    "staff.role_changed": "نقش تغییر کرد",
    "staff.revoked": "عضویت لغو شد",
    "staff.ownership_transferred": "مالکیت منتقل شد",
}


def recent_staff_events(store, limit: int = 8):
    """آخرین رخدادهای حسابرسیِ تیم (فقط همین فروشگاه): چه کسی، کی، چه تغییری."""
    from apps.core.models import AuditLogEntry

    events = list(
        AuditLogEntry.objects.filter(store=store, action_code__startswith="staff.")
        .select_related("actor").order_by("-created_at", "-pk")[:limit]
    )
    for event in events:
        event.label = STAFF_EVENT_LABELS.get(event.action_code, event.action_code)
        event.detail = _staff_event_detail(event)
        event.tone = _STAFF_EVENT_TONES.get(event.action_code, "neutral")
        event.succeeded = event.result == event.ResultStatus.SUCCESS
        event.result_label = event.get_result_display()
    return events


#: دسته‌بندیِ رنگیِ ردیفِ رخداد در «آخرین تغییرات تیم» (فقط ظاهر؛ منطق دسترسی را تغییر نمی‌دهد).
_STAFF_EVENT_TONES = {
    "staff.added": "good", "staff.reactivated": "good", "staff.role_changed": "info",
    "staff.revoked": "warn", "staff.ownership_transferred": "warn",
}


def _role_label(value) -> str:
    try:
        return StoreMembership.Role(value).label
    except ValueError:
        return str(value or "")


def _staff_event_detail(event) -> str:
    """«نقشِ قبلی ← نقشِ تازه» از خلاصه‌های ثبت‌شده در رخداد؛ اگر خلاصه قابل‌خواندن نبود، رشتهٔ خالی."""
    import json

    def _load(raw):
        try:
            data = json.loads(raw) if raw else {}
        except (TypeError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    before, after = _load(event.before_summary), _load(event.after_summary)
    old, new = before.get("role"), after.get("role")
    if old and new and old != new:
        return f"{_role_label(old)} ← {_role_label(new)}"
    if new:
        return _role_label(new)
    return ""


def active_owner_count(store) -> int:
    return StoreMembership.objects.filter(
        store=store, role=StoreMembership.Role.OWNER, status=StoreMembership.MembershipStatus.ACTIVE,
    ).count()


@dataclass(frozen=True)
class AddPreview:
    """نتیجهٔ «بررسیِ پیش از افزودن» — چیزی نوشته نمی‌شود."""

    phone: str
    role: str
    full_name: str
    email: str
    #: new_account | existing_account | already_active | revoked | invited
    state: str
    existing_name: str = ""

    @property
    def can_add(self) -> bool:
        return self.state != "already_active"


def preview_add(store, *, phone: str, role: str, full_name: str = "", email: str = "") -> AddPreview:
    """ورودی را اعتبارسنجی و وضعیتِ این شماره در همین فروشگاه را (بدونِ نوشتن) گزارش می‌کند."""
    cleaned = clean_member_input(phone=phone, role=role, full_name=full_name, email=email)
    user = User.objects.filter(username=cleaned["phone"]).select_related("owner_profile").first()
    state, existing_name = "new_account", ""
    if user is not None:
        state, existing_name = "existing_account", display_name(user)
        membership = StoreMembership.objects.filter(store=store, user=user).first()
        if membership is not None:
            if membership.status == StoreMembership.MembershipStatus.ACTIVE:
                state = "already_active"
            elif membership.status == StoreMembership.MembershipStatus.REVOKED:
                state = "revoked"
            else:
                state = "invited"
    return AddPreview(
        phone=cleaned["phone"], role=cleaned["role"], full_name=cleaned["full_name"], email=cleaned["email"],
        state=state, existing_name=existing_name,
    )


def _enforce_seat(store) -> None:
    """گیتِ صندلی. خطای پلن/اشتراک (``EntitlementError``/``UsageLimitExceeded``) عمداً *همان‌طور* بالا می‌رود (قراردادِ
    سرویس و آزمون‌هایِ اشتراک)؛ ویوها آن را به پیامِ فارسی تبدیل می‌کنند و هرگز ۵۰۰ نمی‌شود."""
    from apps.subscriptions.services.enforcement import enforce_can_add_staff

    enforce_can_add_staff(store)


def _apply_profile(user, *, full_name: str, email: str) -> None:
    """نام/ایمیلِ اختیاری فقط جاهایِ *خالیِ* حساب را پر می‌کند؛ مقدارِ موجود هرگز بازنویسی نمی‌شود و ایمیلِ مالِ
    حسابِ دیگر پذیرفته نمی‌شود."""
    fields = []
    if full_name and not display_name(user):
        user.first_name = full_name
        fields.append("first_name")
    if email and not (user.email or "").strip():
        if User.objects.filter(email__iexact=email).exclude(pk=user.pk).exists():
            raise StaffInputError({"email": "این ایمیل برای حسابِ دیگری ثبت شده است؛ ایمیلِ دیگری وارد کنید یا آن را خالی بگذارید."})
        user.email = email
        fields.append("email")
    if fields:
        user.save(update_fields=fields)


def _get_or_create_user(phone: str):
    user = User.objects.filter(username=phone).select_for_update().first()
    if user is not None:
        return user
    try:
        with transaction.atomic():
            user = User.objects.create_user(username=phone, is_staff=True)
            user.set_unusable_password()
            user.save(update_fields=["password"])
        return user
    except IntegrityError:  # ثبتِ هم‌زمانِ همین شماره (دو کلیک/دو تب): همان حسابِ برنده را بخوان
        return User.objects.select_for_update().get(username=phone)


@transaction.atomic
def add_staff_member(store, *, phone: str, role: str, invited_by, full_name: str = "", email: str = "") -> StoreMembership:
    """کاربری را (با ساختنِ حسابِ کاربری در صورت نبود) عضوِ فعالِ این فروشگاه می‌کند.

    ورود: شمارهٔ موبایل (ارقامِ فارسی و ‎+98‎ هم پذیرفته می‌شود) و نقشِ مجاز؛ نام و ایمیل اختیاری‌اند. اگر پیش‌تر
    عضویتی (با هر وضعیتی) برایِ همین (فروشگاه، کاربر) وجود داشته باشد — طبقِ قید ``uniq_membership_per_store_user``
    نمی‌توان ردیفِ دوم ساخت — همان ردیف با نقشِ تازه به ACTIVE برمی‌گردد. عضو با **همان هویتِ موبایل+OTP** وارد می‌شود
    (بدونِ OwnerProfile، بدونِ فروشگاهِ آزمایشی؛ نگاه کنید به ``owner_auth_service.resolve_owner_identity_by_phone``)."""
    cleaned = clean_member_input(phone=phone, role=role, full_name=full_name, email=email)
    phone, full_name, email = cleaned["phone"], cleaned["full_name"], cleaned["email"]

    # گیتِ صندلی (checkpoint 5A، ADR-69/§27): فقط وقتی این عملیات یک صندلیِ
    # تازه مصرف می‌کند (کاربرِ تازه، یا احیایِ عضویتِ لغوشده) گیت اعمال
    # می‌شود — تغییرِ نقشِ عضوِ از‌پیش‌شمرده‌شده صندلی اضافه نمی‌کند. پیش از
    # ساختِ حسابِ کاربری بررسی می‌شود تا حسابِ یتیم ساخته نشود.
    _existing_user = User.objects.filter(username=phone).first()
    _adds_seat = True
    if _existing_user is not None:
        _m = StoreMembership.objects.filter(store=store, user=_existing_user).first()
        if _m is not None and _m.status in (
            StoreMembership.MembershipStatus.ACTIVE, StoreMembership.MembershipStatus.INVITED,
        ):
            _adds_seat = False
    if _adds_seat:
        _enforce_seat(store)

    user = _get_or_create_user(phone)
    if not user.is_staff:
        user.is_staff = True
        user.save(update_fields=["is_staff"])
    _apply_profile(user, full_name=full_name, email=email)

    existing = StoreMembership.objects.select_for_update().filter(store=store, user=user).first()
    if existing is not None:
        if existing.status == StoreMembership.MembershipStatus.ACTIVE:
            raise StaffInputError({"phone": "این کاربر از قبل عضو فعال این فروشگاه است."})
        old_status, old_role = existing.status, existing.role
        existing.role = role
        existing.status = StoreMembership.MembershipStatus.ACTIVE
        existing.invited_by = invited_by
        existing.accepted_at = timezone.now()
        existing.revoked_at = None
        try:
            existing.full_clean()
        except ValidationError as exc:
            raise MembershipError("؛ ".join(sum(exc.message_dict.values(), []))) from exc
        existing.save()
        record_audit_event(
            store=store, actor=invited_by, action_code="staff.reactivated",
            object_type="StoreMembership", object_id=existing.pk, object_label=phone,
            before={"status": old_status, "role": old_role}, after={"status": "active", "role": role},
        )
        return existing

    membership = StoreMembership(
        store=store, user=user, role=role,
        status=StoreMembership.MembershipStatus.ACTIVE,
        invited_by=invited_by, accepted_at=timezone.now(),
    )
    try:
        membership.full_clean()
    except ValidationError as exc:
        raise MembershipError("؛ ".join(sum(exc.message_dict.values(), []))) from exc
    membership.save()
    record_audit_event(
        store=store, actor=invited_by, action_code="staff.added",
        object_type="StoreMembership", object_id=membership.pk, object_label=phone,
        after={"role": role},
    )
    return membership


@transaction.atomic
def change_role(membership: StoreMembership, *, new_role: str, actor=None) -> StoreMembership:
    if membership.role == StoreMembership.Role.OWNER:
        raise MembershipError("نقشِ مالک را نمی‌توان مستقیماً تغییر داد؛ از «انتقال مالکیت» استفاده کنید.")
    if actor is not None and membership.user_id == getattr(actor, "pk", None):
        raise MembershipError("نقش یا دسترسیِ خودتان را نمی‌توانید تغییر دهید.")
    _validate_assignable_role(new_role)
    old_role = membership.role
    membership.role = new_role
    try:
        membership.full_clean()
    except ValidationError as exc:
        raise MembershipError("؛ ".join(sum(exc.message_dict.values(), []))) from exc
    membership.save(update_fields=["role", "updated_at"])
    record_audit_event(
        store=membership.store, actor=actor, action_code="staff.role_changed",
        object_type="StoreMembership", object_id=membership.pk, object_label=membership.user.username,
        before={"role": old_role}, after={"role": new_role},
    )
    return membership


@transaction.atomic
def revoke_membership(membership: StoreMembership, *, actor=None) -> StoreMembership:
    if membership.role == StoreMembership.Role.OWNER:
        raise MembershipError("نمی‌توان مالکِ فروشگاه را حذف کرد؛ ابتدا مالکیت را به عضوِ دیگری منتقل کنید.")
    if actor is not None and membership.user_id == getattr(actor, "pk", None):
        raise MembershipError("نمی‌توانید دسترسیِ خودتان را لغو کنید.")
    if membership.status == StoreMembership.MembershipStatus.REVOKED:
        raise MembershipError("این عضویت پیش‌تر لغو شده است.")
    membership.status = StoreMembership.MembershipStatus.REVOKED
    membership.revoked_at = timezone.now()
    try:
        membership.full_clean()
    except ValidationError as exc:
        raise MembershipError("؛ ".join(sum(exc.message_dict.values(), []))) from exc
    membership.save(update_fields=["status", "revoked_at", "updated_at"])
    record_audit_event(
        store=membership.store, actor=actor, action_code="staff.revoked",
        object_type="StoreMembership", object_id=membership.pk, object_label=membership.user.username,
    )
    return membership


@transaction.atomic
def reactivate_membership(membership: StoreMembership, *, actor=None) -> StoreMembership:
    if membership.status == StoreMembership.MembershipStatus.ACTIVE:
        raise MembershipError("این عضویت هم‌اکنون فعال است.")
    # احیایِ عضویتِ لغوشده یک صندلیِ تازه مصرف می‌کند (ADR-69/§27).
    if membership.status != StoreMembership.MembershipStatus.INVITED:
        _enforce_seat(membership.store)
    membership.status = StoreMembership.MembershipStatus.ACTIVE
    membership.accepted_at = timezone.now()
    membership.revoked_at = None
    try:
        membership.full_clean()
    except ValidationError as exc:
        raise MembershipError("؛ ".join(sum(exc.message_dict.values(), []))) from exc
    membership.save(update_fields=["status", "accepted_at", "revoked_at", "updated_at"])
    record_audit_event(
        store=membership.store, actor=actor, action_code="staff.reactivated",
        object_type="StoreMembership", object_id=membership.pk, object_label=membership.user.username,
    )
    return membership


@transaction.atomic
def transfer_ownership(store, *, current_owner: StoreMembership, new_owner: StoreMembership, actor=None) -> None:
    """مالکیتِ فروشگاه را از ``current_owner`` به ``new_owner`` منتقل می‌کند.

    هر دو ردیف قفل و به‌ترتیب به‌روزرسانی می‌شوند (ابتدا خلعِ مالکِ فعلی،
    سپس ارتقای مالکِ جدید) تا قیدِ ``uniq_active_owner_per_store`` (دقیقاً
    یک مالکِ فعال) در هیچ لحظه‌ای نقض نشود.
    """
    current = StoreMembership.objects.select_for_update().get(pk=current_owner.pk)
    new = StoreMembership.objects.select_for_update().get(pk=new_owner.pk)

    if current.store_id != store.id or new.store_id != store.id:
        raise MembershipError("این عضویت متعلق به این فروشگاه نیست.")
    if current.role != StoreMembership.Role.OWNER or current.status != StoreMembership.MembershipStatus.ACTIVE:
        raise MembershipError("عضویتِ فعلی، مالکِ فعالِ این فروشگاه نیست.")
    if new.status != StoreMembership.MembershipStatus.ACTIVE:
        raise MembershipError("عضوِ مقصد باید عضویتِ فعال داشته باشد.")
    if new.pk == current.pk:
        raise MembershipError("مالک هم‌اکنون همین عضو است.")

    current.role = StoreMembership.Role.ADMINISTRATOR
    current.save(update_fields=["role", "updated_at"])
    new.role = StoreMembership.Role.OWNER
    new.save(update_fields=["role", "updated_at"])
    record_audit_event(
        store=store, actor=actor, action_code="staff.ownership_transferred",
        object_type="StoreMembership", object_id=new.pk, object_label=new.user.username,
        before={"previous_owner": current.user.username}, after={"new_owner": new.user.username},
    )
