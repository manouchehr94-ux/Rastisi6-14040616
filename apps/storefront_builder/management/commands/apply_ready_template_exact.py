"""Explicit, recoverable, DRAFT-ONLY application of a Ready Template's exact recipe (the repair path for a Store whose
Draft accumulated sections from several templates/versions).

* Default run is a dry run: it prints exactly what would change and changes nothing.
* ``--confirm-replace`` performs the replacement through the ONE canonical mutation boundary
  (``r4_mutation_service.switch_template_current``): same active Draft, one history entry (Undo), a full ARCHIVED
  version snapshot of the previous design taken first (restorable from the version history, section media included).
* Locked sections are never bypassed unless ``--allow-locked`` is also given (and are included in the snapshot).
* Published is never touched and nothing is published; review the Preview in Studio and publish there.
* Merchant business data (products, brands, prices, stock, media files) is never read for writing.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.storefront_builder import layout_preset_registry
from apps.storefront_builder.services import r4_mutation_service
from apps.stores.models import Store

from .diagnose_ready_template_composition import build_report


class Command(BaseCommand):
    help = "اعمالِ صریح و قابل‌بازگشتِ ساختارِ دقیقِ یک قالب آماده روی Draft (پیش‌فرض: فقط گزارش)."

    def add_arguments(self, parser):
        parser.add_argument("--store", required=True)
        parser.add_argument("--template", required=True)
        parser.add_argument("--actor-username", required=True, help="کاربرِ مالک/مدیر که در تاریخچه ثبت می‌شود")
        parser.add_argument("--confirm-replace", action="store_true", help="تأیید صریحِ جایگزینیِ چیدمانِ فعلی")
        parser.add_argument("--allow-locked", action="store_true", help="اجازه‌ی جایگزینیِ بخش‌های قفل‌شده (با نسخه‌ی پشتیبان)")

    def handle(self, *args, **options):
        try:
            store = Store.objects.get(slug=options["store"])
        except Store.DoesNotExist as exc:
            raise CommandError("فروشگاه یافت نشد.") from exc
        preset = layout_preset_registry.get_layout_preset(options["template"])
        if preset is None or not preset.is_ready_template:
            raise CommandError("قالبِ آماده‌ی معتبری با این کلید وجود ندارد.")
        actor = get_user_model().objects.filter(username=options["actor_username"]).first()
        if actor is None:
            raise CommandError("کاربر یافت نشد.")

        report = build_report(store, preset)
        replacement = report["replacement"]
        for page_type, counts in replacement["pages"].items():
            self.stdout.write(
                f"صفحه {page_type}: {counts['current_sections']} بخش فعلی ← {counts['target_sections']} بخشِ قالب"
            )
        if replacement["already_applied"]:
            self.stdout.write("این قالب از قبل دقیقاً روی Draft اعمال است؛ چیزی تغییر نمی‌کند.")
            return
        if replacement["locked_sections"]:
            self.stdout.write(f"بخش‌های قفل‌شده: {len(replacement['locked_sections'])} (با --allow-locked جایگزین می‌شوند)")
        if not options["confirm_replace"]:
            self.stdout.write("حالت گزارش: هیچ تغییری انجام نشد. برای اجرا --confirm-replace را بدهید.")
            return

        try:
            r4_mutation_service.switch_template_current(
                store=store, actor=actor, template_key=preset.key, template_version=preset.version,
                confirm_replace=True, allow_locked=options["allow_locked"],
            )
        except r4_mutation_service.R4MutationError as exc:
            body = r4_mutation_service.error_response_body(exc)
            raise CommandError(f"{body['code']}: {body.get('message', '')}") from exc
        self.stdout.write(
            "انجام شد: فقط Draft تغییر کرد؛ نسخه‌ی قبلیِ طراحی در تاریخچه‌ی نسخه‌ها ذخیره شد. "
            "Published دست‌نخورده است — پس از دیدنِ پیش‌نمایش در Studio منتشر کنید."
        )
