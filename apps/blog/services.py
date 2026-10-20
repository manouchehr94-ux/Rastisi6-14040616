"""The ONE published-blog visibility contract for the shell and its sections."""

from django.db.models import Q
from django.utils import timezone

from .models import BlogPost


def published_posts_for_store(store):
    """Return Store-owned and legacy explicitly global published posts.

    A post owned by Store A is never visible to Store B. Existing NULL-owned
    posts retain the pre-migration platform-wide semantics for compatibility;
    all new demo material is explicitly Store-owned.
    """
    return BlogPost.objects.filter(
        Q(store=store) | Q(store__isnull=True),
        published_at__isnull=False,
        published_at__lte=timezone.now(),
    ).order_by("-published_at", "-created_at")
