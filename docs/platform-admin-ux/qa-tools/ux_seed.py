"""QA-ONLY seed (scratch DB): realistic owner-panel data so every page renders with content. Synthetic values."""
import json, re
from datetime import timedelta
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.test import Client
from apps.billing.models import SubscriptionInvoice
from apps.catalog.models import IndustryTemplate, StoreIndustryInstallation
from apps.portal.models import PlatformInternalNote
from apps.sms.models import SmsBalance, SmsLog, SmsPackage
from apps.stores.models import Store, StoreDomain, StoreMembership
from apps.stores.services.platform_code_service import generate_unique_platform_code
from apps.subscriptions.models import Plan, PlanVersion, StoreSubscription
from apps.subscriptions.services import subscription_service as sub_svc
U = get_user_model()
owner = U.objects.filter(is_superuser=True).first()
ultra_v = PlanVersion.objects.filter(plan__code="ultra", status="published").order_by("-version_number").first()
base_v = PlanVersion.objects.filter(plan__code="base", status="published").order_by("-version_number").first()
stores = []
for i, (name, ver) in enumerate([("فروشگاه نمونه‌ی آرایشی", ultra_v), ("پوشاک آفتاب", base_v), ("Digital Kala | دیجی‌کالای نمونه", base_v)], 1):
    if Store.objects.filter(slug=f"qa-store-{i}").exists(): stores.append(Store.objects.get(slug=f"qa-store-{i}")); continue
    s = Store.objects.create(name=name, slug=f"qa-store-{i}", admin_subdomain=f"qa{i}", status=Store.Status.ACTIVE, platform_code=generate_unique_platform_code())
    u = U.objects.create_user(username=f"owner{i}@example.com", email=f"owner{i}@example.com", password="qa-pass-12345", first_name="مالک", last_name=f"شماره {i}")
    StoreMembership.objects.create(store=s, user=u, role=StoreMembership.Role.OWNER, status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now())
    sub = sub_svc.create_subscription(s, ver)
    sub_svc.activate_subscription(sub, period_end=timezone.now() + timedelta(days=20 + i))
    stores.append(s)
s0 = stores[0]
sub0 = StoreSubscription.objects.filter(store=s0, is_current=True).first()
inv = SubscriptionInvoice.objects.filter(store=s0).first() or SubscriptionInvoice.objects.create(
    store=s0, subscription=sub0, plan_version=ultra_v, kind=SubscriptionInvoice.Kind.INITIAL, number="INV-QA-0001", currency="IRT",
    subtotal=1490000, tax_total=0, grand_total=1490000, amount_paid=0, amount_due=1490000, status=SubscriptionInvoice.Status.OPEN)
if not SmsPackage.objects.exists():
    SmsPackage.objects.create(name="بسته‌ی ۵۰۰ پیامکی", credit_amount=500, price=90000)
    SmsPackage.objects.create(name="بسته‌ی ۵۰۰۰ پیامکی", credit_amount=5000, price=800000)
pkg = SmsPackage.objects.first()
from apps.sms.services.balance_service import get_or_create_balance
b = get_or_create_balance(store=s0)
for st in ("sent", "failed"):
    SmsLog.objects.create(store=s0, event_key="otp", recipient="09121234567", message="x", status=st)
dom = StoreDomain.objects.filter(store=s0, hostname="shop.example.com").first() or StoreDomain.objects.create(
    store=s0, hostname="shop.example.com", domain_type=StoreDomain.DomainType.CUSTOM_DOMAIN,
    verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now())
tpl = IndustryTemplate.objects.first() or IndustryTemplate.objects.create(slug="fashion", name="پوشاک", version=1, readiness=IndustryTemplate.Readiness.PRODUCTION_READY)
StoreIndustryInstallation.objects.get_or_create(store=s0, industry_template=tpl, defaults={"installed_version": 1})
PlatformInternalNote.objects.get_or_create(about_user=owner, author=owner, body="یادداشت نمونه")
c = Client(); c.force_login(owner)
import importlib
urls = importlib.import_module("apps.portal.platform_admin_urls")
from apps.subscriptions.models import PricingFeature
def first_event_key():
    try:
        from apps.notifications import registry
        evs = getattr(registry, "EVENTS", None) or getattr(registry, "REGISTRY", None)
        return next(iter(evs))
    except Exception: return "platform_welcome"
try:
    from apps.sms.services import template_service as _t
except Exception: _t = None
vals = {"store_public_id": str(s0.public_id), "user_id": owner.pk, "plan_id": Plan.objects.get(code="ultra").pk,
        "version_id": ultra_v.pk, "subscription_id": sub0.pk, "invoice_id": inv.pk, "template_id": tpl.pk, "domain_id": dom.pk,
        "package_id": pkg.pk, "feature_id": PricingFeature.objects.get(key="ai_assistant").pk, "pk": 1, "event_key": "", "slot": "", "slug": ""}
json.dump({"vals": vals}, open("/tmp/rs_reg/ux_vals.json", "w"))
print("seed ok", len(stores), inv.pk)
