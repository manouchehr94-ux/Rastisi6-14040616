import uuid

from django.core.management.base import BaseCommand, CommandError

from apps.notifications.mail import events_service
from apps.notifications.models import NotificationOutbox
from apps.notifications.qa import require_qa


class Command(BaseCommand):
    help = "QA only (fake provider): inject a delivery / bounce / complaint event for a sent email through the real ingestion service."

    def add_arguments(self, parser):
        parser.add_argument("event", choices=["delivery", "bounce", "complaint"])
        parser.add_argument("--message-id", default="", help="provider message id; default = the most recent sent email")
        parser.add_argument("--event-id", default="", help="reuse an id to prove idempotency")
        parser.add_argument("--transient", action="store_true", help="bounce is transient (does NOT suppress)")

    def handle(self, *args, **o):
        require_qa()
        mid = o["message_id"]
        if not mid:
            row = (NotificationOutbox.objects.filter(channel=NotificationOutbox.Channel.EMAIL).exclude(provider_ref="")
                   .order_by("-id").first())
            if row is None:
                raise CommandError("no sent email found yet")
            mid = row.provider_ref
        event = events_service.ingest(
            provider="fake", event_id=o["event_id"] or f"qa-{uuid.uuid4().hex[:12]}", event_type=o["event"], message_id=mid,
            permanent=o["event"] == "bounce" and not o["transient"],
        )
        self.stdout.write("duplicate event id: ignored (idempotent)" if event is None else f"ingested {o['event']} for {mid}")
