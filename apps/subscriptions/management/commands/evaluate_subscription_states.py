"""انتقال‌هایِ زمانیِ سررسیدشده‌ی اشتراک‌ها را اعمال می‌کند (تریال→ارفاق/انقضا،
ارفاق→تعلیق، دوره‌ی گذشته→ارفاق، لغوِ زمان‌بندی‌شده→لغو) — نگاه کنید به
ADR-66/67.

این کدبیس صفِ کارِ پس‌زمینه‌ای ندارد (ADR-49)، پس این دستور باید به‌صورتِ
دوره‌ای از یک زمان‌بندِ خارجی (cron/systemd timer) اجرا شود."""

from django.core.management.base import BaseCommand, CommandError

from apps.subscriptions.services.subscription_service import evaluate_subscription_states


class Command(BaseCommand):
    help = "انتقال‌هایِ زمانیِ سررسیدشده‌ی اشتراک‌ها را اعمال می‌کند."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true",
            help="فقط گزارش می‌دهد چه چیزی تغییر می‌کرد، بدونِ اعمالِ واقعی.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        results = evaluate_subscription_states(dry_run=dry_run)
        prefix = "[dry-run] " if dry_run else ""
        self.stdout.write(self.style.SUCCESS(
            f"{prefix}بررسی‌شده={results['scanned']}, "
            f"لغو={results['cancelled']}, ارفاق={results['grace']}, "
            f"تعلیق={results['suspended']}, انقضا={results['expired']}."
        ))

        if results.get("errors"):
            # The remaining rows WERE processed. A non-zero exit makes cron/run_job.sh alert, so a failing row is never silent.
            raise CommandError(f"{len(results['errors'])} item(s) failed (state transitions): " + ", ".join(
                f"{list(e.values())[0]}:{e['error']}" for e in results["errors"][:10]))
