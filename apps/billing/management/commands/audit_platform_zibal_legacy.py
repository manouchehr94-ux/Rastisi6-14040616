"""Read-only readiness check for retiring the legacy platform-Zibal columns (``PlatformConfiguration.encrypted_zibal_credentials`` /
``zibal_sandbox_mode``). Never writes, never prints a secret. Exit code 1 (with ``--strict``) means the legacy copy is still the
EFFECTIVE source somewhere, so the columns/fallback must NOT be removed yet.

Safe to retire when, in EVERY environment (QA + production), this command reports all of:
  1. legacy_has_data == False, OR a canonical PlatformGatewayConfig(zibal) row exists (migration portal/0019 ran);
  2. effective_source == "row" (or "none" when Zibal was never configured) — never "legacy";
  3. nothing reads the legacy columns any more (``credentials_and_mode`` / ``_is_enabled`` fallbacks) — checked by tests.
Then a SEPARATE, explicitly authorised migration may drop the two columns and a code change may delete the fallback."""

from django.core.management.base import BaseCommand, CommandError

from apps.portal.models import PlatformGatewayConfig
from apps.portal.services import platform_gateway_service as pgs
from apps.portal.services.platform_config_service import get_platform_configuration


class Command(BaseCommand):
    help = "گزارشِ فقط‌خواندنیِ آمادگیِ بازنشستگیِ ستون‌هایِ قدیمیِ زیبالِ پلتفرم. --strict: اگر هنوز منبعِ مؤثر «legacy» است کدِ ۱."

    def add_arguments(self, parser):
        parser.add_argument("--strict", action="store_true")

    def handle(self, *args, **options):
        config = get_platform_configuration()
        legacy_creds = bool(config.encrypted_zibal_credentials)
        legacy_data = legacy_creds or bool(config.zibal_sandbox_mode)
        row = PlatformGatewayConfig.objects.filter(gateway_code="zibal").first()
        _creds, _sandbox, source = pgs.credentials_and_mode("zibal")
        report = {
            "legacy_has_data": legacy_data, "canonical_row_exists": row is not None,
            "canonical_has_credentials": bool(row and row.get_credentials()),
            "effective_source": source,                                   # row | legacy | none
            "default_provider": config.default_payment_provider,
        }
        for key, value in report.items():
            self.stdout.write(f"{key}: {value}")
        blockers = []
        if source == "legacy":
            blockers.append("منبعِ مؤثرِ زیبال هنوز ستون‌هایِ قدیمی است؛ migration portal/0019 را اجرا و نتیجه را بررسی کنید.")
        if legacy_data and row is None:
            blockers.append("دادهٔ قدیمی هست امّا ردیفِ کانونی وجود ندارد.")
        if blockers:
            for b in blockers:
                self.stderr.write(self.style.ERROR(f"[blocker] {b}"))
            if options["strict"]:
                raise CommandError("بازنشستگیِ ستون‌هایِ قدیمی هنوز امن نیست.")
            return
        self.stdout.write(self.style.SUCCESS("این محیط برایِ بازنشستگیِ ستون‌هایِ قدیمی آماده است (باید در همه‌ی محیط‌ها تأیید شود)."))
