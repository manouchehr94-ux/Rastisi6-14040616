"""StoreMembership-based merchant-dashboard authorization.

This module is the single place that decides "may this User act on this
Store's merchant dashboard, and with which permissions." It replaces the
historical, tenant-blind ``user.is_staff`` check that
``apps.dashboard.decorators.staff_required`` used on its own (see
``docs/docs/product/00_PROJECT_MASTER_REFERENCE.md`` §10.2/§11.1 — this was
the explicitly recorded, highest-priority gap: any ``is_staff=True`` account
could reach *any* Store's ``/admin-portal/`` once Host-based Store resolution
picked that Store, because nothing checked *which* Store the user actually
belonged to).

Authorization here is layered on top of, not a replacement for, tenant
resolution (``apps.stores.resolution``): resolution decides *which* Store a
request is for; this module decides *whether* the requesting User may act on
that Store, and *what* they may do. Neither layer substitutes for the other.

Only an ``ACTIVE`` ``StoreMembership`` row for the exact Store in question
grants access — never ``is_staff``, ``is_superuser``, membership in a
*different* Store, or an ``INVITED``/``REVOKED`` row.

Role naming note (Phase 1B): the originating request names roles as
"Owner / Administrator / Manager / Product Manager / Order Manager /
Content Manager / Analyst or Read-Only." Per that same request's own
instruction to reuse existing role names rather than create a duplicate
role system, this maps onto the ``StoreMembership.Role`` choices that
already existed before this PR:

* Owner            -> ``Role.OWNER``
* Administrator     -> ``Role.ADMINISTRATOR`` (also covers the generic
  "Manager" description — full operational access short of ownership-tier
  actions like staff/domain/subscription management)
* Product Manager   -> ``Role.CATALOG_MANAGER``
* Order Manager     -> ``Role.ORDER_MANAGER``
* Content Manager   -> ``Role.CONTENT_EDITOR``
* Analyst/Read-Only -> ``Role.ANALYST``

No new ``Role`` value was added.
"""

from .models import StoreMembership

Role = StoreMembership.Role

# ---------------------------------------------------------------------------
# Permission registry
# ---------------------------------------------------------------------------
#
# Granular permission keys. Some of these (marked "reserved" below) have no
# corresponding view yet — attributes, discounts/coupons, customer editing,
# domain management, and subscription management are not yet implemented as
# merchant-admin features at all (no route exists for them in
# ``apps.dashboard.urls``). Staff/membership management (``STAFF_MANAGE``)
# *is* implemented — see ``apps.stores.services.membership_service`` and
# ``apps.dashboard.views`` staff_* views. Unimplemented keys are still
# defined and given a role mapping here, per the Phase 1B
# role-permission-matrix requirement, so that the day a view for them exists
# it only needs a ``permission_required(...)`` decorator — no new registry
# design.

DASHBOARD_VIEW = "dashboard.view"

PRODUCT_VIEW = "product.view"
PRODUCT_CREATE = "product.create"
PRODUCT_EDIT = "product.edit"
PRODUCT_DELETE = "product.delete"
CATEGORY_MANAGE = "category.manage"
BRAND_MANAGE = "brand.manage"
ATTRIBUTE_MANAGE = "attribute.manage"  # reserved — no attribute feature yet
VARIANT_MANAGE = "variant.manage"
INVENTORY_MANAGE = "inventory.manage"
MEDIA_MANAGE = "media.manage"

# Checkpoint 3 — Warehouse/reservation/transfer permissions.
WAREHOUSE_VIEW = "warehouse.view"
WAREHOUSE_MANAGE = "warehouse.manage"  # create/edit/archive/set-default warehouse
TRANSFER_VIEW = "transfer.view"
TRANSFER_MANAGE = "transfer.manage"  # create/ship/receive/cancel a stock transfer
RESERVATION_VIEW = "reservation.view"

# Checkpoint 3 — Shipping/Tax settings permissions.
SHIPPING_SETTINGS_VIEW = "shipping.view"
SHIPPING_SETTINGS_MANAGE = "shipping.manage"
TAX_SETTINGS_VIEW = "tax.view"
TAX_SETTINGS_MANAGE = "tax.manage"

# Checkpoint 4 — Product/Variant/Inventory import-export and Customer CRM.
IMPORT_EXPORT_VIEW = "import_export.view"
IMPORT_EXPORT_MANAGE = "import_export.manage"  # trigger exports, upload/execute imports
CUSTOMER_NOTE_MANAGE = "customer.note_manage"
CUSTOMER_TAG_MANAGE = "customer.tag_manage"
CUSTOMER_SEGMENT_VIEW = "customer.segment_view"
CUSTOMER_SEGMENT_MANAGE = "customer.segment_manage"
CUSTOMER_EXPORT = "customer.export"  # separate from IMPORT_EXPORT_* — PII, gated on its own

ORDER_VIEW = "order.view"
ORDER_STATUS_CHANGE = "order.status_change"

CUSTOMER_VIEW = "customer.view"
CUSTOMER_EDIT = "customer.edit"  # reserved — no customer-edit view yet

REPORTS_VIEW = "reports.view"
COUPON_VIEW = "coupon.view"
DISCOUNT_MANAGE = "discount.manage"  # Coupon create/edit/archive (Admin Panel Completion Program checkpoint 2)

RETURN_VIEW = "return.view"
RETURN_MANAGE = "return.manage"  # approve/reject/receive/inspect/complete
REFUND_VIEW = "refund.view"
REFUND_MANAGE = "refund.manage"  # create/execute a refund

AUDIT_LOG_VIEW = "audit.view"

SETTINGS_MANAGE = "settings.manage"
PAYMENT_SETTINGS_MANAGE = "settings.payment"
SMS_SETTINGS_MANAGE = "settings.sms"
CONTENT_MANAGE = "content.manage"
# Dedicated boundary for the visual storefront layout builder (header/footer/
# homepage sections/draft-publish). Deliberately separate from CONTENT_MANAGE
# — editing the storefront's visual arrangement is a different authorization
# surface from editing CMS pages/hero slides/menus, even though today the
# same CONTENT_EDITOR role happens to get both.
STOREFRONT_LAYOUT_MANAGE = "storefront_layout.manage"

# Merchant Manual Collections (Phase B) — a Collection has its own public
# page + SEO fields, like Content, not like a catalog-internal grouping
# (Category/Brand). Deliberately its own key, not reused from CONTENT_MANAGE
# or STOREFRONT_LAYOUT_MANAGE (a Collection is a distinct authorization
# surface from either CMS pages or the homepage layout builder, even though
# in this phase the same CONTENT_EDITOR role happens to get all three).
COLLECTION_MANAGE = "collection.manage"

STAFF_MANAGE = "staff.manage"
DOMAIN_MANAGE = "domain.manage"  # reserved — no domain-management UI yet
SUBSCRIPTION_MANAGE = "subscription.manage"  # coarse legacy key — kept for back-compat
# Soft-deleting the whole Store is the single most destructive owner action.
# It gets its own granular key (rather than reusing SETTINGS_MANAGE) and is
# Owner-only via _OWNER_ONLY below — no view may hardcode an "if OWNER" check;
# they must gate on this canonical permission through ``user_has_permission``.
STORE_DELETE = "store.delete"

# Checkpoint 5A — SaaS subscription / usage visibility + plan change.
# SUBSCRIPTION_VIEW / USAGE_VIEW are read-only insight (billing status, quota
# consumption); SUBSCRIPTION_CHANGE is the billing-tier decision (upgrade/
# downgrade/cancel) and stays with the Owner only, like the other _OWNER_ONLY
# keys. Platform-level PLAN administration is never a merchant permission — it
# lives only in Django Admin behind superuser (see apps/subscriptions/admin.py).
SUBSCRIPTION_VIEW = "subscription.view"
SUBSCRIPTION_CHANGE = "subscription.change"
USAGE_VIEW = "usage.view"

# Checkpoint 5B — SaaS billing (invoices/payments/account/cancellation).
# BILLING_VIEW is read-only billing history; BILLING_ACCOUNT_MANAGE edits the
# billing account; BILLING_PAYMENT_MANAGE starts payments; SUBSCRIPTION_CANCEL
# is the cancellation decision and stays Owner-only. Platform billing admin is
# never a merchant permission — it lives only in Django Admin behind superuser.
BILLING_VIEW = "billing.view"
BILLING_ACCOUNT_MANAGE = "billing.account_manage"
BILLING_PAYMENT_MANAGE = "billing.payment_manage"
SUBSCRIPTION_CANCEL = "subscription.cancel"

# Back-compat aliases: the coarse Phase-1 keys these replace. Nothing in
# this codebase reads these anymore (all decorated views moved to the
# granular keys above in the same PR that added them), kept only so an
# external caller importing the old names does not hard-crash.
CATALOG = PRODUCT_VIEW
ORDERS = ORDER_VIEW
CUSTOMERS = CUSTOMER_VIEW
CONTENT = CONTENT_MANAGE
SETTINGS = SETTINGS_MANAGE
REPORTS = REPORTS_VIEW
MEMBERSHIP = STAFF_MANAGE

ALL_PERMISSIONS = frozenset({
    DASHBOARD_VIEW,
    PRODUCT_VIEW, PRODUCT_CREATE, PRODUCT_EDIT, PRODUCT_DELETE,
    CATEGORY_MANAGE, BRAND_MANAGE, ATTRIBUTE_MANAGE, VARIANT_MANAGE, INVENTORY_MANAGE, MEDIA_MANAGE,
    WAREHOUSE_VIEW, WAREHOUSE_MANAGE, TRANSFER_VIEW, TRANSFER_MANAGE, RESERVATION_VIEW,
    SHIPPING_SETTINGS_VIEW, SHIPPING_SETTINGS_MANAGE, TAX_SETTINGS_VIEW, TAX_SETTINGS_MANAGE,
    IMPORT_EXPORT_VIEW, IMPORT_EXPORT_MANAGE,
    CUSTOMER_NOTE_MANAGE, CUSTOMER_TAG_MANAGE, CUSTOMER_SEGMENT_VIEW, CUSTOMER_SEGMENT_MANAGE, CUSTOMER_EXPORT,
    ORDER_VIEW, ORDER_STATUS_CHANGE,
    CUSTOMER_VIEW, CUSTOMER_EDIT,
    REPORTS_VIEW, COUPON_VIEW, DISCOUNT_MANAGE,
    RETURN_VIEW, RETURN_MANAGE, REFUND_VIEW, REFUND_MANAGE,
    AUDIT_LOG_VIEW,
    SETTINGS_MANAGE, PAYMENT_SETTINGS_MANAGE, SMS_SETTINGS_MANAGE, CONTENT_MANAGE, STOREFRONT_LAYOUT_MANAGE,
    COLLECTION_MANAGE,
    STAFF_MANAGE, DOMAIN_MANAGE, SUBSCRIPTION_MANAGE, STORE_DELETE,
    SUBSCRIPTION_VIEW, SUBSCRIPTION_CHANGE, USAGE_VIEW,
    BILLING_VIEW, BILLING_ACCOUNT_MANAGE, BILLING_PAYMENT_MANAGE, SUBSCRIPTION_CANCEL,
})

_CATALOG_READ_WRITE = frozenset({
    PRODUCT_VIEW, PRODUCT_CREATE, PRODUCT_EDIT, PRODUCT_DELETE,
    CATEGORY_MANAGE, BRAND_MANAGE, ATTRIBUTE_MANAGE, VARIANT_MANAGE, INVENTORY_MANAGE, MEDIA_MANAGE,
    # Catalog Manager owns inventory infrastructure (checkpoint 3 §20 policy):
    # views + adjusts stock, manages warehouses/transfers/reservations.
    WAREHOUSE_VIEW, WAREHOUSE_MANAGE, TRANSFER_VIEW, TRANSFER_MANAGE, RESERVATION_VIEW,
    # Catalog Manager owns Product/Variant/Inventory import-export (checkpoint
    # 4 §25 policy) — Customer export is a separate, more sensitive permission
    # (CUSTOMER_EXPORT) that Catalog Manager does NOT get.
    IMPORT_EXPORT_VIEW, IMPORT_EXPORT_MANAGE,
})
# Order Manager owns Returns/Refunds financial authority (checkpoint 2 §15
# policy) — Catalog Manager deliberately does NOT get REFUND_MANAGE/RETURN_MANAGE.
# Order Manager views (not manages) warehouses/reservations/transfers since
# fulfillment visibility matters for order handling (checkpoint 3 policy).
# Order Manager DOES manage Shipping (checkpoint 3B §21 policy — shipping is
# an order-fulfillment concern) but only VIEWS Tax settings — Tax changes
# require Owner/Administrator since they affect every future order's totals.
_ORDER_READ_WRITE = frozenset({
    ORDER_VIEW, ORDER_STATUS_CHANGE, CUSTOMER_VIEW, CUSTOMER_EDIT,
    RETURN_VIEW, RETURN_MANAGE, REFUND_VIEW, REFUND_MANAGE,
    WAREHOUSE_VIEW, RESERVATION_VIEW, TRANSFER_VIEW,
    SHIPPING_SETTINGS_VIEW, SHIPPING_SETTINGS_MANAGE, TAX_SETTINGS_VIEW,
    # Order Manager owns the customer-relationship side of CRM (checkpoint 4
    # §25 policy): notes, tags, segments, and the sensitive Customer export —
    # but not the catalog-wide IMPORT_EXPORT_* permission, which is Catalog
    # Manager's domain.
    CUSTOMER_EXPORT, CUSTOMER_NOTE_MANAGE, CUSTOMER_TAG_MANAGE,
    CUSTOMER_SEGMENT_VIEW, CUSTOMER_SEGMENT_MANAGE,
})
_CONTENT_READ_WRITE = frozenset({CONTENT_MANAGE, MEDIA_MANAGE, STOREFRONT_LAYOUT_MANAGE, COLLECTION_MANAGE})
# Owner-only: staff/domain management and the billing-tier change decision.
# SUBSCRIPTION_VIEW/USAGE_VIEW are deliberately NOT here — Administrators (and,
# for usage, Analysts) may see billing status and quota consumption; only the
# Owner may actually change the plan tier.
_OWNER_ONLY = frozenset({
    STAFF_MANAGE, DOMAIN_MANAGE, SUBSCRIPTION_MANAGE, SUBSCRIPTION_CHANGE,
    # Cancelling the subscription is an Owner-only decision (checkpoint 5B).
    SUBSCRIPTION_CANCEL,
    # Soft-deleting the entire Store is the most destructive action — Owner-only.
    STORE_DELETE,
})

#: What each role may do. Deliberately explicit and centralized — no view
#: or template should hardcode a role name to decide what it can show, only
#: ``user_has_permission``. See the master reference doc §10.3 for the
#: target role list this mirrors.
ROLE_PERMISSIONS = {
    Role.OWNER: ALL_PERMISSIONS,
    Role.ADMINISTRATOR: ALL_PERMISSIONS - _OWNER_ONLY,
    Role.CATALOG_MANAGER: frozenset({DASHBOARD_VIEW, REPORTS_VIEW}) | _CATALOG_READ_WRITE,
    Role.ORDER_MANAGER: frozenset({DASHBOARD_VIEW, REPORTS_VIEW}) | _ORDER_READ_WRITE,
    Role.CONTENT_EDITOR: frozenset({DASHBOARD_VIEW}) | _CONTENT_READ_WRITE,
    Role.ANALYST: frozenset({
        DASHBOARD_VIEW, REPORTS_VIEW, PRODUCT_VIEW, ORDER_VIEW, CUSTOMER_VIEW,
        COUPON_VIEW, RETURN_VIEW, REFUND_VIEW, AUDIT_LOG_VIEW,
        WAREHOUSE_VIEW, RESERVATION_VIEW, TRANSFER_VIEW, SHIPPING_SETTINGS_VIEW, TAX_SETTINGS_VIEW,
        # Read-only exports and segment viewing (checkpoint 4 §25 policy) —
        # no IMPORT_EXPORT_MANAGE (cannot trigger imports), no CUSTOMER_EXPORT
        # (PII export stays with Order Manager/Owner/Administrator).
        IMPORT_EXPORT_VIEW, CUSTOMER_SEGMENT_VIEW,
        # Usage consumption is operational reporting insight (checkpoint 5A) —
        # Analyst sees quota usage but not billing status or plan change.
        USAGE_VIEW,
        # Read-only billing history (checkpoint 5B) — no payment/account/cancel.
        BILLING_VIEW,
    }),
}


def get_active_membership(user, store):
    """The user's ACTIVE ``StoreMembership`` for ``store``, or ``None``.

    Returns ``None`` for an unauthenticated user, a ``None`` store, a
    membership in a *different* Store, or a membership whose status is
    ``INVITED``/``REVOKED`` — an inactive/rejected/expired membership must
    never grant access. Exactly one row can ever match, since
    ``StoreMembership`` enforces ``uniq_membership_per_store_user``.
    """
    if store is None or user is None or not getattr(user, "is_authenticated", False):
        return None
    return StoreMembership.objects.filter(
        store=store, user=user, status=StoreMembership.MembershipStatus.ACTIVE
    ).first()


def user_can_access_dashboard(user, store):
    """Whether ``user`` may open ``store``'s merchant dashboard at all.

    Any active membership, regardless of role, grants baseline access — an
    ``ANALYST`` may sign in and see report pages, for instance. Fine-grained
    per-action gating is ``user_has_permission``.
    """
    return get_active_membership(user, store) is not None


def membership_has_permission(membership, permission):
    """Whether an already-looked-up ``membership`` (may be ``None``) grants
    ``permission``. Avoids a second query when a caller (the ``staff_required``
    decorator) already resolved the membership once for this request."""
    if membership is None:
        return False
    return permission in ROLE_PERMISSIONS.get(membership.role, frozenset())


def user_has_permission(user, store, permission):
    """Whether ``user``'s active membership in ``store`` grants ``permission``.

    ``permission`` must be one of the module-level constants above.
    """
    return membership_has_permission(get_active_membership(user, store), permission)
