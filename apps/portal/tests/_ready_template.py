"""Test helper: choose a canonical Ready Template through the onboarding Template step."""

from apps.storefront_builder import layout_preset_registry


def first_ready_key() -> str:
    return layout_preset_registry.list_ready_templates()[0].key


def select_template(client, template_url: str, key: str | None = None, host: str = "rastisi.localhost"):
    return client.post(template_url, {"template_key": key or first_ready_key()}, HTTP_HOST=host)
