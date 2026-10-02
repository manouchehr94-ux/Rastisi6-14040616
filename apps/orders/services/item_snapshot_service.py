"""اسنپ‌شاتِ تاریخیِ ویژگی‌هایِ کالا در لحظه‌ی خرید (برند، دسته، رنگ، سایز،
ویژگی‌ها) — موتورِ قواعدِ کمپین باید از «آنچه خریده شد» تصمیم بگیرد، نه از
وضعیتِ فعلیِ کاتالوگ (که ممکن است برند/رنگ/دسته‌ی کالا عوض شده باشد).

قرارداد: ``OrderItem.attributes_snapshot`` یک دیکشنری با ``v=1`` است:

``brand``       {"id", "name"} یا ``None``
``category``    {"id", "name", "ancestor_ids": [..]} یا ``None``
``colors``      [{"label", "hex"}]
``sizes``       [str]
``attributes``  {attribute_code: [label, ...]}
``source``      "snapshot" (ثبت‌شده در لحظه‌ی سفارش) یا "live" (جایگزینِ
                بازسازی‌شده از کاتالوگِ فعلی برایِ ردیف‌هایِ قدیمیِ بدونِ اسنپ‌شات)
"""

from __future__ import annotations

from apps.core.utils import normalize_text

SNAPSHOT_VERSION = 1

_COLOR_KEYWORDS = ("رنگ", "color", "colour")
_SIZE_KEYWORDS = ("سایز", "اندازه", "size")


def _is_color_name(name: str) -> bool:
    name = normalize_text(name or "").lower()
    return any(k in name for k in _COLOR_KEYWORDS)


def _is_size_name(name: str) -> bool:
    name = normalize_text(name or "").lower()
    return any(k in name for k in _SIZE_KEYWORDS)


def _category_info(category) -> dict | None:
    if category is None:
        return None
    ancestors: list[int] = []
    node = category.parent
    seen = {category.pk}
    while node is not None and node.pk not in seen:
        ancestors.append(node.pk)
        seen.add(node.pk)
        node = node.parent
    return {"id": category.pk, "name": category.name, "ancestor_ids": ancestors}


def build_item_snapshot(product, variant=None, *, source: str = "snapshot") -> dict:
    colors: list[dict] = []
    sizes: list[str] = []
    attributes: dict[str, list[str]] = {}

    def add_color(label, hex_code=""):
        label = (label or "").strip()
        if label and not any(c["label"] == label for c in colors):
            colors.append({"label": label, "hex": (hex_code or "").strip()})

    def add_size(label):
        label = (label or "").strip()
        if label and label not in sizes:
            sizes.append(label)

    def add_attr(code, label):
        label = (label or "").strip()
        if not code or not label:
            return
        bucket = attributes.setdefault(code, [])
        if label not in bucket:
            bucket.append(label)

    if variant is not None:
        if _is_color_name(variant.attribute):
            add_color(variant.value, variant.value_hex)
        elif _is_size_name(variant.attribute):
            add_size(variant.value)
        else:
            add_attr(normalize_text(variant.attribute), variant.value)
        for link in variant.option_values.select_related("option", "option_value"):
            option, value = link.option, link.option_value
            if option.input_type == "color" or _is_color_name(option.label):
                add_color(value.label, value.color_hex)
            elif _is_size_name(option.label):
                add_size(value.label)
            else:
                add_attr(option.attribute.code if option.attribute_id else normalize_text(option.label), value.label)

    for pav in product.attribute_values.select_related("attribute", "value"):
        attribute = pav.attribute
        if pav.value_id:
            label, hex_code = pav.value.label, pav.value.color_hex
        elif pav.text_value:
            label, hex_code = pav.text_value, ""
        elif pav.number_value is not None:
            label, hex_code = f"{pav.number_value.normalize():f}", ""
        elif pav.boolean_value is not None:
            label, hex_code = ("yes" if pav.boolean_value else "no"), ""
        else:
            continue
        if attribute.data_type == "color" or _is_color_name(attribute.label) or _is_color_name(attribute.code):
            add_color(label, hex_code)
        elif _is_size_name(attribute.label) or _is_size_name(attribute.code):
            add_size(label)
        add_attr(attribute.code, label)

    return {
        "v": SNAPSHOT_VERSION,
        "source": source,
        "brand": {"id": product.brand_id, "name": product.brand.name} if product.brand_id else None,
        "category": _category_info(product.category) if product.category_id else None,
        "colors": colors,
        "sizes": sizes,
        "attributes": attributes,
    }


def effective_item_snapshot(item) -> dict:
    """اسنپ‌شاتِ ثبت‌شده؛ برایِ ردیف‌هایِ قدیمی (بدونِ اسنپ‌شات) از کاتالوگِ
    فعلی بازسازی می‌شود و صریحاً ``source="live"`` علامت می‌خورد."""
    snap = item.attributes_snapshot or {}
    if snap.get("v") == SNAPSHOT_VERSION:
        return snap
    if item.product_id is None:
        return {"v": SNAPSHOT_VERSION, "source": "live", "brand": None, "category": None,
                "colors": [], "sizes": [], "attributes": {}}
    return build_item_snapshot(item.product, item.variant, source="live")
