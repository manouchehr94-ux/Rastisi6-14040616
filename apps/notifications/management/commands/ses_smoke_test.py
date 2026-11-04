"""LIVE Amazon SES smoke test — the ONLY notification command that can send real email, and it is opt-in twice.

Never run by automated tests, CI or the default QA launcher. It prints nothing secret (no keys, no tokens); failures are
reported by exception TYPE and AWS error code only.
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.notifications.mail.base import OutboundEmail
from apps.notifications.mail.registry import get_transport

SIMULATOR = {  # Amazon SES mailbox simulator: never reaches a real inbox, never counts against bounce/complaint reputation
    "success": "success@simulator.amazonses.com",
    "bounce": "bounce@simulator.amazonses.com",
    "complaint": "complaint@simulator.amazonses.com",
}
CONFIRM = "--i-understand-this-sends-real-email"


class Command(BaseCommand):
    help = "LIVE SES smoke test (explicit opt-in). Use --check-only to inspect a sender identity without sending anything."

    def add_arguments(self, parser):
        parser.add_argument("--from-address", required=True, help="sender address on a domain verified in SES, e.g. info@mybikestore.com")
        parser.add_argument("--to", default="", help="recipient; default = SES mailbox simulator address for --scenario")
        parser.add_argument("--scenario", choices=sorted(SIMULATOR), default="success")
        parser.add_argument("--check-only", action="store_true", help="read-only: look up the identity, send nothing")
        parser.add_argument(CONFIRM, dest="confirmed", action="store_true")

    def handle(self, *args, **o):
        if getattr(settings, "RASTISI_EMAIL_PROVIDER", "fake") != "ses":
            raise CommandError("RASTISI_EMAIL_PROVIDER is not 'ses'; refusing (nothing was sent).")
        sender = o["from_address"].strip().lower()
        if "@" not in sender:
            raise CommandError("--from-address must be a full e-mail address")
        domain = sender.rsplit("@", 1)[1]
        transport = get_transport()
        try:
            state = transport.get_identity(domain)
        except Exception as exc:  # noqa: BLE001
            raise CommandError(f"could not read the SES identity ({type(exc).__name__}). Check credentials/region/IAM.") from None
        self.stdout.write(f"identity {domain}: provider status={state.status} verified_for_sending={state.verified_for_sending}"
                          + (f" error_type={state.error_type}" if state.error_type else ""))
        if o["check_only"]:
            if not state.verified_for_sending:
                raise CommandError("the sender domain is NOT verified for sending (or SES could not be reached: check credentials, "
                                   "region and IAM). This check FAILED.")
            self.stdout.write("OK: identity is verified for sending at SES. Nothing was sent.")
            return
        if not o["confirmed"]:
            raise CommandError(f"live sending requires {CONFIRM}; nothing was sent.")
        if not state.verified_for_sending:
            raise CommandError("the sender domain is not verified for sending at SES; nothing was sent.")
        to = o["to"].strip() or SIMULATOR[o["scenario"]]
        outcome = transport.send(OutboundEmail(
            from_address=sender, from_name="RastiSi SES smoke test", to_address=to,
            subject="RastiSi SES smoke test", text_body="This is a RastiSi live-SES smoke test message.",
            tags={"purpose": "smoke_test"}))
        if outcome.ok:
            self.stdout.write(f"SENT to {to}; provider message id: {outcome.message_id}")
        else:
            raise CommandError(f"send failed: {outcome.error_code} (retryable={outcome.retryable})")
