"""Final onboarding publication: publish the Storefront Draft, THEN mark onboarding complete.

One transaction, in this order:

1. lock the Store row (a double-click / racing POST waits, then sees the finished state and no-ops);
2. require a valid applied Ready Template (read from the real Storefront Layout provenance — never
   only ``Store.onboarding_stage``);
3. publish the Draft through the canonical ``layout_service.publish`` (no second publisher);
4. only then set ``onboarding_completed_at`` / ``onboarding_stage = DONE``.

Any failure rolls the whole thing back, leaving the Store private and onboarding incomplete.
"""

from dataclasses import dataclass

from django.db import DatabaseError, transaction
from django.utils import timezone

from apps.core.services.rate_limit import RateLimitExceeded
from apps.storefront_builder.services import layout_service, store_template_service
from apps.stores.models import Store

NO_TEMPLATE_MESSAGE = "برای انتشارِ فروشگاه ابتدا باید یک «قالبِ فروشگاه» انتخاب کنید."
PUBLISH_FAILED_MESSAGE = "انتشارِ ویترین انجام نشد و فروشگاه هنوز خصوصی است؛ لطفاً کمی بعد دوباره تلاش کنید."
RATE_LIMITED_MESSAGE = "تعدادِ انتشار در این بازه بیش از حدِ مجاز است؛ کمی بعد دوباره تلاش کنید."


class OnboardingPublishError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class PublishOutcome:
    already_completed: bool
    published_storefront: bool


def complete_onboarding(*, store, actor) -> PublishOutcome:
    try:
        with transaction.atomic():
            locked = Store.objects.select_for_update().get(pk=store.pk)
            if locked.onboarding_completed_at:
                return PublishOutcome(already_completed=True, published_storefront=False)

            applied = store_template_service.get_applied_template(locked)
            if applied is None:
                raise OnboardingPublishError("no_template", NO_TEMPLATE_MESSAGE)

            published = False
            if applied.location == "draft":
                try:
                    layout_service.publish(locked, user=actor)
                except layout_service.NoDraftToPublishError as exc:
                    raise OnboardingPublishError("no_draft", NO_TEMPLATE_MESSAGE) from exc
                except RateLimitExceeded as exc:
                    raise OnboardingPublishError("rate_limited", RATE_LIMITED_MESSAGE) from exc
                published = True
            # else: the Store's PUBLISHED version already carries a valid Ready Template and there is
            # no newer Draft — nothing to publish; just complete onboarding.

            locked.onboarding_completed_at = timezone.now()
            locked.onboarding_stage = Store.OnboardingStage.DONE
            locked.save(update_fields=["onboarding_completed_at", "onboarding_stage", "updated_at"])
            return PublishOutcome(already_completed=False, published_storefront=published)
    except DatabaseError as exc:  # the transaction is rolled back: still private, still incomplete
        raise OnboardingPublishError("database", PUBLISH_FAILED_MESSAGE) from exc
