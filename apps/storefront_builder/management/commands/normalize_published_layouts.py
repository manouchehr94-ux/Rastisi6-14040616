from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.storefront_builder.models import StorefrontLayout, StorefrontSection
from apps.storefront_builder.services import layout_service


class Command(BaseCommand):
    help = (
        "Explicit lifecycle boundary for LEGACY Published storefront versions: place every active section that sits in "
        "no cell and refresh the version's content fingerprint. A public request never does this (it is read-only). "
        "Idempotent; Published versions that are already engine-complete are not written."
    )

    def add_arguments(self, parser):
        parser.add_argument("--store", default="", help="Only this Store slug (default: every Store with a Published version).")
        parser.add_argument("--dry-run", action="store_true", help="List the affected Stores without writing.")

    def handle(self, *args, **options):
        layouts = StorefrontLayout.objects.filter(published_version__isnull=False).select_related("store", "published_version")
        if options["store"]:
            layouts = layouts.filter(store__slug=options["store"])
        changed = 0
        for layout in layouts.order_by("store__slug"):
            pending = StorefrontSection.objects.filter(
                page__version=layout.published_version, is_active=True, placement_cell__isnull=True, cell__isnull=True,
            ).count()
            if not pending:
                continue
            if options["dry_run"]:
                self.stdout.write(f"{layout.store.slug}: {pending} unplaced section(s) in Published v{layout.published_version.version_number}")
                changed += 1
                continue
            with transaction.atomic():
                if layout_service.normalize_published_composition(layout.store):
                    changed += 1
                    self.stdout.write(f"{layout.store.slug}: normalised Published v{layout.published_version.version_number} ({pending} section(s))")
        verb = "would change" if options["dry_run"] else "changed"
        self.stdout.write(self.style.SUCCESS(f"{verb} {changed} Store(s)."))
