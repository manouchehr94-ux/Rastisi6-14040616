"""Seed a DISPOSABLE database for the Trial → purchase browser acceptance (synthetic data only; no real gateway/SMS/e-mail)."""
import json, os, sys
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "shop_core.settings")
sys.path.insert(0, os.environ.get("REPO", os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
import django
django.setup()
from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import timezone
from apps.core.models import ShopSettings
from apps.portal.models import OwnerProfile
from apps.portal.services import platform_gateway_service as pgs
from apps.portal.services.platform_config_service import update_platform_configuration
from apps.stores.models import Store, StoreMembership
from apps.subscriptions.services import plan_service as ps, subscription_service as ss, trial_service
from apps.subscriptions.tests.test_pricing_dynamic import make_plan
User = get_user_model()
out = {"sessions": {}}
update_platform_configuration(actor=None, step_up_actions={"subscription_purchase_confirm": False})
trial_service.ensure_trial_plan()
for code, monthly, order, rec in (("e2e-pro", 1_000_000, 2, True), ("e2e-lite", 200_000, 1, False)):
    plan, draft = make_plan(code, base=monthly, order=order, publish=False, recommended=rec)
    ps.set_formula_pricing(draft, monthly_price=monthly, discounts={"quarterly": 5, "semiannual": 10, "yearly": 15})
    ps.publish_plan_version(draft)
# a LEGACY store (grandfathered, unlimited plan) — must keep working untouched
from apps.subscriptions.models import Plan
legacy_v = Plan.objects.get(code="legacy").versions.filter(status="published").order_by("-version_number").first()    # created by the legacy migration
old = Store.objects.create(name="فروشگاه قدیمی", slug="oldshop", admin_subdomain="oldshop", status=Store.Status.ACTIVE)
ShopSettings.provision_for(old)
old_owner = User.objects.create_user(username="09120007001", password="e2e-pass-12345", is_staff=True)
OwnerProfile.objects.create(user=old_owner, phone="09120007001", full_name="مالک قدیمی")
StoreMembership.objects.create(store=old, user=old_owner, role=StoreMembership.Role.OWNER, status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now())
ss.activate_subscription(ss.create_subscription(old, legacy_v, actor=old_owner), actor=old_owner)
c = Client(); c.force_login(old_owner); out["sessions"]["legacy_owner"] = c.cookies["sessionid"].value
fin = User.objects.create_user(username="trial-staff@example.com", password="e2e-pass-12345", is_staff=True, is_superuser=True)
c = Client(); c.force_login(fin); out["sessions"]["staff"] = c.cookies["sessionid"].value
pgs.save_gateway("zibal", credentials={"merchant": "E2E-DUMMY-MERCHANT"}, sandbox=False, enabled=True); pgs.set_default("zibal")
json.dump(out, open(os.environ.get("SEED_OUT", "/tmp/trial_e2e_seed.json"), "w"), ensure_ascii=False)
print("seeded")
