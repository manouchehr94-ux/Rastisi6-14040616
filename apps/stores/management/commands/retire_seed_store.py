"""Remove the empty ``akhlaghi`` Store that migration ``stores.0002`` seeds in
every fresh database - so a clean install holds exactly the two demo stores.

Safety: dry-run unless ``--confirm``; refuses unless the store carries ONLY the
rows that migrations/provisioning create automatically (settings, footer,
default warehouse, default subscription, empty layout). Any product, order,
customer, membership, domain, media or other data aborts. This never touches
any other store.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.stores.models import Store

PROVISIONING_ONLY = {
    "core.shopsettings",
    "content.footersettings",
    "catalog.warehouse",
    "subscriptions.storesubscription",
    "subscriptions.subscriptionevent",
    "storefront_builder.storefrontlayout",
}


class Command(BaseCommand):
    help = "Delete the empty migration-seeded 'akhlaghi' store (dry-run unless --confirm)."

    def add_arguments(self, parser):
        parser.add_argument("--slug", default="akhlaghi")
        parser.add_argument("--confirm", action="store_true")

    def handle(self, *args, **opts):
        store = Store.objects.filter(slug=opts["slug"]).first()
        if store is None:
            self.stdout.write(f"store {opts['slug']!r} does not exist - nothing to do")
            return
        blocking = {}
        for rel in store._meta.related_objects:
            label = rel.related_model._meta.label_lower
            n = rel.related_model.objects.filter(**{rel.field.name: store}).count()
            if n and label not in PROVISIONING_ONLY:
                blocking[rel.related_model._meta.label] = n
        if blocking:
            raise CommandError(f"{store.slug} holds real data, refusing to delete: {blocking}")
        if not opts["confirm"]:
            self.stdout.write(f"dry-run: {store.slug} is empty (provisioning rows only); re-run with --confirm to delete")
            return
        with transaction.atomic():
            store.delete()
        self.stdout.write(self.style.SUCCESS(f"deleted empty seed store {opts['slug']!r}"))
