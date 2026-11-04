import time

from django.core.management import call_command
from django.core.management.base import BaseCommand

from apps.notifications.qa import require_qa


class Command(BaseCommand):
    help = "QA only: loop that runs the notification outbox worker and the sender-identity revalidation every few seconds."

    def add_arguments(self, parser):
        parser.add_argument("--interval", type=float, default=5.0)
        parser.add_argument("--once", action="store_true")

    def handle(self, *args, **o):
        require_qa()
        while True:
            for name in ("process_notification_outbox", "refresh_email_identities"):
                try:
                    call_command(name, stdout=self.stdout)
                except Exception as exc:  # noqa: BLE001 — a failed batch must not kill the QA worker
                    self.stderr.write(f"{name}: {type(exc).__name__}: {exc}")
            if o["once"]:
                return
            time.sleep(o["interval"])
