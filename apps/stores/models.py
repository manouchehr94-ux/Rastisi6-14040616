import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from .hostnames import normalize_admin_subdomain, normalize_hostname


class StoresTimestampedModel(models.Model):
    """Local created_at/updated_at base for the ``stores`` app.

    ``apps.core.models.TimeStampedModel`` is not reused here on purpose.
    Several existing apps (catalog, orders, customers, ...) import from
    ``apps.core``, and a later foundation PR (see
    ``docs/architecture/SAAS_MIGRATION_PLAN.md``, PR 4) is expected to add a
    ``store`` foreign key to ``apps.core.ShopSettings`` itself — i.e. `core`
    is expected to depend on `stores` in the future. If `stores` imported
    from `core` now, that would set up a circular dependency between the two
    apps as soon as PR 4 lands. Defining timestamps locally here keeps
    `stores` dependency-free of `core` and avoids that future cycle.
    """

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Store(StoresTimestampedModel):
    """A Store is the authoritative SaaS tenant and data-ownership boundary.

    Every future commerce record must be either platform-global by explicit
    design, or owned directly or indirectly by exactly one Store. ``Store``
    is a new, independent domain entity — it is not ``apps.catalog.Vendor``
    and does not replace it. See ``docs/architecture/SAAS_DOMAIN_DECISIONS.md``
    (ADR-1) for why the two are kept separate.

    This model intentionally has no owner field — Store ownership is
    represented exclusively through an active ``StoreMembership`` with
    ``role=OWNER`` (ADR-2). It also has no billing/subscription/theme/payment
    fields, and no *public storefront* domain fields (``StoreDomain`` is a
    separate model on purpose, with its own merchant-driven verification
    lifecycle).

    ``admin_subdomain`` (Phase 1B / ADR-16, see
    ``docs/architecture/SAAS_DOMAIN_DECISIONS.md``) is the one domain-shaped
    field that *does* live directly on ``Store``, precisely because it is
    the opposite of ``StoreDomain`` in every way that matters: platform-
    assigned (not merchant-supplied), never subject to DNS/HTTP
    verification, and deliberately independent from whatever public
    storefront domain(s) the Store has today — changing or losing every
    ``StoreDomain`` row must never change the merchant admin host.
    """

    class Status(models.TextChoices):
        PROVISIONING = "provisioning", "در حال آماده‌سازی"
        ACTIVE = "active", "فعال"
        SUSPENDED = "suspended", "معلق"
        CLOSED = "closed", "بسته‌شده"

    public_id = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        help_text="شناسه‌ی عمومی پایدار برای ارجاع خارجی (API، صورتحساب، پشتیبانی).",
    )
    name = models.CharField("نام فروشگاه", max_length=200)
    slug = models.SlugField(
        "اسلاگ",
        max_length=200,
        unique=True,
        allow_unicode=True,
        help_text="یکتای سراسری در کل پلتفرم — نه فقط در یک فروشگاه.",
    )
    admin_subdomain = models.CharField(
        "زیردامنه‌ی مدیریت",
        max_length=63,
        unique=True,
        help_text=(
            "بخش پایدار زیردامنه‌ی پنل مدیریت، مستقل از دامنه‌ی عمومی فروشگاه "
            "(مثل «digilool» در https://digilool.rastisi.ir/admin-portal/). "
            "برخلاف slug، همیشه ASCII و DNS-safe است — چون این مقدار مستقیماً "
            "بخشی از یک Host واقعی می‌شود، نه فقط یک URL path."
        ),
    )
    status = models.CharField(
        "وضعیت",
        max_length=20,
        choices=Status.choices,
        default=Status.PROVISIONING,
        db_index=True,
    )
    platform_code = models.CharField(
        "کد پایدار پلتفرم",
        max_length=9,
        unique=True,
        editable=False,
        help_text=(
            "شناسه‌ی ۹ نویسه‌ای پایدار و قابل‌تایپ (ADR-94) — پایه‌ی نام "
            "میزبان آزمایشی «{code}.rastisi.ir». برخلاف public_id (UUID، "
            "برای ارجاع فنی) یا admin_subdomain (میزبان پنل مدیریت)، هرگز "
            "تغییر نمی‌کند و هرگز به فروشگاه دیگری واگذار نمی‌شود، حتی پس از "
            "تغییر زیردامنه‌ی عمومی."
        ),
    )
    onboarding_completed_at = models.DateTimeField(
        "زمان تکمیل راه‌اندازی",
        null=True, blank=True,
        help_text=(
            "تا این مقدار خالی است، فروشگاه خصوصی است (Section 6) — فقط "
            "برایِ مالک/کارکنانِ عضو با پیش‌نمایشِ احرازهویت‌شده قابل‌دیدن، نه "
            "برایِ بازدیدکنندهٔ ناشناس، حتی اگر Store.status=active باشد. "
            "``apps.stores.services.publication_service`` تنها جایِ مجاز "
            "برایِ خواندنِ این مقدار در تصمیمِ «آیا این فروشگاه اکنون "
            "عمومی/در دسترس است؟» است."
        ),
    )

    onboarding_required_at = models.DateTimeField(
        "زمان الزامِ راه‌اندازیِ اولیه",
        null=True, blank=True,
        help_text=(
            "نشانهٔ پایدارِ «این فروشگاه از مسیرِ مدرنِ ثبت‌نام/ساخت در پورتال "
            "ساخته شده و باید پیش از عمومی‌شدن، آنبوردینگ را با «انتشار» تمام "
            "کند». فقط ``provisioning_service.provision_trial_store`` آن را "
            "هنگامِ ساخت مقداردهی می‌کند؛ فروشگاه‌هایِ قدیمی/ساخته‌شده به‌صورتِ "
            "دستی NULL می‌مانند و رفتارِ fail-open (ADR-65) آن‌ها دست‌نخورده است. "
            "تا وقتی این مقدار هست و ``onboarding_completed_at`` خالی است، "
            "``publication_service`` فروشگاه را غیرعمومی می‌داند — صرف‌نظر از "
            "وجود یا نبودِ اشتراک."
        ),
    )

    class OnboardingStage(models.TextChoices):
        IDENTITY = "identity", "معرفیِ فروشگاه"
        INDUSTRY = "industry", "انتخابِ صنف"
        TEMPLATE = "template", "قالبِ فروشگاه"
        BRANDING = "branding", "هویتِ بصری"
        REVIEW = "review", "بازبینی و انتشار"
        DONE = "done", "تکمیل‌شده"

    onboarding_stage = models.CharField(
        "مرحله‌ی جاریِ راه‌اندازی",
        max_length=20, choices=OnboardingStage.choices, default=OnboardingStage.IDENTITY,
        help_text=(
            "پیشرفتِ ویزاردِ آنبوردینگ (Section 5) — صرفاً برای هدایتِ مالک به "
            "همان‌جایی که رها کرده (save-progress)، نه یک قفلِ سخت‌گیرانه: "
            "مالک همیشه می‌تواند آزادانه به مراحلِ قبلی برگردد و آن‌ها را "
            "دوباره ویرایش کند. تنها گذرِ صریح از مرحله‌ی REVIEW است که "
            "``onboarding_completed_at`` را مقداردهی می‌کند."
        ),
    )

    deletion_requested_at = models.DateTimeField(
        "زمانِ درخواستِ حذف",
        null=True, blank=True,
        help_text=(
            "حذف همیشه نرم است (Section 14) — تا این‌جا مقداردهی شده، "
            "``status=CLOSED`` و فروشگاه غیرِ عمومی است، اما هیچ داده‌ای "
            "پاک نمی‌شود؛ فقط پس از رسیدنِ به "
            "``deletion_scheduled_purge_at``، دستورِ ``purge_deleted_stores`` "
            "می‌تواند واقعاً حذف کند."
        ),
    )
    deletion_requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="درخواست‌دهنده‌ی حذف", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="requested_store_deletions",
    )
    deletion_scheduled_purge_at = models.DateTimeField(
        "زمانِ برنامه‌ریزی‌شده‌ی پاک‌سازیِ نهایی",
        null=True, blank=True,
        help_text="از زمانِ درخواست به‌اضافه‌ی PlatformConfiguration.deletion_retention_days محاسبه می‌شود.",
    )
    pre_deletion_status = models.CharField(
        "وضعیتِ پیش از درخواستِ حذف",
        max_length=20, choices=Status.choices, blank=True, default="",
        help_text="برایِ بازگردانیِ دقیق در صورتِ لغوِ درخواستِ حذف (cancel_deletion).",
    )
    suspended_at = models.DateTimeField(
        "زمانِ تعلیق",
        null=True, blank=True,
        help_text=(
            "مقداردهی‌شده یعنی این Store توسطِ مدیرِ پلتفرم تعلیق شده — نگاه "
            "کنید به apps.stores.services.store_status_service. جدا از "
            "``status=SUSPENDED`` نگه‌داشته می‌شود تا زمان/دلیل/فاعلِ تعلیق "
            "حتی پس از فعال‌سازیِ دوباره هم در تاریخچه قابل‌بازیابی بماند."
        ),
    )
    suspended_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="تعلیق‌کننده", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="suspended_stores",
    )
    suspension_reason = models.CharField("دلیلِ تعلیق", max_length=300, blank=True, default="")

    class Meta:
        verbose_name = "فروشگاه"
        verbose_name_plural = "فروشگاه‌ها"
        ordering = ["name"]

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if self.admin_subdomain:
            try:
                self.admin_subdomain = normalize_admin_subdomain(self.admin_subdomain)
            except ValidationError as exc:
                raise ValidationError({"admin_subdomain": exc.messages}) from exc

    def _fallback_admin_subdomain(self):
        """A deterministic, always-valid ``admin_subdomain`` derived from
        this Store, used only when the caller didn't supply one explicitly.

        Tries the Store's own ``slug`` first (already globally unique, so
        this can only collide with itself); ``slug`` is ``allow_unicode=True``
        though, so a Persian/non-ASCII slug can't pass
        ``normalize_admin_subdomain`` (which must stay a plain DNS label) —
        in that case, falls back to a ``public_id``-derived label instead of
        guessing a transliteration. This exists so ordinary
        ``Store.objects.create(name=..., slug=...)`` call sites (throughout
        the existing test suite and any future provisioning code that
        doesn't care about the exact admin host yet) keep working without
        every caller needing to invent one; a merchant-onboarding flow can
        always set an explicit, merchant-chosen value later.
        """
        try:
            return normalize_admin_subdomain(self.slug)
        except ValidationError:
            return f"store-{self.public_id.hex[:12]}"

    def _fallback_platform_code(self):
        """A deterministic ``platform_code`` derived from this Store's own
        ``public_id``, used only when the caller didn't supply one
        explicitly — mirrors ``_fallback_admin_subdomain``'s precedent
        (ADR-94). No DB query is needed (unlike the real, careful path):
        ``public_id`` is already DB-unique, and this is a lossy, order-
        preserving-free mapping of its bits into the platform-code alphabet,
        so a collision is exactly as astronomically unlikely as
        ``_fallback_admin_subdomain``'s own ``public_id.hex[:12]`` fallback
        already is — and just as fail-closed (``IntegrityError``) in the
        practically-impossible event of one. Real trial provisioning
        (``apps.stores.services.platform_code_service.
        generate_unique_platform_code``) always generates and existence-
        checks a fresh code explicitly instead of relying on this.
        """
        alphabet = settings.RASTISI_PLATFORM_CODE_ALPHABET
        length = settings.RASTISI_PLATFORM_CODE_LENGTH
        base = len(alphabet)
        remaining = self.public_id.int
        chars = []
        for _ in range(length):
            remaining, digit = divmod(remaining, base)
            chars.append(alphabet[digit])
        return "".join(chars)

    def save(self, *args, **kwargs):
        if self.admin_subdomain:
            self.admin_subdomain = normalize_admin_subdomain(self.admin_subdomain)
        else:
            self.admin_subdomain = self._fallback_admin_subdomain()
        if not self.platform_code:
            self.platform_code = self._fallback_platform_code()
        super().save(*args, **kwargs)


class StoreDomainMutationError(Exception):
    """Raised when a bulk/queryset write path would bypass StoreDomain's
    authoritative hostname normalization.

    ``StoreDomain.hostname`` must always be the normalized, canonical form
    produced by ``normalize_hostname``. ``QuerySet.update()`` issues a raw SQL
    UPDATE and ``QuerySet.bulk_create()`` issues a raw SQL INSERT — both
    bypass ``Model.save()``/``Model.clean()`` entirely, so without this guard
    either path could silently persist a raw, un-normalized, or
    differently-cased hostname and defeat the uniqueness guarantee. Use
    ``instance.save()`` (directly, or via ``StoreDomain.objects.create()``,
    which calls it) instead.
    """


def _verification_lifecycle_errors(instance):
    """Field-error dict for any StoreDomain verification-lifecycle incoherence.

    Mirrors the DB-level ``CheckConstraint``s declared on
    ``StoreDomain.Meta.constraints`` so ``clean()``/bulk validation raise an
    early, well-labeled ``ValidationError`` instead of relying only on a raw
    ``IntegrityError`` from the database. Rules enforced (see
    ``docs/architecture/SAAS_DOMAIN_DECISIONS.md`` ADR-5):

    * ``VERIFIED`` requires ``verified_at``.
    * Any non-``VERIFIED`` status must not retain ``verified_at``.
    * ``PENDING`` requires ``verification_requested_at``.
    * ``PENDING`` requires a non-empty ``verification_token``.
    """
    errors = {}
    status = instance.verification_status
    verified = instance.VerificationStatus.VERIFIED
    pending = instance.VerificationStatus.PENDING

    if status == verified and instance.verified_at is None:
        errors.setdefault("verified_at", []).append(
            "دامنه‌ی تأییدشده باید زمان تأیید داشته باشد."
        )
    if status != verified and instance.verified_at is not None:
        errors.setdefault("verified_at", []).append(
            "فقط دامنه‌ی تأییدشده می‌تواند زمان تأیید داشته باشد."
        )
    if status == pending and instance.verification_requested_at is None:
        errors.setdefault("verification_requested_at", []).append(
            "دامنه‌ی در انتظار تأیید باید زمان درخواست تأیید داشته باشد."
        )
    if status == pending and not instance.verification_token:
        errors.setdefault("verification_token", []).append(
            "دامنه‌ی در انتظار تأیید باید توکن تأیید داشته باشد."
        )
    if instance.retired_at is not None and instance.is_primary:
        errors.setdefault("retired_at", []).append(
            "دامنه‌ی بازنشسته نمی‌تواند هم‌زمان دامنه‌ی اصلی باشد."
        )
    return errors


def _normalize_and_validate_domain(instance):
    """Normalize ``hostname`` and validate verification-lifecycle coherence.

    Shared by ``StoreDomain.clean()`` and ``StoreDomainQuerySet.bulk_create()``
    so there is exactly one place that decides what counts as a valid
    StoreDomain, instead of two independently-maintained copies of the same
    rules that could drift apart.
    """
    errors = {}

    if instance.hostname:
        try:
            instance.hostname = normalize_hostname(instance.hostname)
        except ValidationError as exc:
            errors["hostname"] = exc.messages

    errors.update(_verification_lifecycle_errors(instance))

    if errors:
        raise ValidationError(errors)


class StoreDomainQuerySet(models.QuerySet):
    """Enforces StoreDomain's hostname-normalization guarantee on bulk paths.

    This is deliberately narrow: it does not turn ``StoreDomain.objects``
    into a tenant-scoping default manager (it never filters rows by Store),
    it only protects the ``hostname`` write path, which is the one field
    whose canonical form cannot be expressed as a plain database constraint.
    """

    def update(self, **kwargs):
        if "hostname" in kwargs:
            raise StoreDomainMutationError(
                "hostname را نمی‌توان مستقیماً با update() تغییر داد؛ "
                "چون این مسیر نرمال‌سازی instance.save() را دور می‌زند. "
                "از instance.save() استفاده کنید."
            )
        return super().update(**kwargs)

    def bulk_create(self, objs, *args, **kwargs):
        objs = list(objs)
        for obj in objs:
            _normalize_and_validate_domain(obj)
        return super().bulk_create(objs, *args, **kwargs)


StoreDomainManager = models.Manager.from_queryset(StoreDomainQuerySet)


class StoreDomain(StoresTimestampedModel):
    """A hostname bound to a Store.

    ``hostname`` always holds the normalized, canonical form produced by
    ``apps.stores.hostnames.normalize_hostname`` — never a raw URL. This is
    enforced on every write path this app exposes:

    * ``instance.save()`` and ``full_clean()`` normalize/validate directly.
    * ``StoreDomain.objects.bulk_create()`` normalizes and validates every
      instance before insertion (``StoreDomainQuerySet.bulk_create``).
    * ``StoreDomain.objects.filter(...).update(hostname=...)`` is rejected
      outright with ``StoreDomainMutationError``, because a raw SQL UPDATE
      cannot re-run the Python-level IDNA normalization.

    See ``docs/architecture/SAAS_DOMAIN_DECISIONS.md`` (ADR-4, ADR-5) for the
    normalization and verification-lifecycle decisions. This model does not
    implement DNS/HTTP verification networking or request-time host
    resolution — those are later, separate PRs.
    """

    objects = StoreDomainManager()

    class VerificationStatus(models.TextChoices):
        UNVERIFIED = "unverified", "تأییدنشده"
        PENDING = "pending", "در انتظار تأیید"
        VERIFIED = "verified", "تأییدشده"
        FAILED = "failed", "ناموفق"

    class RoutingStatus(models.TextChoices):
        UNCHECKED = "unchecked", "بررسی‌نشده"
        CONNECTED = "connected", "متصل"
        NOT_CONNECTED = "not_connected", "متصل نیست"

    class TlsStatus(models.TextChoices):
        UNCHECKED = "unchecked", "بررسی‌نشده"
        READY = "ready", "آماده"
        NOT_READY = "not_ready", "آماده نیست"

    class DomainType(models.TextChoices):
        GENERATED_TRIAL = "generated_trial", "زیردامنه‌ی آزمایشی خودکار"
        PLATFORM_SUBDOMAIN = "platform_subdomain", "زیردامنه‌ی انتخابی روی rastisi.ir"
        CUSTOM_DOMAIN = "custom_domain", "دامنه‌ی اختصاصی"

    store = models.ForeignKey(
        Store,
        verbose_name="فروشگاه",
        on_delete=models.CASCADE,
        related_name="domains",
    )
    hostname = models.CharField(
        "نام میزبان",
        max_length=253,
        unique=True,
        help_text="نام میزبان نرمال‌شده (بدون پروتکل/مسیر/پورت).",
    )
    is_primary = models.BooleanField("دامنه‌ی اصلی", default=False)
    domain_type = models.CharField(
        "نوع دامنه",
        max_length=20,
        choices=DomainType.choices,
        default=DomainType.CUSTOM_DOMAIN,
        db_index=True,
        help_text=(
            "توصیفی است، نه تعیین‌کننده‌ی مسیریابی (ADR-95) — واجد شرایط "
            "بودن برای مسیریابی همچنان فقط از verification_status/Store."
            "status می‌آید. زیردامنه‌های آزمایشی/انتخابی روی rastisi.ir از "
            "ابتدا verified ساخته می‌شوند چون Rastisi خودش مالک DNS آن "
            "زیردامنه‌هاست؛ فقط custom_domain مسیر تأیید واقعی را طی می‌کند."
        ),
    )
    retired_at = models.DateTimeField(
        "زمان بازنشستگی",
        null=True, blank=True,
        help_text=(
            "وقتی مقداردهی شده، این نام میزبان دیگر هرگز چیزی نمایش نمی‌دهد "
            "— نه محتوای فروشگاه، نه تغییرمسیر (ADR-101؛ جایگزینِ رفتارِ "
            "تغییرمسیرِ همیشگیِ ADR-96 که کنار گذاشته شد). درخواست به این "
            "نام میزبان یک پاسخِ امنِ «غیرفعال/یافت‌نشد» می‌گیرد "
            "(domain_is_eligible_for_routing این ردیف را واجد شرایط "
            "نمی‌داند). ردیف هرگز حذف نمی‌شود و hostname برای همیشه یکتا "
            "می‌ماند — پس این نام میزبان هرگز به فروشگاه دیگری واگذار "
            "نمی‌شود، فقط دیگر به هیچ‌جا نمی‌رود."
        ),
    )

    verification_status = models.CharField(
        "وضعیت تأیید",
        max_length=20,
        choices=VerificationStatus.choices,
        default=VerificationStatus.UNVERIFIED,
        db_index=True,
    )
    verification_token = models.CharField(
        "توکن تأیید", max_length=64, blank=True, default=""
    )
    verification_requested_at = models.DateTimeField(
        "زمان درخواست تأیید", null=True, blank=True
    )
    verified_at = models.DateTimeField("زمان تأیید", null=True, blank=True)

    routing_status = models.CharField(
        "وضعیت اتصال DNS",
        max_length=20,
        choices=RoutingStatus.choices,
        default=RoutingStatus.UNCHECKED,
        db_index=True,
        help_text="نتیجه آخرین بررسی اینکه A/CNAME دامنه واقعاً به زیرساخت RastiSi اشاره می‌کند.",
    )
    routing_checked_at = models.DateTimeField(
        "زمان آخرین بررسی اتصال DNS", null=True, blank=True
    )
    tls_status = models.CharField(
        "وضعیت TLS",
        max_length=20,
        choices=TlsStatus.choices,
        default=TlsStatus.UNCHECKED,
        db_index=True,
        help_text="نتیجه آخرین handshake واقعی HTTPS برای همین hostname.",
    )
    tls_checked_at = models.DateTimeField(
        "زمان آخرین بررسی TLS", null=True, blank=True
    )
    tls_certificate_expires_at = models.DateTimeField(
        "زمان انقضای گواهی TLS", null=True, blank=True
    )

    class Meta:
        verbose_name = "دامنه‌ی فروشگاه"
        verbose_name_plural = "دامنه‌های فروشگاه"
        ordering = ["store", "-is_primary", "hostname"]
        constraints = [
            models.UniqueConstraint(
                fields=["store"],
                condition=models.Q(is_primary=True),
                name="uniq_primary_domain_per_store",
            ),
            models.UniqueConstraint(
                fields=["verification_token"],
                condition=~models.Q(verification_token=""),
                name="uniq_verification_token_when_set",
            ),
            models.CheckConstraint(
                check=~models.Q(verification_status="verified")
                | models.Q(verified_at__isnull=False),
                name="verified_status_requires_verified_at",
            ),
            models.CheckConstraint(
                check=models.Q(verification_status="verified")
                | models.Q(verified_at__isnull=True),
                name="only_verified_domains_have_verified_at",
            ),
            models.CheckConstraint(
                check=~models.Q(verification_status="pending")
                | models.Q(verification_requested_at__isnull=False),
                name="pending_status_requires_verification_requested_at",
            ),
            models.CheckConstraint(
                check=~models.Q(verification_status="pending")
                | ~models.Q(verification_token=""),
                name="pending_status_requires_verification_token",
            ),
            models.CheckConstraint(
                check=models.Q(retired_at__isnull=True) | models.Q(is_primary=False),
                name="retired_domain_is_never_primary",
            ),
        ]
        indexes = [
            models.Index(fields=["store", "is_primary"], name="idx_domain_store_primary"),
        ]

    def __str__(self):
        marker = " (اصلی)" if self.is_primary else ""
        return f"{self.hostname}{marker}"

    def clean(self):
        super().clean()
        _normalize_and_validate_domain(self)

    def save(self, *args, **kwargs):
        if self.hostname:
            self.hostname = normalize_hostname(self.hostname)
        super().save(*args, **kwargs)


class StoreMembership(StoresTimestampedModel):
    """The authoritative link between a User and a Store, carrying a role.

    Store ownership is represented exclusively through an active
    ``StoreMembership`` row with ``role=OWNER`` — ``Store`` has no separate
    ``owner`` field (ADR-2). This model establishes the data shape and its
    core invariants only; invitation delivery, tokenized acceptance, owner
    transfer, authorization decorators, and dashboard integration are later,
    separate PRs.

    ``user`` uses ``on_delete=PROTECT``, not ``CASCADE``: since ownership
    lives exclusively in this table, silently deleting a User's membership
    rows as a side effect of deleting the User could delete a Store's only
    active Owner membership without anyone deciding that should happen,
    leaving the Store orphaned. Formal account deletion for a user who holds
    one or more memberships therefore requires a future, explicit
    membership-revocation/ownership-transfer service to run first — this PR
    does not implement that service, so such a deletion currently raises
    ``ProtectedError`` and must be handled by the caller.
    """

    class Role(models.TextChoices):
        OWNER = "owner", "مالک"
        ADMINISTRATOR = "administrator", "مدیر"
        CATALOG_MANAGER = "catalog_manager", "مدیر کاتالوگ"
        ORDER_MANAGER = "order_manager", "مدیر سفارش‌ها"
        CONTENT_EDITOR = "content_editor", "ویرایشگر محتوا"
        ANALYST = "analyst", "تحلیلگر"

    class MembershipStatus(models.TextChoices):
        INVITED = "invited", "دعوت‌شده"
        ACTIVE = "active", "فعال"
        REVOKED = "revoked", "لغوشده"

    store = models.ForeignKey(
        Store,
        verbose_name="فروشگاه",
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="کاربر",
        on_delete=models.PROTECT,
        related_name="store_memberships",
    )
    role = models.CharField("نقش", max_length=20, choices=Role.choices)
    status = models.CharField(
        "وضعیت عضویت",
        max_length=10,
        choices=MembershipStatus.choices,
        default=MembershipStatus.INVITED,
        db_index=True,
    )
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="دعوت‌کننده",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="store_invitations_sent",
    )
    invited_at = models.DateTimeField("زمان دعوت", auto_now_add=True)
    accepted_at = models.DateTimeField("زمان پذیرش", null=True, blank=True)
    revoked_at = models.DateTimeField("زمان لغو", null=True, blank=True)

    class Meta:
        verbose_name = "عضویت در فروشگاه"
        verbose_name_plural = "عضویت‌های فروشگاه"
        ordering = ["store", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["store", "user"], name="uniq_membership_per_store_user"
            ),
            models.UniqueConstraint(
                fields=["store"],
                condition=models.Q(role="owner", status="active"),
                name="uniq_active_owner_per_store",
            ),
            models.CheckConstraint(
                check=~models.Q(status="active") | models.Q(accepted_at__isnull=False),
                name="active_membership_requires_accepted_at",
            ),
            models.CheckConstraint(
                check=~models.Q(status="revoked") | models.Q(revoked_at__isnull=False),
                name="revoked_membership_requires_revoked_at",
            ),
        ]

    def __str__(self):
        return f"{self.user} @ {self.store} ({self.get_role_display()})"

    def clean(self):
        super().clean()
        errors = {}

        if self.status == self.MembershipStatus.ACTIVE and self.accepted_at is None:
            errors["accepted_at"] = "عضویت فعال باید زمان پذیرش داشته باشد."
        if self.status == self.MembershipStatus.REVOKED and self.revoked_at is None:
            errors["revoked_at"] = "عضویت لغوشده باید زمان لغو داشته باشد."

        if errors:
            raise ValidationError(errors)


class StoreOwnershipTransfer(StoresTimestampedModel):
    """انتقالِ مالکیتِ فروشگاه (Section 15) — دوطرفه و هر دو طرف OTP-گیت:
    مالکِ فعلی با تأییدِ گام‌دومِ خودش (action=``store_ownership_transfer``)
    درخواست را می‌سازد، و طرفِ مقابل با OTPِ خودش (شماره‌ی مقصد، نه شماره‌ی
    مالکِ فعلی) آن را می‌پذیرد — تا زمانِ پذیرشِ واقعی هیچ عضویتی تغییر
    نمی‌کند."""

    class Status(models.TextChoices):
        PENDING = "pending", "در انتظارِ پذیرش"
        COMPLETED = "completed", "انجام‌شده"
        EXPIRED = "expired", "منقضی‌شده"
        CANCELLED = "cancelled", "لغوشده"

    store = models.ForeignKey(
        Store, verbose_name="فروشگاه", on_delete=models.CASCADE, related_name="ownership_transfers",
    )
    initiated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="آغازکننده", on_delete=models.PROTECT,
        related_name="ownership_transfers_initiated",
    )
    target_phone = models.CharField("موبایلِ مالکِ جدید", max_length=15)
    token = models.CharField("توکنِ پذیرش", max_length=32, unique=True, editable=False)
    status = models.CharField("وضعیت", max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    expires_at = models.DateTimeField("زمانِ انقضا")
    completed_at = models.DateTimeField("زمانِ تکمیل", null=True, blank=True)
    cancelled_at = models.DateTimeField("زمانِ لغو", null=True, blank=True)

    class Meta:
        verbose_name = "انتقالِ مالکیتِ فروشگاه"
        verbose_name_plural = "انتقال‌هایِ مالکیتِ فروشگاه"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["store"], condition=models.Q(status="pending"),
                name="uniq_pending_ownership_transfer_per_store",
            ),
        ]

    def __str__(self):
        return f"{self.store.slug} → {self.target_phone} ({self.get_status_display()})"

    def save(self, *args, **kwargs):
        if not self.token:
            import secrets

            self.token = secrets.token_hex(16)
        super().save(*args, **kwargs)

    @property
    def is_expired(self) -> bool:
        from django.utils import timezone

        return timezone.now() >= self.expires_at


class StoreIntegrationConnection(StoresTimestampedModel):
    """اتصالِ یک Store به یک یکپارچه‌سازیِ بیرونیِ ساده (eNamad، Torob،
    Google Analytics، Google Tag Manager، پیکسلِ تبلیغاتی) — نگاه کنید به
    ``apps.stores.integrations.registry`` برایِ فهرستِ کاملِ Providerها.

    درگاه‌های پرداخت/اقساط (ZarinPal، SnappPay، Zibal، ...) اینجا نیستند —
    آن‌ها یک چرخه‌ی تراکنشیِ کامل دارند و از الگویِ اثبات‌شده‌ی
    ``apps.orders.models.PaymentGatewayConfig``/``apps.orders.gateways``
    استفاده می‌کنند؛ این مدل فقط برایِ یکپارچه‌سازی‌هایی است که صرفاً یک
    شناسه/کد نیاز دارند، نه یک تراکنشِ مالی.

    اعتبارنامه‌ها دقیقاً همان الگویِ
    ``PaymentGatewayConfig.encrypted_credentials`` را دارند (یک JSON
    رمزنگاری‌شده با ``apps.orders.encryption``، بازاستفاده‌شده نه تکرار)."""

    store = models.ForeignKey(
        Store, verbose_name="فروشگاه", on_delete=models.CASCADE, related_name="integration_connections",
    )
    provider_code = models.CharField("کدِ Provider", max_length=40)
    is_active = models.BooleanField("فعال", default=False)
    encrypted_credentials = models.TextField(
        "اعتبارنامه‌ی رمزنگاری‌شده", blank=True, default="",
        help_text="مقدارِ رمزنگاری‌شده — هرگز مستقیم خوانده نمی‌شود",
    )
    last_tested_at = models.DateTimeField("آخرین تستِ اتصال", null=True, blank=True)
    last_test_result = models.CharField("نتیجه‌ی آخرین تست", max_length=10, blank=True, default="")
    last_test_message = models.CharField("پیامِ آخرین تست", max_length=300, blank=True, default="")
    connected_at = models.DateTimeField("زمانِ اتصال", null=True, blank=True)

    class Meta:
        verbose_name = "اتصالِ یکپارچه‌سازیِ فروشگاه"
        verbose_name_plural = "اتصال‌هایِ یکپارچه‌سازیِ فروشگاه"
        constraints = [
            models.UniqueConstraint(fields=["store", "provider_code"], name="uniq_integration_per_store_provider"),
        ]

    def __str__(self):
        return f"{self.store.slug} ← {self.provider_code}"

    def get_credentials(self) -> dict:
        import json

        from apps.orders.encryption import decrypt_credential

        if not self.encrypted_credentials:
            return {}
        plaintext = decrypt_credential(self.encrypted_credentials)
        if not plaintext:
            return {}
        try:
            return json.loads(plaintext)
        except (json.JSONDecodeError, TypeError):
            return {}

    def set_credentials(self, credentials: dict) -> None:
        import json

        from apps.orders.encryption import encrypt_credential

        clean = {k: v for k, v in (credentials or {}).items() if v}
        self.encrypted_credentials = encrypt_credential(json.dumps(clean, ensure_ascii=False)) if clean else ""
