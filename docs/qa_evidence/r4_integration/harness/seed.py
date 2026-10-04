"""Deterministic, isolated fixture bootstrap for qa_storefront_builder_r4 (not committed).
Creates only the Store/user/membership the project's own command requires; the command itself seeds
sections, products, brands, hero slides and media (phase3)."""
import os, sys
sys.path.insert(0, os.getcwd()); os.environ.setdefault("DJANGO_SETTINGS_MODULE", "shop_core.settings")
import django; django.setup()
from django.contrib.auth import get_user_model
from django.utils import timezone
from apps.core.models import ShopSettings
from apps.stores.models import Store, StoreMembership
store = Store.objects.get(slug="akhlaghi")  # migration-seeded; the 127.0.0.1 compat fallback only resolves this sole Store
assert Store.objects.count() == 1 and store.status == Store.Status.ACTIVE
if not ShopSettings.objects.filter(store=store).exists():
    ShopSettings.provision_for(store)
u = get_user_model().objects.create_user(username="r4owner", password="x12345678", is_staff=True)
StoreMembership.objects.create(store=store, user=u, role="owner", status="active", accepted_at=timezone.now())
print("seeded", store.pk, u.pk)
