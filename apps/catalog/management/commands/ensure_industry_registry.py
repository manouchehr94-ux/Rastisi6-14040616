"""Platform bootstrap step: make sure the industry (صنف) catalogue is loaded — safely and repeatably.

    python manage.py ensure_industry_registry            # read-only report; exit code 1 when the catalogue is not ready
    python manage.py ensure_industry_registry --apply    # load ONLY the missing templates, then report again
    python manage.py ensure_industry_registry --json

This is a PLATFORM operation (run once after ``migrate`` in every environment: production, staging, a fresh QA database) — never something a
customer, a request or a login triggers, and never tied to a Store. ``--apply`` calls ``seed_industry_templates --only-missing``: it creates the
templates that do not exist yet and leaves every existing row (and every Store installation) untouched, so running it again — or on a database
that is already complete — changes nothing. It does NOT run the full ``seed_industry_templates`` (whose ``update_or_create`` re-syncs existing
rows); use that one deliberately, with a plan, when the registry itself changed."""

import json

from django.core.management import call_command
from django.core.management.base import BaseCommand

from apps.catalog.services import industry_registry_readiness as readiness


class Command(BaseCommand):
    help = "بررسی (و با --apply بارگذاریِ فقط موارد گم‌شده‌ی) رجیستری صنف‌ها؛ idempotent و فقط برای اپراتور پلتفرم."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="الگوهای گم‌شده را بساز (رکوردهای موجود دست‌نخورده می‌مانند)")
        parser.add_argument("--json", action="store_true", help="خروجی JSON قابل‌پردازش ماشینی")

    def handle(self, *args, **options):
        before = readiness.check_registry()
        if options["apply"] and (before.missing or not before.is_ready):
            if before.missing:
                call_command("seed_industry_templates", only_missing=True, stdout=self.stderr)
            after = readiness.check_registry()
            applied = True
        else:
            after, applied = before, False

        if options["json"]:
            self.stdout.write(json.dumps({"applied": applied, "before": before.as_dict(), "after": after.as_dict()}, ensure_ascii=False, indent=2))
        else:
            self.stdout.write(
                f"رجیستری: {after.registry_total} · در پایگاه‌داده: {after.database_total} · فعال: {after.active_total} · "
                f"قابل‌ارائه به فروشنده: {after.offerable_total} · «سایر (صنف آزاد)»: {'قابل‌ارائه' if after.other_offerable else 'در دسترس نیست'}"
            )
            if applied:
                self.stdout.write(f"بارگذاری انجام شد: {before.database_total} → {after.database_total} الگو.")
            for problem in after.problems:
                self.stdout.write(self.style.WARNING(f"⚠️  {problem}"))
            if after.is_ready:
                self.stdout.write(self.style.SUCCESS("✅ رجیستری صنف‌ها آماده است."))
        if not after.is_ready:
            raise SystemExit(1)
