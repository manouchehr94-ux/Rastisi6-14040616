"""Published, Store-scoped journal pages inside the universal storefront shell."""

from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET

from apps.stores.resolution import resolve_store_for_storefront

from .services import published_posts_for_store


def _render_journal(request, template, context, *, store):
    from apps.storefront_builder.services.storefront_context_service import (
        build_universal_storefront_context,
    )

    context.update(build_universal_storefront_context(
        request, store, "journal", page_context=context, shell_only=True,
    ))
    return render(request, template, context)


@require_GET
def journal_index(request):
    store = resolve_store_for_storefront(request)
    posts = published_posts_for_store(store)[:48]
    return _render_journal(request, "blog/journal_index.html", {"posts": posts}, store=store)


@require_GET
def journal_detail(request, slug):
    store = resolve_store_for_storefront(request)
    post = get_object_or_404(published_posts_for_store(store), slug=slug)
    return _render_journal(request, "blog/journal_detail.html", {"post": post}, store=store)
