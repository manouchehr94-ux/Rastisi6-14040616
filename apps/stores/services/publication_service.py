"""محاسبه‌ی «وضعیتِ مؤثرِ انتشار» یک Store — تک مرجعِ حقیقت (Section 6).

عمداً هیچ فیلدِ وضعیتِ تازه‌ای روی Store اضافه نمی‌کند (به‌جز ``onboarding_
completed_at``، که مفهومی کاملاً مستقل از Store.status و از وضعیتِ اشتراک
است) — این سرویس فقط سیگنال‌هایِ از پیش موجود را ترکیب می‌کند:

* ``Store.status`` (provisioning/active/suspended/closed)
* ``Store.onboarding_required_at`` + ``Store.onboarding_completed_at``
  (فروشگاهِ مدرنِ پورتال تا «انتشار»ِ نهاییِ آنبوردینگ خصوصی است؛ فروشگاهِ
  قدیمی بدونِ ``onboarding_required_at`` تحت‌تأثیر نیست)
* وضعیتِ مؤثرِ اشتراک (``apps.subscriptions.services.entitlement_service.
  get_subscription_access_state`` — از پیش موجود، Checkpoint 5A)

``apps.subscriptions`` را در سطحِ ماژول import نمی‌کند — ``StoreSubscription.
store`` خودش یک FK به ``stores.Store`` است، پس import در جهتِ برعکس یک
چرخه‌ی import می‌سازد؛ دقیقاً مثلِ همه‌جایِ دیگرِ این کدبیس (مثلاً
``apps.dashboard.context_processors.subscription_banner``)، import محلی/
داخلِ تابع است."""

from django.db import models


class PublicationState(models.TextChoices):
    ONBOARDING = "onboarding", "در حالِ راه‌اندازی (خصوصی)"
    TRIAL_PRIVATE = "trial_private", "آزمایشی (خصوصی — راه‌اندازی ناتمام)"
    TRIAL_PUBLIC = "trial_public", "آزمایشی (عمومی)"
    ACTIVE_PAID = "active_paid", "فعال (پولی)"
    RESTRICTED = "restricted", "محدودشده (نیازمندِ پرداخت)"
    SUSPENDED = "suspended", "معلق"
    INACTIVE = "inactive", "غیرفعال"


#: این وضعیت‌ها یعنی «Storefront عمومی نباید محتوا نمایش دهد» —
#: ``resolve_store_for_storefront`` دقیقاً همین مجموعه را می‌بندد.
NON_PUBLIC_STATES = frozenset({
    PublicationState.ONBOARDING,
    PublicationState.TRIAL_PRIVATE,
    PublicationState.RESTRICTED,
    PublicationState.SUSPENDED,
    PublicationState.INACTIVE,
})


def get_store_publication_state(store) -> str:
    from apps.stores.models import Store

    if store.status == Store.Status.CLOSED:
        return PublicationState.INACTIVE
    if store.status == Store.Status.SUSPENDED:
        return PublicationState.SUSPENDED
    if store.status == Store.Status.PROVISIONING:
        return PublicationState.ONBOARDING

    from apps.subscriptions.services.entitlement_service import AccessState, get_subscription_access_state

    access = get_subscription_access_state(store)

    if access.state in (AccessState.RESTRICTED, AccessState.EXPIRED):
        return PublicationState.RESTRICTED

    if store.onboarding_required_at is not None and store.onboarding_completed_at is None:
        # A Store created by the modern portal provisioning flow stays private
        # until the final onboarding Publish — decided BEFORE the "no
        # subscription" fail-open below, so a missing default plan (ADR-65's
        # fail-open at provisioning) can never make it public early.
        # (A genuinely restricted/expired subscription is reported as such above.)
        return PublicationState.TRIAL_PRIVATE

    if access.state == AccessState.NONE:
        # No subscription at all exists for this Store. Modern portal Stores
        # (onboarding_required_at set) were already handled above; what remains
        # is a legacy Store or one created ad hoc (e.g. throughout the test
        # suite) with no durable onboarding signal. Fail-open for those,
        # matching ADR-65's "never silently restrict a Store" principle.
        return PublicationState.ACTIVE_PAID

    if store.onboarding_completed_at is None:
        return PublicationState.TRIAL_PRIVATE

    if access.subscription_status == "trialing":
        return PublicationState.TRIAL_PUBLIC

    return PublicationState.ACTIVE_PAID


def is_publicly_visible(store) -> bool:
    return get_store_publication_state(store) not in NON_PUBLIC_STATES
