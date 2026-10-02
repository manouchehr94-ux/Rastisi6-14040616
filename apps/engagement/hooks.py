"""اتصالِ رویدادهایِ کسب‌وکار به کمپین‌هایِ ``EVENT`` — پس از commit و بدونِ اثر روی پرداخت."""

import logging

from django.db import transaction

logger = logging.getLogger(__name__)


def on_payment_success(order) -> None:
    def run():
        try:
            from apps.engagement.services.campaign_service import run_event_campaigns

            run_event_campaigns(order.store, order.customer)
        except Exception:  # noqa: BLE001 — کمپین نباید پرداختِ موفق را مخدوش کند
            logger.exception("event campaigns failed after payment of order %s", order.pk)

    transaction.on_commit(run)
