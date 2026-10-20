"""ARCH-02b — helpers for tests about the template gallery.

The Design Studio's own gallery is the ONE official place to browse, preview and apply a Ready Template. The old
dashboard gallery URL only forwards there (``?open=templates``), so tests read the gallery through the Studio's
server-rendered data (``studio.template_cards`` / ``studio.client.templates``), never through a second page.
"""

from django.urls import reverse


def legacy_gallery_url() -> str:
    return reverse("dashboard:storefront-builder-templates")


def studio_gallery_response(client, **extra):
    """GET the legacy gallery URL and follow it to the Studio (final response = the Studio editor page)."""
    return client.get(legacy_gallery_url(), follow=True, **extra)


def gallery_cards(response) -> list[dict]:
    return response.context["studio"]["template_cards"]


def gallery_cards_by_key(response) -> dict[str, dict]:
    return {card["preset"].key: card for card in gallery_cards(response)}


def gallery_client_templates(response) -> list[dict]:
    """The exact JSON-able catalog the Studio's gallery UI (r4_studio.js) renders from."""
    return response.context["studio"]["client"]["templates"]
