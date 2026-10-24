"""The bundle contract: on-disk layout, model scope and ownership paths.

Layout (``<bundle>`` is a directory, or the same tree inside a .zip)::

    manifest.json                 format, version, per-store counts + media hashes
    stores/<key>/store.json       identity block of the source store (informational)
    stores/<key>/data.json        Django-serialized rows, in ``MODEL_SPECS`` order
    media/<MEDIA_ROOT-relative>   every file referenced by a FileField in data.json

Scope is deliberately limited to *presentation content*: catalogue, media,
navigation, footer and the Studio layout (all versions). Customers, orders,
carts, SMS, billing, audit logs, sessions and users are NEVER exported.

Primary keys are preserved. Studio section settings reference products,
categories, menus and media assets by numeric id, so re-numbering rows would
silently break the published layouts. Consequently the rows of all stores that
share one target database must have disjoint primary keys; the validator
checks this and refuses to import otherwise.
"""

from __future__ import annotations

from dataclasses import dataclass

FORMAT_NAME = "rastisi-store-bundle"
FORMAT_VERSION = 1

MANIFEST_NAME = "manifest.json"
STORES_DIR = "stores"
MEDIA_DIR = "media"
STORE_FILE = "store.json"
DATA_FILE = "data.json"


@dataclass(frozen=True)
class ModelSpec:
    label: str
    #: ORM lookups (each ending in ``store``) that tie a row to its Store. A row
    #: belongs to the store when ANY path matches.
    store_paths: tuple[str, ...]


def _s(label: str, *paths: str) -> ModelSpec:
    return ModelSpec(label, tuple(paths) or ("store",))


_VERSION = "layout__store"
_PAGE = "version__layout__store"
_SECTION_PATH = "section__page__version__layout__store"

#: Order matters only for readability and for reporting; rows are written inside
#: one transaction with deferred FK checks.
MODEL_SPECS: tuple[ModelSpec, ...] = (
    _s("orders.TaxClass", "store"),
    _s("orders.TaxRate", "store"),
    _s("catalog.Vendor"),
    _s("catalog.Category"),
    _s("catalog.Brand"),
    _s("catalog.ProductTag"),
    _s("catalog.Attribute"),
    _s("catalog.AttributeValue", "attribute__store"),
    _s("catalog.Warehouse"),
    _s("catalog.Product"),
    _s("catalog.ProductVariant"),
    _s("catalog.ProductOption", "product__store"),
    _s("catalog.ProductOptionValue", "option__product__store"),
    _s("catalog.VariantOptionValue", "variant__store"),
    _s("catalog.ProductImage", "product__store"),
    _s("catalog.ProductVideo", "product__store"),
    _s("catalog.ProductAttributeValue", "product__store"),
    _s("catalog.ProductMetafield", "product__store"),
    _s("catalog.Specification", "product__store"),
    _s("catalog.WarehouseInventory"),
    _s("catalog.MerchantCollection"),
    _s("catalog.MerchantCollectionItem", "collection__store"),
    _s("content.ContentPage"),
    _s("content.MediaAsset"),
    _s("content.Menu"),
    _s("content.MenuItem", "menu__store"),
    _s("content.SocialLink"),
    _s("content.FooterSettings"),
    _s("content.FooterTrustBadge"),
    _s("content.FooterPaymentLogo"),
    _s("storefront_builder.StorefrontLayout"),
    _s("storefront_builder.StorefrontLayoutVersion", _VERSION),
    _s("storefront_builder.StorefrontPage", _PAGE),
    _s("storefront_builder.StorefrontContainer", "page__version__layout__store"),
    _s("storefront_builder.StorefrontCell", "container__page__version__layout__store"),
    _s("storefront_builder.StorefrontSection", "page__version__layout__store"),
    _s("content.HeroSlide", "store", _SECTION_PATH),
    _s("content.PromotionalBanner", "store", _SECTION_PATH),
    _s("content.StoryRailItem", "store", _SECTION_PATH),
    # ShopSettings last: it references ContentPage / TaxClass.
    _s("core.ShopSettings"),
)

SPEC_BY_LABEL = {spec.label: spec for spec in MODEL_SPECS}

#: Keys inside any Studio JSON blob (section/header/footer/appearance settings)
#: that hold primary keys of other bundle rows, and the model they point at.
JSON_REFERENCE_KEYS: dict[str, str] = {
    "product_ids": "catalog.Product",
    "category_ids": "catalog.Category",
    "brand_ids": "catalog.Brand",
    "collection_ids": "catalog.MerchantCollection",
    "menu_id": "content.Menu",
    "media_asset_id": "content.MediaAsset",
    "image_media_asset_id": "content.MediaAsset",
    "campaign_media_asset_id": "content.MediaAsset",
}

#: The six Studio page types the demos must provide (see storefront_builder).
REQUIRED_PAGE_TYPES = ("home", "product_detail", "listing", "collection", "search", "cart")

#: Credential-bearing columns that must never travel in a bundle. They are
#: dropped at export (the importer leaves the model default, i.e. empty) and the
#: validator fails any bundle that still carries a non-empty value.
SECRET_FIELD_PATTERN = r"(password|secret|token|api_key|apikey|credential)"
SECRET_FIELDS: dict[str, tuple[str, ...]] = {
    "core.ShopSettings": (
        "melipayamak_username", "melipayamak_password", "kavenegar_api_key",
        "smsrasti_device_token", "smsrasti_last_seen_at",
    ),
}
