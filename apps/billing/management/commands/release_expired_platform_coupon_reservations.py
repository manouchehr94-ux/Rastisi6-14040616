"""آزادسازیِ رزروهایِ منقضیِ کوپنِ پلتفرم (جاروب).

شمارشِ ظرفیت به این فرمان وابسته نیست (رزروِ منقضی خودبهخود حساب نمیشود)؛ این فرمان فقط وضعیتِ ردیفها، آمارِ ادمین و
ردگیری را بهروز نگه میدارد. امنِ اجرای مکرر (cron هر ۵ تا ۱۵ دقیقه). ``--dry-run`` فقط میشمارد."""

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.billing.models import PlatformCouponRedemption
from apps.billing.services import platform_coupon_service


class Command(BaseCommand):
    help = "Release expired platform coupon reservations (no financial effect); idempotent."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        if opts["dry_run"]:
            due = PlatformCouponRedemption.objects.filter(
                status=PlatformCouponRedemption.Status.RESERVED, expires_at__lte=timezone.now(),
            ).count()
            self.stdout.write(f"due={due} released=0 (dry-run)")
            return
        self.stdout.write(f"released={platform_coupon_service.release_expired_reservations()}")
