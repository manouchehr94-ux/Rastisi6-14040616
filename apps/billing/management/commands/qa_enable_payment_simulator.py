"""LOCAL QA: configure the platform Zibal gateway with a DUMMY merchant and make it the default, so the subscription checkout offers an online method.

Refuses to run unless the QA simulator guard holds (DEBUG, non-production, opt-in flag, isolated QA database). Writes only the platform gateway row
(the same call Platform Admin uses). It never contacts a bank; credentials are a dummy string."""

from django.core.management.base import BaseCommand, CommandError

from apps.billing.providers import qa_simulator
from apps.portal.services import platform_gateway_service as pgs


class Command(BaseCommand):
    help = "QA only: enable the simulated Zibal platform gateway (dummy merchant) and make it the default."

    def handle(self, *args, **options):
        if not qa_simulator.is_active():
            raise CommandError(
                "The QA payment simulator is not active. Required: RASTISI_QA_PAYMENT_SIMULATOR=1, DJANGO_DEBUG=True, a database whose name "
                "contains 'qa' (or RASTISI_QA_SIMULATOR_DB_CONFIRM=<exact db name>) and not production mode. Nothing was changed."
            )
        pgs.save_gateway("zibal", credentials={"merchant": "QA-SIMULATOR-DUMMY-MERCHANT"}, sandbox=False, enabled=True)
        pgs.set_default("zibal")
        self.stdout.write(self.style.SUCCESS("Simulated Zibal gateway enabled and set as default (dummy merchant, no network)."))
