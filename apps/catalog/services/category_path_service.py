"""مسیرِ کاملِ دسته‌بندی (مثلاً «پوشاک > مردانه») — نمایشِ بدونِ ابهام برایِ
صادرات/واردات اکسل. نامِ دسته‌بندی در یک Store یکتا نیست (فقط اسلاگ یکتاست)،
پس نامِ تنها مبهم است؛ مسیرِ کامل تقریباً همیشه یکتاست و هر جا هنوز مبهم
باشد، فراخوان آن را به‌عنوانِ «مبهم» گزارش می‌کند (هرگز حدس نمی‌زند)."""

from apps.catalog.models import Category

PATH_SEPARATOR = " > "
_SEPARATOR_CHARS = ">‹›«»</\\|"


def category_path(category) -> str:
    """مسیرِ کاملِ ``category`` از ریشه تا خودش. ``category.parent`` باید (برایِ
    کارایی) از پیش با ``select_related`` واکشی شده باشد، اما در نبودِ آن هم
    درست کار می‌کند."""
    parts, seen, node = [], set(), category
    while node is not None and node.pk not in seen:
        seen.add(node.pk)
        parts.append(node.name)
        node = node.parent
    return PATH_SEPARATOR.join(reversed(parts))


def normalize_path_key(value: str) -> str:
    """کلیدِ مقایسه‌ی یک مسیر: جداکننده‌هایِ رایج یکسان و فاصله‌ها نرمال می‌شوند."""
    from apps.core.utils import normalization_key

    text = str(value or "")
    for char in _SEPARATOR_CHARS:
        text = text.replace(char, ">")
    return ">".join(normalization_key(part) for part in text.split(">") if part.strip())


def store_category_paths(store, *, leaves_only: bool = False) -> list:
    """فهرستِ ``(مسیر، Category)`` برایِ همه‌ی زیردسته‌هایِ Store (دسته‌هایِ
    ریشه‌ای قابلِ انتخابِ کالا نیستند). مرتب بر اساسِ مسیر."""
    categories = list(Category.objects.filter(store=store).select_related("parent", "parent__parent"))
    parent_ids = {c.parent_id for c in categories if c.parent_id}
    rows = []
    for category in categories:
        if category.parent_id is None:
            continue
        if leaves_only and category.pk in parent_ids:
            continue
        rows.append((category_path(category), category))
    rows.sort(key=lambda item: item[0])
    return rows
