from django.core.management.base import BaseCommand, CommandError

from apps.content import about_page
from apps.stores.models import Store


class Command(BaseCommand):
    help = (
        "Create the store's «درباره ما» content page (Draft, footer-linked) if it does not exist. Never overwrites an existing "
        "page's text. Publishing is explicit (--publish); the default is a dry run that only reports."
    )

    def add_arguments(self, parser):
        parser.add_argument("--store", required=True, help="Store slug")
        parser.add_argument("--create", action="store_true", help="actually create the Draft page (default: report only)")
        parser.add_argument("--publish", action="store_true", help="also publish it (implies --create); the placeholder text is shown as-is")

    def handle(self, *args, **opts):
        store = Store.objects.filter(slug=opts["store"]).first()
        if store is None:
            raise CommandError(f"unknown store: {opts['store']}")
        state = about_page.about_page_state(store)
        self.stdout.write(f"store={store.slug} about-us state={state['state']}")
        if not (opts["create"] or opts["publish"]):
            self.stdout.write("dry run: nothing written (use --create, and --publish only after reviewing the text)")
            return
        page, created, published_now = about_page.ensure_about_page(store, publish=opts["publish"])
        self.stdout.write(f"created={created} published_now={published_now} url={page.get_absolute_url()} status={page.status}")
