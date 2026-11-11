"""انتقال‌هایِ زمانیِ سررسیدشده‌ی اشتراک‌ها را اعمال می‌کند (تریال→ارفاق/انقضا،
ارفاق→تعلیق، دوره‌ی گذشته→ارفاق، لغوِ زمان‌بندی‌شده→لغو) — نگاه کنید به
ADR-66/67.

این کدبیس صفِ کارِ پس‌زمینه‌ای ندارد (ADR-49)، پس این دستور باید به‌صورتِ
دوره‌ای از یک زمان‌بندِ خارجی (cron/systemd timer) اجرا شود."""

from django.core.management.base import BaseCommand, CommandError
from apps.core.job_lock import exclusive

from apps.subscriptions.services.subscription_service import evaluate_subscription_states


class Command(BaseCommand):
    help = "انتقال‌هایِ زمانیِ سررسیدشده‌ی اشتراک‌ها را اعمال می‌کند."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true",
            help="فقط گزارش می‌دهد چه چیزی تغییر می‌کرد، بدونِ اعمالِ واقعی.",
        )

    @exclusive("evaluate_subscription_states")
    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        results = evaluate_subscription_states(dry_run=dry_run)
        # F-08: restore financially suspended subscriptions whose paid (e.g. future) period has begun. Always attempted, even if
        # the state transitions above reported an error, so one failure cannot keep a paid store suspended.
        from apps.billing.services import financial_suspension_service

        restored = financial_suspension_service.evaluate_restorations(dry_run=dry_run)
        results["errors"] = list(results.get("errors") or []) + restored["errors"]
        self.stdout.write(f"financial_suspension_restored={restored['restored']} (scanned={restored['scanned']})")
        prefix = "[dry-run] " if dry_run else ""
        self.stdout.write(self.style.SUCCESS(
            f"{prefix}بررسی‌شده={results['scanned']}, "
            f"لغو={results['cancelled']}, ارفاق={results['grace']}, "
            f"تعلیق={results['suspended']}, انقضا={results['expired']}."
        ))

        if results.get("errors"):
            # The remaining rows WERE processed. A non-zero exit makes cron/run_job.sh alert, so a failing row is never silent.
            raise CommandError(f"{len(results['errors'])} item(s) failed (state transitions / financial restoration): " + ", ".join(
                f"{list(e.values())[0]}:{e['error']}" for e in results["errors"][:10]))
