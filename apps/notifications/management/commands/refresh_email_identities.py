"""Periodic revalidation of Store email sender identities (run from cron/scheduler, e.g. hourly).

    python manage.py refresh_email_identities            # re-check every identity that is due
    python manage.py refresh_email_identities --store 12 # force one Store now

Never sends mail; talks only to the configured provider's identity API."""

from django.core.management.base import BaseCommand

from apps.notifications.mail import provisioning_service as svc


class Command(BaseCommand):
    help = "Revalidate Store email sender identities with the email provider."

    def add_arguments(self, parser):
        parser.add_argument("--store", type=int, default=None, help="Store id to force-check")

    def handle(self, *args, **options):
        if options["store"]:
            from apps.stores.models import Store

            identity = svc.sync_sender_identity(Store.objects.get(pk=options["store"]))
            self.stdout.write(f"store={identity.store_id} status={identity.status} reason={identity.reason_code}")
            return
        result = svc.revalidate_due()
        self.stdout.write(f"checked={result['checked']} changed={result['changed']}")
