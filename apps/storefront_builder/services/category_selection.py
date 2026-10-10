"""Deterministic, Store-scoped category selection for ``category_grid`` (``category_source``).

Eligible categories are the Store's ACTIVE categories whose whole ancestor chain is active.
Ordering is always (``order``, ``name``, ``pk``) inside a sibling group, so a selection is
stable between requests, Preview and Published. No category is ever invented: a caller that
reserves empty positions does so only AFTER consuming every eligible item (see ``min_slots``).

Modes
-----
``top_level``             top-level categories only (the historical behaviour, the default);
``top_then_descendants``  every top-level category first, then descendants breadth-first;
``all``                   the whole tree depth-first (each parent followed by its descendants);
``leaf``                  only categories without an active child, in depth-first order.
"""

from __future__ import annotations

from collections import defaultdict, deque

from apps.catalog.models import Category

CATEGORY_SOURCE_MODES = ("top_level", "top_then_descendants", "all", "leaf")


def select_categories(store, mode: str = "top_level") -> list[Category]:
    if mode not in CATEGORY_SOURCE_MODES:
        mode = "top_level"
    rows = list(Category.objects.filter(store=store, is_active=True).order_by("order", "name", "pk"))
    children: dict[int | None, list[Category]] = defaultdict(list)
    for category in rows:
        children[category.parent_id].append(category)
    roots = children.get(None, [])
    if mode == "top_level":
        return list(roots)

    def depth_first() -> list[Category]:
        out: list[Category] = []
        stack = list(reversed(roots))
        while stack:
            node = stack.pop()
            out.append(node)
            stack.extend(reversed(children.get(node.pk, [])))
        return out

    if mode == "all":
        return depth_first()
    if mode == "leaf":
        return [node for node in depth_first() if not children.get(node.pk)]
    # top_then_descendants: roots, then breadth-first descendants (parents keep their sibling order)
    out = list(roots)
    queue = deque(roots)
    while queue:
        node = queue.popleft()
        for child in children.get(node.pk, []):
            out.append(child)
            queue.append(child)
    return out
