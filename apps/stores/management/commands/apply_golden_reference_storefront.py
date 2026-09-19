"""Management command — set up the Golden Reference Storefront (G1).

Turns the isolated ``rasti-mode-demo`` store into the first visually complete
Golden Reference Storefront: a premium multi-brand fashion/lifestyle store a
prospective merchant can visit to see what a finished RastiSi storefront looks
like.

It is a thin, reproducible orchestration over existing infrastructure:

1. Run the idempotent demo seed (``seed_ready_template_fashion_demo``) for the
   real Catalog/content ONLY — it is NOT asked to Apply+Publish a Ready
   Template (no ``--ready-template``).
2. Apply the REAL registered ``fashion_promo_catalog`` baseline, layer the
   Golden customization (identity palette, premium global shell variants, the
   approved commercial Home composition), and publish — all via
   ``golden_reference_service.apply_golden_reference_storefront`` through the
   normal preset/appearance/publish contracts. This is the single,
   architecturally-correct Apply+Publish mechanism (honest provenance + authored
   ``template_baseline_snapshot`` + merchant divergence).

Idempotent and tenant-scoped: only the fixed ``rasti-mode-demo`` slug is ever
touched. Re-running converges to the same published state (no duplicate rows).
The destructive ``--reset`` (which deletes and rebuilds ONLY the demo store) is
forwarded to the seed and must never be used on protected/real merchant stores.

This does NOT add a Ready Template — the A8 catalog stays at exactly 50. The
store's recorded provenance remains ``fashion_promo_catalog``.
"""

from io import StringIO

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from apps.storefront_builder.services import golden_reference_service, layout_service
from apps.stores.management.commands.seed_ready_template_fashion_demo import (
    STORE_SLUG,
)
from apps.stores.models import Store

GOLDEN_BASELINE_TEMPLATE_KEY = golden_reference_service.GOLDEN_BASELINE_TEMPLATE_KEY


class Command(BaseCommand):
    help = (
        "برپاییِ «Golden Reference Storefront» رویِ فروشگاهِ Demoِ ایزوله "
        f"(«{STORE_SLUG}») — یک فروشگاهِ پوشاک/لایف‌استایلِ چندبرندِ premiumِ "
        "کاملاً بصری، ساخته‌شده تماماً از رویِ قراردادهایِ تولیدِ موجود. "
        "Idempotent و Tenant-scoped."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--owner-username",
            default="",
            help="یوزرنیمِ یک کاربرِ موجود که (اختیاری) مالکِ StoreMembership این فروشگاهِ Demo می‌شود.",
        )
        parser.add_argument(
            "--reset",
            action="store_true",
            help=(
                f"پیش از برپایی، فقط فروشگاهِ Demo با اسلاگِ ثابتِ «{STORE_SLUG}» را کاملاً "
                "حذف و بازسازی می‌کند (به دستورِ seed فوروارد می‌شود). هرگز روی فروشگاهِ "
                "واقعی/محافظت‌شده استفاده نشود."
            ),
        )

    def handle(self, *args, **options):
        seed_args = []
        if options.get("reset"):
            seed_args.append("--reset")
        owner_username = (options.get("owner_username") or "").strip()
        if owner_username:
            seed_args += ["--owner-username", owner_username]

        # Step 1 — real demo Catalog/content ONLY (idempotent). The seed is
        # deliberately NOT asked to Apply+Publish the Ready Template
        # (no --ready-template): the Golden service below is the single,
        # architecturally-correct Apply+Publish mechanism (real registered
        # baseline Apply -> Golden merchant customization -> Publish).
        call_command("seed_ready_template_fashion_demo", *seed_args, stdout=StringIO())

        try:
            store = Store.objects.get(slug=STORE_SLUG)
        except Store.DoesNotExist as exc:  # pragma: no cover - seed always creates it
            raise CommandError(
                f"فروشگاهِ Demo «{STORE_SLUG}» پس از اجرای seed یافت نشد."
            ) from exc

        # Step 2 — Golden customization via existing preset/appearance/publish.
        published = golden_reference_service.apply_golden_reference_storefront(store)
        home = published.home_page()
        section_order = list(home.sections.order_by("order").values_list("section_key", flat=True))

        # Step 3 (P5-W5C Independent Architect repair) — leave a fresh,
        # editable Draft after publishing, exactly like a real merchant's
        # Publish action does. The Ready Template Gallery's live-preview
        # route (Demo mode) reads an EXISTING Draft only and never
        # bootstraps one itself (Preview must create zero persistence) —
        # so the canonical Demo Store must already have one ready, the
        # same way `get_or_create_draft` already keeps a merchant's own
        # Store always Draft-ready the moment they open their Gallery.
        # `publish()` sets `layout.draft_version = None`; without this
        # step the Demo Store would be un-previewable immediately after
        # every fresh seed/deploy.
        layout_service.get_or_create_draft(store)

        self.stdout.write(
            self.style.SUCCESS(
                "apply_golden_reference_storefront با موفقیت اجرا شد:\n"
                f"  Store: {store.slug}\n"
                f"  Baseline Ready Template (provenance): {GOLDEN_BASELINE_TEMPLATE_KEY}\n"
                f"  Palette: {golden_reference_service.GOLDEN_PALETTE_SLUG}\n"
                f"  Header: {golden_reference_service.GOLDEN_HEADER_VARIANT}\n"
                f"  Footer: {golden_reference_service.GOLDEN_FOOTER_VARIANT}\n"
                f"  Bottom Nav: {golden_reference_service.GOLDEN_BOTTOM_NAV_VARIANT}\n"
                f"  Home ({len(section_order)} بخش): {' → '.join(section_order)}\n"
                f"  Published version: #{published.pk}\n"
            )
        )
