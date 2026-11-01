"""Test helper for the tabbed «یکپارچه‌سازی‌ها» page: every category is its own URL (``?section=integrations&view=…``)."""

from django.urls import reverse

VIEWS = ("overview", "seo", "analytics", "torob", "enamad", "future")


def view_url(view: str = "overview") -> str:
    base = reverse("dashboard:settings") + "?section=integrations"
    return base if view == "overview" else f"{base}&view={view}"


def view_html(client, view: str = "overview", **extra) -> str:
    return client.get(view_url(view), **extra).content.decode()


def all_views_html(client, **extra) -> str:
    """The six categories concatenated — for assertions about «somewhere on the integrations page»."""
    return "\n".join(view_html(client, v, **extra) for v in VIEWS)
