"""ممیزیِ قالب‌هایِ پیامکِ قدیمی پیش از اعمالِ رندرِ سخت‌گیرانه (S2).

پیش‌فرض فقط‌خواندنی است. دسته‌بندی هر ``SmsTemplate``:

* ``ok``            — با رندرِ جدید سازگار است؛
* ``unsafe_syntax`` — ساختارِ غیرمجاز (``{x.y}``، ``{x[0]}``، ``{x:fmt}``، آکولادِ تنها…)؛
  در ارسالِ واقعی متنِ پیش‌فرض جایگزین می‌شود؛ با ``--apply --backup FILE`` متنِ
  پیش‌فرض ذخیره می‌شود و متنِ اصلی ابتدا در فایل پشتیبان نوشته می‌شود؛
* ``unknown_variable`` — از پیش هم ارسال نمی‌شد (متغیرِ ناشناخته)؛ فقط گزارش می‌شود.

همچنین ردیف‌هایِ بی‌اثرِ ``NotificationTemplate`` (پیامکِ رویدادهایِ قدیمی) را گزارش می‌کند."""

import json

from django.core.management.base import BaseCommand, CommandError

from apps.sms.events import DEFAULT_TEMPLATES, EVENT_VARIABLES
from apps.sms.models import SmsTemplate
from apps.sms.services import template_renderer


def classify(event_key: str, body: str) -> tuple[str, str]:
    try:
        template_renderer.validate(body, EVENT_VARIABLES.get(event_key, {}))
    except template_renderer.StrictTemplateError as exc:
        return ("unsafe_syntax" if exc.kind == "syntax" else "unknown_variable"), str(exc)
    return "ok", ""


class Command(BaseCommand):
    help = "Audit SmsTemplate bodies against the strict renderer (read-only unless --apply)."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="reset unsafe_syntax templates to the default text")
        parser.add_argument("--backup", help="JSON file receiving the original bodies (required with --apply)")
        parser.add_argument("--fail-on-issues", action="store_true")

    def handle(self, *args, **opts):
        if opts["apply"] and not opts["backup"]:
            raise CommandError("--apply requires --backup FILE")
        results = []
        for t in SmsTemplate.objects.order_by("event_key"):
            status, detail = classify(t.event_key, t.body)
            results.append((t, status, detail))
            self.stdout.write(f"{t.event_key:22s} {status:17s} {detail}")
        bad = [r for r in results if r[1] == "unsafe_syntax"]
        unknown = [r for r in results if r[1] == "unknown_variable"]

        stale = self._stale_notification_rows()
        self.stdout.write(f"templates={len(results)} unsafe_syntax={len(bad)} unknown_variable={len(unknown)} "
                          f"stale_notification_sms_rows={stale}")

        if opts["apply"] and bad:
            with open(opts["backup"], "w", encoding="utf-8") as fh:
                json.dump([{"id": t.pk, "event_key": t.event_key, "body": t.body} for t, _, _ in bad],
                          fh, ensure_ascii=False, indent=2)
            for t, _, _ in bad:
                if t.event_key in DEFAULT_TEMPLATES:
                    t.body = DEFAULT_TEMPLATES[t.event_key]
                    t.save(update_fields=["body", "updated_at"])
            self.stdout.write(f"reset {len(bad)} template(s); originals saved to {opts['backup']}")
        if opts["fail_on_issues"] and (bad or unknown):
            raise CommandError("template issues found")

    @staticmethod
    def _stale_notification_rows() -> int:
        from apps.notifications import events as ev
        from apps.notifications.models import NotificationTemplate

        keys = [e.key for e in ev.EVENTS.values() if e.legacy_sms_event]
        return NotificationTemplate.objects.filter(event_key__in=keys, channel="sms").count()
