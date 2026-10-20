"""RS-06 — the store's «درباره ما» page on the EXISTING content-page system (``ContentPage``), nothing parallel.

Price-inquiry CTAs resolve to ``/pages/about-us/`` of THEIR OWN store (see ``pricing_mode_service.inquiry_destination_url``).
A store that never created that page used to get a dead label; this module gives the merchant a one-click, idempotent way
to create it. Creating is NOT publishing: a new page is a Draft with an explicit placeholder text, and it goes public only
through the merchant's own «انتشار» action (or an explicit ``--publish`` of the management command)."""

from django.db import transaction
from django.utils import timezone

from .models import ContentPage

ABOUT_SLUG = "about-us"
ABOUT_TITLE = "درباره ما"
PLACEHOLDER_BODY = (
    "<p><strong>متنِ نمایشی — پیش از انتشار ویرایش کنید.</strong></p>"
    "<p>این صفحه هنوز توسط فروشگاه تکمیل نشده است. معرفی فروشگاه، داستان برند و راه‌های ارتباط با شما را اینجا بنویسید.</p>"
)


def get_about_page(store):
    return ContentPage.objects.filter(store=store, slug=ABOUT_SLUG).first()


def about_page_state(store) -> dict:
    """``state``: ``missing`` | ``draft`` | ``published`` (+ the page)."""
    page = get_about_page(store)
    if page is None:
        return {"state": "missing", "page": None}
    return {"state": "published" if page.status == ContentPage.Status.PUBLISHED else "draft", "page": page}


@transaction.atomic
def ensure_about_page(store, *, publish: bool = False, actor=None):
    """Create the store's About page if absent (Draft, linked in the footer) — never overwrites an existing page's text.
    ``publish=True`` publishes it (explicit act); returns ``(page, created, published_now)``."""
    page = ContentPage.objects.select_for_update().filter(store=store, slug=ABOUT_SLUG).first()
    created = False
    if page is None:
        page = ContentPage.objects.create(
            store=store, title=ABOUT_TITLE, slug=ABOUT_SLUG, body=PLACEHOLDER_BODY,
            summary="معرفی فروشگاه و راه‌های ارتباط", status=ContentPage.Status.DRAFT,
            show_in_footer=True, footer_column=ContentPage.FooterColumn.QUICK_ACCESS,
        )
        created = True
    published_now = False
    if publish and page.status != ContentPage.Status.PUBLISHED:
        page.status = ContentPage.Status.PUBLISHED
        page.published_at = timezone.now()
        page.published_by = actor
        page.save(update_fields=["status", "published_at", "published_by", "updated_at"])
        published_now = True
    return page, created, published_now
