from django.core.management.base import BaseCommand

from apps.notifications.services import webpush


class Command(BaseCommand):
    help = "یک جفت‌کلیدِ VAPID تازه چاپ می‌کند (ذخیره نمی‌شود). کلیدِ خصوصی را فقط در محیطِ امن (RASTISI_VAPID_PRIVATE_KEY) بگذارید؛ هرگز در Repository."

    def handle(self, *args, **options):
        keys = webpush.generate_keypair()
        self.stdout.write(f"RASTISI_VAPID_PRIVATE_KEY={keys['private']}\n# public (safe to share): {keys['public']}")
