"""READ-ONLY diagnosis: what explicit selection of a Ready Template would do to a Store's Draft.

Writes nothing (no Draft, section, container, history row, version or setting). It reports, per covered page, how many
sections the Draft has now versus the template's recipe, which sections would be replaced, which are locked, which
carry slot identities of OTHER template versions (e.g. the 26 ``stationery_spectrum:v1`` leftovers), and whether the
replacement needs the merchant's confirmation.
"""

import json

from django.core.management.base import BaseCommand, CommandError

from apps.storefront_builder import layout_preset_registry
from apps.storefront_builder.models import StorefrontLayout
from apps.storefront_builder.services import preset_service
from apps.stores.models import Store


def build_report(store, preset) -> dict:
    layout = StorefrontLayout.objects.filter(store=store).select_related("draft_version", "published_version").first()
    if layout is None or layout.draft_version is None:
        raise CommandError("این فروشگاه Draft فعال ندارد؛ چیزی برای تشخیص وجود ندارد.")
    draft = layout.draft_version
    summary = preset_service.describe_exact_replacement(draft, preset)
    target_prefix = f"{preset.key}:v{preset.version}:"
    foreign = {}
    for page_type in summary["pages"]:
        slots = list(
            draft.get_page(page_type).sections.order_by("order", "id").values_list("template_slot_key", flat=True)
        )
        foreign[page_type] = {
            "sections_total": len(slots),
            "from_other_template_or_version": sorted({s.rsplit(":", 1)[0] for s in slots if s and not s.startswith(target_prefix)}),
            "from_other_template_or_version_count": sum(1 for s in slots if s and not s.startswith(target_prefix)),
            "merchant_created_count": sum(1 for s in slots if not s),
        }
    published = layout.published_version
    return {
        "store": store.slug,
        "draft": {"id": draft.pk, "revision": draft.edit_revision, "provenance": draft.template_provenance},
        "published": {"id": published.pk, "provenance": published.template_provenance} if published else None,
        "target": {"key": preset.key, "version": preset.version},
        "replacement": summary,
        "composition": foreign,
        "writes_performed": False,
    }


class Command(BaseCommand):
    help = "تشخیصِ فقط‌خواندنیِ اثرِ انتخابِ صریحِ یک قالب آماده روی Draft یک فروشگاه (هیچ چیز نوشته نمی‌شود)."

    def add_arguments(self, parser):
        parser.add_argument("--store", required=True, help="اسلاگِ فروشگاه")
        parser.add_argument("--template", required=True, help="کلیدِ قالبِ آماده")

    def handle(self, *args, **options):
        try:
            store = Store.objects.get(slug=options["store"])
        except Store.DoesNotExist as exc:
            raise CommandError("فروشگاه یافت نشد.") from exc
        preset = layout_preset_registry.get_layout_preset(options["template"])
        if preset is None or not preset.is_ready_template:
            raise CommandError("قالبِ آماده‌ی معتبری با این کلید وجود ندارد.")
        self.stdout.write(json.dumps(build_report(store, preset), ensure_ascii=False, indent=2, default=str))
