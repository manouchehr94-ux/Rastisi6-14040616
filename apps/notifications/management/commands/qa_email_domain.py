from django.core.management.base import BaseCommand, CommandError

from apps.notifications.mail.fake import FakeTransport
from apps.notifications.qa import require_qa


class Command(BaseCommand):
    help = "QA only (fake provider): simulate the email provider's verdict for a sender domain. Does not touch the DB."

    def add_arguments(self, parser):
        parser.add_argument("action", choices=["verify", "fail", "temp-fail", "show"])
        parser.add_argument("domain", nargs="?", default="")

    def handle(self, *args, **o):
        require_qa()
        if o["action"] != "show" and not o["domain"]:
            raise CommandError("domain is required")
        domain = o["domain"].lower()
        if o["action"] == "verify":
            FakeTransport.verify(domain)
        elif o["action"] == "fail":
            FakeTransport.fail_domain(domain)
        elif o["action"] == "temp-fail":
            FakeTransport.temp_fail_domain(domain)
        else:
            from apps.notifications.mail.fake import _load_shared

            _load_shared()
            for d, e in sorted(FakeTransport.identities.items()):
                self.stdout.write(f"{d}: {e.get('status')}")
            return
        self.stdout.write(f"fake provider: {domain} -> {o['action']}. Now press «بررسیِ دوباره» in the store panel "
                          "(or run: manage.py refresh_email_identities).")
