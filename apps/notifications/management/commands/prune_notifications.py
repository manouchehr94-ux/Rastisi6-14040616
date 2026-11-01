from django.core.management.base import BaseCommand

from apps.notifications.services.inbox_engine import prune


class Command(BaseCommand):
    help = "سیاستِ نگهداریِ اعلانِ مدیران: رویدادهایِ منقضی‌شده (و سهمِ گیرندگان) حذف می‌شوند؛ اعلانِ سنجاق‌شده می‌ماند."

    def handle(self, *args, **options):
        self.stdout.write(f"deleted_events={prune()['deleted_events']}")
