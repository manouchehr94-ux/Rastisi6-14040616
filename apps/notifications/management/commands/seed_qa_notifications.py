"""QA fixture for the Windows/local acceptance run. Idempotent; refuses to run outside QA mode (see ``apps.notifications.qa``).

Creates (and prints the logins for) a platform owner, a limited platform-team member, and four tenants:

* A  ``qa-no-domain``  — no custom domain               -> sender INACTIVE (scenario E)
* B  ``qa-pending``    — custom domain, DNS not verified -> sender PENDING with DNS records (scenario F)
* C  ``qa-bike``       — ``mybikestore.test`` verified   -> sender ACTIVE ``info@mybikestore.test``, products, checkout (G, H, L)
* D  ``qa-other``      — second tenant, own verified domain + a marked email override (isolation, scenario K)
"""

from __future__ import annotations

import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.catalog.models import Category, Product, Vendor
from apps.core.models import ShopSettings
from apps.customers.models import Customer
from apps.notifications.mail import provisioning_service as svc
from apps.notifications.mail.fake import FakeTransport
from apps.notifications.qa import require_qa
from apps.notifications.services import template_service as ts
from apps.orders.models import PaymentGateway, PaymentGatewayConfig, ShippingMethod
from apps.stores.models import Store, StoreDomain, StoreMembership

User = get_user_model()
MARKER_D = "QA-OVERRIDE-TENANT-D"

PLATFORM_OWNER = ("qa-platform@rastisi.test", "09120000001")
LIMITED_MEMBER = ("qa-catalog-only@rastisi.test", "09120000002")
STORES = (
    # slug, name, admin_subdomain, owner phone, custom domain, verified at provider?
    ("qa-no-domain", "فروشگاه الف (بدون دامنه)", "qa-a", "09121110001", "", False),
    ("qa-pending", "فروشگاه ب (دامنه در انتظار DNS)", "qa-b", "09121110002", "pendingstore.test", False),
    ("qa-bike", "فروشگاه دوچرخه (فعال)", "qa-bike", "09121110003", "mybikestore.test", True),
    ("qa-other", "فروشگاه دیگر (مستأجر دوم)", "qa-other", "09121110004", "otherstore.test", True),
)


class Command(BaseCommand):
    help = "QA only: seed platform users + four tenants in the states needed for the notification acceptance scenarios."

    def add_arguments(self, parser):
        parser.add_argument("--password", required=True, help="throw-away password for every QA account")
        parser.add_argument("--port", default="8765")
        parser.add_argument("--json", default="", help="write the machine-readable QA info (URLs, logins) to this path")

    @transaction.atomic
    def handle(self, *args, **o):
        require_qa()
        pw, port = o["password"], o["port"]

        owner = self._user(PLATFORM_OWNER, pw, is_staff=True, is_superuser=True)
        limited = self._user(LIMITED_MEMBER, pw, is_staff=True)
        limited.user_permissions.set(Permission.objects.filter(
            content_type__app_label="notifications", codename="view_notification_catalog"))

        info = {"port": port, "platform_admin_url": f"http://platformadmins.rastisi.localhost:{port}/",
                "login_url": f"http://rastisi.localhost:{port}/login/", "password": pw,
                "platform_owner": PLATFORM_OWNER[0], "platform_limited_member": LIMITED_MEMBER[0], "stores": []}

        for slug, name, sub, phone, domain, verified in STORES:
            store, _ = Store.objects.get_or_create(slug=slug, defaults={"name": name, "status": Store.Status.ACTIVE})
            store.name, store.admin_subdomain = name, sub
            store.save(update_fields=["name", "admin_subdomain"])
            ShopSettings.provision_for(store)
            user = self._user((f"{slug}-owner@rastisi.test", phone), pw, is_staff=True)
            StoreMembership.objects.get_or_create(
                store=store, user=user, defaults={"role": StoreMembership.Role.OWNER, "accepted_at": timezone.now(),
                                                  "status": StoreMembership.MembershipStatus.ACTIVE})
            if domain:
                StoreDomain.objects.get_or_create(store=store, hostname=domain, defaults={
                    "domain_type": StoreDomain.DomainType.CUSTOM_DOMAIN,
                    "verification_status": StoreDomain.VerificationStatus.UNVERIFIED})
            identity = svc.sync_sender_identity(store)
            if verified and identity.status != "active":
                FakeTransport.verify(domain)
                identity = svc.sync_sender_identity(store)
            info["stores"].append({
                "slug": slug, "name": name, "owner_login": phone, "owner_email": f"{slug}-owner@rastisi.test",
                "domain": domain, "sender_status": identity.status, "sender_address": identity.from_address,
                "store_admin_url": f"http://{sub}.rastisi.localhost:{port}/admin-portal/",
                "storefront_hint": "—" if not domain else f"(custom domain {domain} is not resolvable locally)",
            })

        self._commerce(Store.objects.get(slug="qa-bike"))
        d = Store.objects.get(slug="qa-other")
        ts.save_template(d, "order.created", "email", enabled=True, subject=f"{MARKER_D} موضوع",
                         body=f"{MARKER_D} سفارش {{order_number}} ثبت شد.", actor=None)

        if o["json"]:
            with open(o["json"], "w", encoding="utf-8") as fh:
                json.dump(info, fh, ensure_ascii=False, indent=1)
            self.stdout.write(f"seeded {len(info['stores'])} stores; details written to the QA info file")
        else:
            self.stdout.write(json.dumps(info, ensure_ascii=False, indent=1))

    def _user(self, ident, pw, **flags):
        email, phone = ident
        user, _ = User.objects.get_or_create(username=phone, defaults={"email": email})
        user.email = email
        for k, v in flags.items():
            setattr(user, k, v)
        user.is_active = True
        user.set_password(pw)
        user.save()
        return user

    def _commerce(self, store):
        """Just enough catalog + COD + shipping for a checkout / `qa_place_order` on the active tenant."""
        vendor, _ = Vendor.objects.get_or_create(store=store, slug="qa-vendor", defaults={"name": "فروشنده‌ی QA"})
        cat, _ = Category.objects.get_or_create(store=store, slug="qa-bikes", defaults={"name": "دوچرخه"})
        Product.objects.get_or_create(store=store, slug="qa-bike-1", defaults={
            "vendor": vendor, "category": cat, "name": "دوچرخه‌ی QA", "sku": "QA-BIKE-1", "price": Decimal("5000000"), "stock": 50})
        ShippingMethod.objects.get_or_create(store=store, slug="qa-post", defaults={"name": "پست", "cost": Decimal("0")})
        PaymentGateway.objects.get_or_create(store=store, slug="qa-cod", defaults={"name": "پرداخت در محل"})
        PaymentGatewayConfig.objects.get_or_create(store=store, gateway_code=PaymentGatewayConfig.GatewayCode.COD,
                                                   defaults={"is_active": True})
        shop = ShopSettings.load(store=store)
        shop.tax_percent, shop.free_shipping_threshold = Decimal("0"), Decimal("99999999999")
        shop.save()
        user, _ = User.objects.get_or_create(username="09125550001", defaults={"email": "buyer@example.com"})
        user.set_password("x")  # customer logs in via OTP in real life; QA never needs this password
        user.save()
        Customer.objects.get_or_create(user=user, defaults={
            "full_name": "مشتری QA", "phone": "09125550001", "email": "buyer@example.com",
            "accepts_promotional_email": True, "accepts_promotional_sms": True})
