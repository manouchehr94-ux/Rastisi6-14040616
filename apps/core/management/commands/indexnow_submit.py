"""Tell IndexNow participants (Bing & co.) which public URLs of ONE store exist/changed.

Safe by default: it only PRINTS what would be sent. Sending needs ``--send`` AND the platform switch ``RASTISI_INDEXNOW_ENABLED``
AND a publicly indexable store. It is a hint, not an indexing guarantee. Run it from a scheduler after a publish; a publish never
depends on it."""

from django.core.management.base import BaseCommand, CommandError
from django.test import RequestFactory

from apps.core import indexnow, seo, seo_policy
from apps.stores.models import Store, StoreDomain


class Command(BaseCommand):
    help = "Dry-run (default) or send the store's public URLs to IndexNow."

    def add_arguments(self, parser):
        parser.add_argument("--store", required=True, help="Store slug")
        parser.add_argument("--send", action="store_true", help="Actually send (needs RASTISI_INDEXNOW_ENABLED)")

    def handle(self, *args, **opts):
        store = Store.objects.filter(slug=opts["store"]).first()
        if store is None:
            raise CommandError("unknown store")
        domain = (StoreDomain.objects.filter(store=store, retired_at__isnull=True, is_primary=True).first()
                  or StoreDomain.objects.filter(store=store, retired_at__isnull=True).first())
        if domain is None:
            raise CommandError("the store has no domain")
        request = RequestFactory().get("/", HTTP_HOST=domain.hostname, secure=True)
        request.store = store
        state = seo_policy.indexability(request, store)
        origin = seo_policy.canonical_origin(request, store)
        urls = [e["loc"] for e in seo._sitemap_entries(request, store, origin=origin)] if state.indexable else []
        payload = indexnow.build_payload(store, origin, urls)
        self.stdout.write(f"store={store.slug} host={payload['host']} indexable={state.indexable} ({state.code}) urls={len(payload['urlList'])}")
        self.stdout.write(f"keyLocation={payload['keyLocation']}")
        if not opts["send"]:
            self.stdout.write("dry-run: nothing sent (use --send to submit)")
            return
        result = indexnow.submit(store, origin, urls, indexable=state.indexable)
        self.stdout.write(f"status={result.status} submitted={result.submitted} http={result.http_status}")
