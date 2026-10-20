"""Tiny helper shared by tests that need to drive the canonical R4 mutation route."""

import json

from django.urls import reverse


def r4_mutate(client, draft, mutation, *, base_revision=None):
    """POST one R4 mutation for ``draft`` through the real route (fresh revision unless given)."""
    draft.refresh_from_db()
    return client.post(
        reverse("dashboard:storefront-builder-r4-mutation"),
        data=json.dumps({
            "base_revision": draft.edit_revision if base_revision is None else base_revision,
            "mutation": mutation,
        }),
        content_type="application/json",
    )
