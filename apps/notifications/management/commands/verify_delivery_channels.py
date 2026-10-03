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
        from apps.core.models import ShopSettings
        from apps.sms.models import SmsBalance

        problems = []
        shops = ShopSettings.objects.filter(sms_enabled=True).select_related("store")
        if slug:
            shops = shops.filter(store__slug=slug)
        B = ShopSettings.SmsBackend
        for shop in shops:
            backend = shop.sms_backend
            line = f"sms store={shop.store.slug} backend={backend}"
            if backend == B.CONSOLE:
                line += " -> NOT REAL (messages are marked sent but never leave the server)"
                problems.append(f"{shop.store.slug}: console SMS backend")
            elif backend == B.MELIPAYAMAK and not (shop.melipayamak_username and shop.melipayamak_password):
                line += " -> credentials MISSING"
                problems.append(f"{shop.store.slug}: melipayamak credentials missing")
            elif backend == B.KAVENEGAR and not shop.kavenegar_api_key:
                line += " -> API key MISSING"
                problems.append(f"{shop.store.slug}: kavenegar api key missing")
            elif backend == B.SMSRASTI and not shop.smsrasti_device_token:
                line += " -> device token MISSING"
                problems.append(f"{shop.store.slug}: smsrasti device token missing")
            else:
                line += " -> configured (secrets not printed)"
            if backend != B.CONSOLE and not shop.sms_sender_number and backend != B.SMSRASTI:
                line += "; sender number NOT set (provider-approved sender/template required)"
                problems.append(f"{shop.store.slug}: sender number missing")
            credits = SmsBalance.objects.filter(store=shop.store).values_list("credits", flat=True).first()
            line += f"; credits={credits if credits is not None else 'no balance row'}"
            if credits is not None and credits <= 0 and backend != B.CONSOLE:
                problems.append(f"{shop.store.slug}: no SMS credit")
            self.stdout.write(line)
        owner_backend = getattr(settings, "RASTISI_OWNER_SMS_BACKEND", "console")
        self.stdout.write(f"platform (OTP/owner) sms backend: {owner_backend}" + (" -> NOT REAL" if owner_backend == "console" else ""))
        if owner_backend == "console":
            problems.append("platform OTP backend is console")
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
            self.stdout.write(f"test sms: status={log.status} provider={log.provider} (accepted != delivered; confirm on the handset)")
