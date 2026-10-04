"""Delivery-channel readiness audit for operators. Read-only unless a test send is explicitly requested.

  manage.py verify_delivery_channels                       # config audit only (no network, no secrets printed)
  manage.py verify_delivery_channels --send-test-email you@your-domain --confirm-test-recipient
  manage.py verify_delivery_channels --send-test-sms 09xxxxxxxxx --store <slug> --confirm-test-recipient

Important distinction printed with every result: "ACCEPTED by provider" (HTTP/API success, what the
system records as SENT) is NOT "DELIVERED to the handset/inbox"; delivery receipts are not consumed
by this codebase. Console/locmem/dummy backends are reported as NOT REAL — a SENT row produced by
them proves nothing. Test sends go to a recipient YOU confirm is a dedicated test address; they use
the normal production path (credit gate, SmsLog, outbox history) and are never sent to customers."""

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError

NOT_REAL_EMAIL = ("console", "locmem", "dummy", "filebased")


class Command(BaseCommand):
    help = "Audit SMS/email delivery configuration; optional explicit test sends."

    def add_arguments(self, parser):
        parser.add_argument("--store", help="limit SMS audit / test send to this store slug")
        parser.add_argument("--send-test-email")
        parser.add_argument("--send-test-sms")
        parser.add_argument("--confirm-test-recipient", action="store_true",
                            help="required for test sends: confirms the recipient is a dedicated test address")

    def handle(self, *args, **opts):
        problems = self.audit_email() + self.audit_sms(opts.get("store"))
        self.stdout.write("NOTE: 'accepted by provider' (recorded as SENT) != 'delivered'; no delivery receipts are consumed.")
        if opts["send_test_email"] or opts["send_test_sms"]:
            if not opts["confirm_test_recipient"]:
                raise CommandError("test sends require --confirm-test-recipient (use a dedicated test address/number)")
            if opts["send_test_email"]:
                self.test_email(opts["send_test_email"])
            if opts["send_test_sms"]:
                self.test_sms(opts["send_test_sms"], opts.get("store"))
        self.stdout.write(f"problems: {len(problems)}")
        if problems:
            raise SystemExit(1)

    # ------------------------------------------------------------------ email
    def audit_email(self) -> list[str]:
        backend = settings.EMAIL_BACKEND
        real = not any(token in backend.lower() for token in NOT_REAL_EMAIL)
        self.stdout.write(f"email backend: {backend} -> {'REAL' if real else 'NOT REAL (nothing is delivered)'}")
        problems = [] if real else ["email backend is not a real transport"]
        if real and "smtp" in backend.lower():
            for name, ok in (("EMAIL_HOST", bool(settings.EMAIL_HOST)), ("EMAIL_HOST_USER", bool(settings.EMAIL_HOST_USER)),
                             ("EMAIL_HOST_PASSWORD", bool(settings.EMAIL_HOST_PASSWORD))):
                self.stdout.write(f"  {name}: {'set' if ok else 'MISSING'}")
                if not ok:
                    problems.append(f"{name} missing")
            self.stdout.write(f"  TLS={settings.EMAIL_USE_TLS} port={settings.EMAIL_PORT}")
        sender = settings.DEFAULT_FROM_EMAIL
        self.stdout.write(f"  from: {'configured' if '@' in sender else 'INVALID'} (domain {sender.split('@')[-1]})"
                          " — verify SPF/DKIM/DMARC for this domain at your DNS provider")
        return problems

    def test_email(self, to: str):
        sent = send_mail("RastiSi delivery test", "Dedicated test message — ignore.", settings.DEFAULT_FROM_EMAIL, [to], fail_silently=False)
        self.stdout.write(f"test email: transport accepted={bool(sent)} (check the inbox/spam of the test address to confirm delivery)")

    # -------------------------------------------------------------------- sms
    def audit_sms(self, slug) -> list[str]:
        """همان تصمیمِ زمانِ اجرا: روشِ هر فروشگاه ``phone`` (SmsRasti) یا ``platform`` (درگاهِ مرکزی) است؛
        اعتبارنامه‌ی ارائه‌دهنده فقط یک‌بار و در سطحِ پلتفرم بررسی می‌شود (نه به‌ازایِ فروشگاه)."""
        from apps.core.models import ShopSettings
        from apps.sms.services.delivery_status_service import get_sms_delivery_status

        problems = []
        shops = ShopSettings.objects.filter(sms_enabled=True).select_related("store")
        if slug:
            shops = shops.filter(store__slug=slug)
        platform = None
        for shop in shops:
            status = get_sms_delivery_status(shop.store)
            platform = status["platform"]
            line = f"sms store={shop.store.slug} method={status['method']} health={status['health']}"
            if status["method"] == "phone":
                seen = status["device"]["last_seen_at"]
                line += f" device_paired={status['device']['paired']} device_online={status['device']['online']} last_seen={seen:%Y-%m-%d %H:%M}" if seen else f" device_paired={status['device']['paired']} device_online=False last_seen=never"
                line += f" queued={status['queue']['pending'] + status['queue']['sending']} failed={status['queue']['failed']}"
            else:
                line += f" credits={status['credits']}"
            self.stdout.write(line)
            for message in status["errors"]:
                self.stdout.write(f"  ERROR: {message}")
                problems.append(f"{shop.store.slug}: {message}")
            for message in status["warnings"]:
                self.stdout.write(f"  WARNING: {message}")
        if platform is None:
            from apps.portal.services.owner_sms_service import describe_platform_backend

            platform = describe_platform_backend()
        self.stdout.write(
            f"platform sms gateway (used by 'platform' stores, all OTP/security): provider={platform['provider']} "
            f"{'REAL' if platform['real'] else 'NOT REAL (nothing is delivered)'}"
        )
        for message in platform["problems"]:
            self.stdout.write(f"  PLATFORM PROBLEM: {message}")
            problems.append(f"platform: {message}")
        return problems

    def test_sms(self, phone: str, slug):
        from apps.sms.services.sms_service import send_raw_sms
        from apps.stores.models import Store

        if not slug:
            raise CommandError("--store is required for --send-test-sms")
        store = Store.objects.filter(slug=slug).first()
        if store is None:
            raise CommandError("unknown store")
        log = send_raw_sms(phone=phone, message="RastiSi delivery test", store=store)
        if log is None:
            self.stdout.write("test sms: not attempted (sms disabled for the store)")
        else:
            note = ("QUEUED for the Android device — delivered only after the device acknowledges (watch the SmsRasti queue)"
                    if log.provider == "smsrasti" else "accepted != delivered; confirm on the handset")
            self.stdout.write(f"test sms: status={log.status} provider={log.provider} ({note})")
