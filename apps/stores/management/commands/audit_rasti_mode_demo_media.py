"""Read-only missing-media audit for the canonical shared fashion demo.

No records, paths or content are changed. A missing image is a data/media
problem, not permission to substitute a different merchant's image.
"""

from django.core.management.base import BaseCommand, CommandError

from apps.blog.services import published_posts_for_store
from apps.catalog.models import Category, ProductImage
from apps.content.models import FooterPaymentLogo, FooterTrustBadge
from apps.stores.models import Store


class Command(BaseCommand):
    help = "Audit media referenced by the shared Rasti Mode demo, without any writes."

    def handle(self, *args, **options):
        store = Store.objects.filter(slug="rasti-mode-demo").first()
        if store is None:
            raise CommandError("فروشگاه دموی پوشاک پیدا نشد؛ هیچ تغییری انجام نشد.")
        missing = []
        checked = 0

        def inspect(kind, ident, field):
            nonlocal checked
            if not field or not getattr(field, "name", ""):
                return
            checked += 1
            try:
                available = field.storage.exists(field.name)
            except (OSError, ValueError, NotImplementedError):
                available = False
            if not available:
                missing.append((kind, ident, field.name))

        for image in ProductImage.objects.filter(product__store=store).select_related("product"):
            inspect("product", image.product_id, image.image)
            inspect("thumbnail", image.product_id, image.thumbnail)
        for category in Category.objects.filter(store=store):
            inspect("category", category.pk, category.image)
        # Only the same scoped journal items this demo renders are audited.
        for post in published_posts_for_store(store):
            inspect("journal", post.pk, post.cover_image)
        for item in FooterTrustBadge.objects.filter(store=store):
            inspect("trust_badge", item.pk, item.image)
        for item in FooterPaymentLogo.objects.filter(store=store):
            inspect("payment_logo", item.pk, item.image)

        self.stdout.write(f"Media references checked: {checked}; missing: {len(missing)}")
        for kind, ident, filename in missing:
            self.stdout.write(f"MISSING {kind} id={ident}: {filename}")
        if missing:
            self.stdout.write(self.style.WARNING(
                "No files were modified. Restore genuine media files or update their references via the proper merchant UI."
            ))
        else:
            self.stdout.write(self.style.SUCCESS("All referenced image files are available."))
