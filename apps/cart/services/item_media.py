"""RS-10 — ONE image resolver for cart rows (cart page, checkout, mini-cart).

Priority is the catalogue's own authority (``ProductVariant.display_image`` → the picked variant's exact image, then the
image bound to its option value (colour), then the product cover); there is no cart-specific rule. A placeholder is the
template's job and is used ONLY when neither exists or the stored file is not actually available — never an invented
picture and never an emoji while a real image exists."""

from dataclasses import dataclass

CART_ITEM_PREFETCH = (
    "product__images", "variant__images", "variant__option_values",
)


@dataclass(frozen=True)
class CartItemImage:
    url: str
    alt: str


def _file_available(field) -> bool:
    if not field or not getattr(field, "name", ""):
        return False
    try:
        return bool(field.storage.exists(field.name))
    except (OSError, ValueError, NotImplementedError):
        return False


def cart_item_image(item) -> CartItemImage | None:
    product = item.product
    image = item.variant.display_image if getattr(item, "variant_id", None) and item.variant is not None else product.cover_image
    if image is None and item.variant_id:
        image = product.cover_image
    if image is None:
        return None
    for field in (image.thumbnail, image.image):
        if _file_available(field):
            return CartItemImage(url=field.url, alt=image.alt or product.name)
    return None


def attach_item_images(items) -> None:
    for item in items:
        item.display_image = cart_item_image(item)
