"""Task 8 QA helper (dev-only, not part of the app): publish a given mobile
bottom-nav variant on the QA demo store so browser QA can exercise every
registered presentation. Reuses the canonical layout draft->publish path.

Usage: python manage.py shell -c "exec(open('tools/storefront_builder_qa/_publish_nav.py').read())"  with NAV env,
or invoked via the orchestrator which sets NAV.
"""
import copy
import os

from apps.stores.models import Store
from apps.storefront_builder.services import layout_service
from apps.storefront_builder.storefront_appearance.persistence import STORE_APPEARANCE_CONFIG_KEY as K

nav = os.environ["NAV"]  # e.g. "bottom_nav.five_item.v1" or "bottom_nav.hidden.v1"
store = Store.objects.get(slug="rastisi-fashion-test")
draft = layout_service.get_or_create_draft(store)
cfg = copy.deepcopy(dict(draft.appearance_config or {}))
man = dict(cfg.get(K) or {})
sel = dict(man.get("selections") or {})
sel["bottom_nav"] = nav
man["selections"] = sel
cfg[K] = man
draft.appearance_config = cfg
draft.save(update_fields=["appearance_config"])
layout_service.publish(store)
print(f"PUBLISHED bottom_nav={nav}")
