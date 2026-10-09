#!/usr/bin/env python
"""Runtime, computed-style contrast audit for the whole RastiSi web product.

What it does for every surface (page) it visits:

  1. REST      – every visible text node / form value / placeholder is measured
                 against its *effective* background (paint stack at the text's
                 real position: ancestors, overlays, images, gradients).
  2. HOVER     – each distinct interactive component is hovered and its subtree
                 re-measured (background AND foreground at the SAME state).
  3. ACTIVE    – pointer pressed (not released over the control).
  4. FOCUS     – real Tab traversal; subtree contrast re-measured and the focus
                 indicator itself must be perceivable (>= 3:1).
  5. TOGGLES   – tabs / switches / disclosure / checkbox / radio / popup
                 triggers are activated and the WHOLE page is re-measured.
  6. ACTIONS   – per-surface scripted states (e.g. submit an empty form to
                 trigger validation errors).

All colour maths lives in apps/core/color_utils.py (shared with the product).
Thresholds: WCAG 2.2 AA – 4.5:1 text, 3:1 large text / UI boundaries; disabled
text is held to 3:1 by product rule.

Typical use (dev server already running, see README.md):

    python tools/contrast_audit/run_audit.py --suite all --out /tmp/audit.json
    python tools/contrast_audit/run_audit.py --suite storefront-templates

Exit status is non-zero when any hard failure remains.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, REPO_ROOT)

import audit_lib  # noqa: E402

PROBE_JS = open(os.path.join(HERE, "probe.js"), encoding="utf-8").read()
CHROMIUM_CANDIDATES = (
    "/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
    "/opt/pw-browsers/chromium",
)
VIEWPORTS = {"1366x768": (1366, 768, False), "1440x900": (1440, 900, False), "390": (390, 844, True)}

DEFAULT_PORT = "8765"
PLATFORM_HOST = "rastisi.localhost"
PADMIN_HOST = "platformadmins.rastisi.localhost"
DEFAULT_STORE_HOST = "rastisi-fashion-test.rastisi.localhost"


# ---------------------------------------------------------------------------
# results aggregation
# ---------------------------------------------------------------------------
DUMP = {"needle": ""}


class Results:
    def __init__(self):
        self.failures = {}          # key -> record
        self.checked = set()        # unique (sel, fg, bg, state class)
        self.raw_items = 0
        self.pages = []
        self.states = defaultdict(int)
        self.focus_checked = set()
        self.focus_failures = {}
        self.errors = []
        self.categories = defaultdict(int)
        self.templates = defaultdict(lambda: {"measured": 0, "failing": 0, "worst": 99.0, "worst_text": ""})

    def add_items(self, surface, state, items):
        state_class = state.split(":")[0]
        for item in items:
            verdict = audit_lib.evaluate_item(item)
            if verdict is None:
                continue
            self.raw_items += 1
            if DUMP["needle"] and DUMP["needle"] in item["sel"]:
                print(f"    dump {surface['name']} [{state}] {item['sel']} {item['text']!r} "
                      f"{verdict.fg_hex} on {verdict.bg_hex} = {verdict.ratio:.2f} ({'ok' if verdict.passed else 'FAIL'})")
            self.states[state_class] += 1
            ck = (item["sel"], verdict.fg_hex, verdict.bg_hex, state_class)
            self.checked.add(ck)
            self.categories[verdict.category] += 1
            tpl = surface.get("template")
            if tpl:
                rec_t = self.templates[tpl]
                rec_t["measured"] += 1
                if not verdict.passed:
                    rec_t["failing"] += 1
                    if verdict.ratio < rec_t["worst"]:
                        rec_t["worst"], rec_t["worst_text"] = round(verdict.ratio, 2), f"{item['sel']} {item['text'][:24]!r} {verdict.fg_hex} on {verdict.bg_hex}"
            if verdict.passed:
                continue
            key = (surface["name"] if surface.get("group_by_surface") else surface["suite"],
                   item["sel"], verdict.fg_hex, verdict.bg_hex, state_class, verdict.category)
            rec = self.failures.get(key)
            if rec is None:
                rec = self.failures[key] = {
                    "suite": surface["suite"], "surfaces": set(), "sel": item["sel"], "path": item["path"],
                    "text": item["text"], "fg": verdict.fg_hex, "bg": verdict.bg_hex,
                    "ratio": round(verdict.ratio, 2), "threshold": verdict.threshold,
                    "state": state, "state_class": state_class, "category": verdict.category,
                    "kind": verdict.kind, "flags": verdict.flags, "size": item["size"], "weight": item["weight"],
                    "count": 0,
                }
            rec["count"] += 1
            rec["surfaces"].add(surface["name"])
            if verdict.ratio < rec["ratio"]:
                rec["ratio"] = round(verdict.ratio, 2)

    def add_focus(self, surface, facts):
        focused, rest = facts["focused"], facts["rest"]
        key = (surface["suite"], focused["sel"])
        self.focus_checked.add(key)
        passed, detail = audit_lib.evaluate_focus(focused, rest)
        if not passed and key not in self.focus_failures:
            self.focus_failures[key] = {"suite": surface["suite"], "sel": focused["sel"], "path": focused["path"],
                                        "text": focused["text"], "detail": detail, "surfaces": {surface["name"]}}
        elif not passed:
            self.focus_failures[key]["surfaces"].add(surface["name"])

    def summary(self):
        hard = [f for f in self.failures.values()]
        return {
            "pages_audited": len(self.pages),
            "raw_text_measurements": self.raw_items,
            "unique_checks": len(self.checked),
            "by_state_class": dict(self.states),
            "by_background_kind": dict(self.categories),
            "distinct_failures": len(hard),
            "failing_measurements": sum(f["count"] for f in hard),
            "focus_components_checked": len(self.focus_checked),
            "focus_indicator_failures": len(self.focus_failures),
            "errors": len(self.errors),
            **({"templates_audited": len(self.templates),
                "templates_passing": sum(1 for t in self.templates.values() if not t["failing"])} if self.templates else {}),
        }

    def to_json(self):
        def clean(rec):
            rec = dict(rec)
            rec["surfaces"] = sorted(rec["surfaces"])
            return rec

        return {
            "summary": self.summary(),
            "pages": self.pages,
            "failures": sorted((clean(f) for f in self.failures.values()), key=lambda r: (r["ratio"] - r["threshold"])),
            "focus_failures": [clean(f) for f in self.focus_failures.values()],
            "templates": dict(self.templates),
            "errors": self.errors,
        }


# ---------------------------------------------------------------------------
# page driving
# ---------------------------------------------------------------------------
def settle(page, ms=250):
    page.wait_for_timeout(ms)
    page.evaluate("window.__contrastProbe && window.__contrastProbe.settle()")


def measure(page, results, surface, state, root=None):
    try:
        data = page.evaluate("([root]) => window.__contrastProbe.collect(root)", [root])
    except Exception as exc:  # noqa: BLE001
        results.errors.append(f"{surface['name']} [{state}] measure: {str(exc).splitlines()[0][:160]}")
        return 0
    results.add_items(surface, state, data["items"])
    return len(data["items"])


def sweep_hover_active(page, results, surface, max_targets):
    targets = page.evaluate("() => window.__contrastProbe.interactiveTargets(2)")
    for target in targets[:max_targets]:
        idx = target["idx"]
        try:
            rect = page.evaluate("(i) => window.__contrastProbe.targetRect(i)", idx)
            if not rect or not rect["reachable"]:
                continue
            page.mouse.move(rect["x"], rect["y"])
            settle(page, 60)
            measure(page, results, surface, f"hover:{target['sig']}", idx)
            if target["disabled"] or target["tag"] in ("select", "textarea") or target["type"] in (
                    "text", "email", "password", "tel", "number", "search", "url", "file"):
                continue
            page.mouse.down()
            settle(page, 60)
            measure(page, results, surface, f"active:{target['sig']}", idx)
            page.mouse.move(2, 2)
            page.mouse.up()
        except Exception as exc:  # noqa: BLE001
            results.errors.append(f"{surface['name']} hover {target['sig']}: {str(exc).splitlines()[0][:140]}")
    try:
        page.mouse.move(2, 2)
    except Exception:  # noqa: BLE001
        pass
    return targets


def sweep_focus(page, results, surface, max_stops=120):
    per_sig = defaultdict(int)
    try:
        page.evaluate("window.scrollTo(0,0)")
        page.keyboard.press("Home")
    except Exception:  # noqa: BLE001
        pass
    page.evaluate("document.activeElement && document.activeElement.blur()")
    for _ in range(max_stops):
        page.keyboard.press("Tab")
        try:
            facts = page.evaluate("window.__contrastProbe.focusPair()")
        except Exception as exc:  # noqa: BLE001
            results.errors.append(f"{surface['name']} focus: {str(exc).splitlines()[0][:140]}")
            break
        if not facts:
            break
        sig = facts["focused"]["sel"]
        per_sig[sig] += 1
        if per_sig[sig] > 2:
            continue
        results.add_focus(surface, facts)
        measure(page, results, surface, f"focus:{sig}", "focus")


def sweep_toggles(page, results, surface, targets, max_toggles):
    url = page.url
    candidates = []
    seen = set()
    for t in targets:
        togglish = (t["role"] in ("tab", "switch", "checkbox", "radio", "menuitemcheckbox")
                    or t["tag"] == "summary" or t["type"] in ("checkbox", "radio")
                    or t.get("toggle"))
        if not togglish or t["disabled"] or t["sig"] in seen:
            continue
        if t["tag"] == "a" and t["href"] and not t["href"].startswith("#"):
            continue
        seen.add(t["sig"])
        candidates.append(t)
    for t in candidates[:max_toggles]:
        try:
            page.goto(url, wait_until="load", timeout=30000)
            page.evaluate("() => window.__contrastProbe.interactiveTargets(2)")
            rect = page.evaluate("(i) => window.__contrastProbe.targetRect(i)", t["idx"])
            if not rect or not rect["reachable"]:
                continue
            page.mouse.click(rect["x"], rect["y"])
            settle(page, 300)
            page.mouse.move(2, 2)
            measure(page, results, surface, f"toggle:{t['sig']}")
        except Exception as exc:  # noqa: BLE001
            results.errors.append(f"{surface['name']} toggle {t['sig']}: {str(exc).splitlines()[0][:140]}")


def sweep_openers(page, results, surface, targets, max_openers):
    """Open dialogs / drawers / quick-views / popovers and re-measure the whole page with them open."""
    url = page.url
    seen, candidates = set(), []
    for t in targets:
        if not t.get("opener") or t["disabled"] or t["sig"] in seen:
            continue
        seen.add(t["sig"])
        candidates.append(t)
    for t in candidates[:max_openers]:
        try:
            page.goto(url, wait_until="load", timeout=30000)
            page.evaluate("() => window.__contrastProbe.interactiveTargets(2)")
            rect = page.evaluate("(i) => window.__contrastProbe.targetRect(i)", t["idx"])
            if not rect or not rect["reachable"]:
                continue
            page.mouse.click(rect["x"], rect["y"])
            settle(page, 700)
            page.mouse.move(2, 2)
            measure(page, results, surface, f"open:{t['sig']}")
            page.keyboard.press("Escape")
        except Exception as exc:  # noqa: BLE001
            results.errors.append(f"{surface['name']} open {t['sig']}: {str(exc).splitlines()[0][:140]}")


ACTIONS_JS = {
    # submit the first visible form with an empty required field to surface validation / error UI
    "submit_empty_form": """() => {
        const forms = Array.from(document.forms).filter(f => f.offsetParent !== null && f.querySelector('input:not([type=hidden]), select, textarea'));
        for (const f of forms) {
            const btn = f.querySelector('button[type=submit], input[type=submit], button:not([type])');
            if (btn) { f.noValidate = true; btn.click(); return true; }
        }
        return false;
    }""",
}


def run_action(page, name):
    if name in ACTIONS_JS:
        page.evaluate(ACTIONS_JS[name])
        try:
            page.wait_for_load_state("load", timeout=8000)
        except Exception:  # noqa: BLE001
            pass
        settle(page, 300)


_ORM = ThreadPoolExecutor(max_workers=1)


def _apply_template(key):
    """Apply a Ready Template to the demo store's draft and publish it — the exact controlled
    path ``capture_ready_template_previews`` uses (Django ORM work runs on its own thread because the
    Playwright sync API owns an event loop on the main thread)."""
    from django.core.cache import cache

    from apps.storefront_builder import layout_preset_registry as lpr
    from apps.storefront_builder.services import layout_service, preset_service
    from apps.stores.models import Store

    cache.clear()  # the publish rate limiter (20/h) is process-local here; this audit is a dev tool
    store = Store.objects.get(slug="rastisi-fashion-test")
    preset = lpr.get_layout_preset(key) if hasattr(lpr, "get_layout_preset") else None
    if preset is None:
        preset = next(t for t in lpr.list_ready_templates() if t.key == key)
    layout = layout_service.get_or_create_layout(store)
    if layout.published_version_id and not layout.draft_version_id:
        if layout.published_version.effective_appearance_config().get("layout_preset_key") == key:
            return
    draft = layout_service.get_or_create_draft(store)
    preset_service.apply_preset(draft, preset)
    layout_service.publish(store)


def apply_template(key, attempts=6):
    """Publish a template to the demo store, retrying transient SQLite "database is locked" errors
    (a dev DB shared with the running dev server)."""
    for attempt in range(attempts):
        try:
            return _ORM.submit(_apply_template, key).result()
        except Exception as exc:  # noqa: BLE001
            if "locked" not in str(exc).lower() or attempt == attempts - 1:
                raise
            time.sleep(2 + attempt * 2)


def audit_surface(contexts, results, surface, args):
    # anonymous surfaces (public site, auth pages, public storefront) must NOT carry the owner's session —
    # a logged-in visitor is redirected away from /login/ and sees different chrome.
    context = contexts["anon"] if surface.get("auth") == "anon" else contexts["session"]
    if surface.get("apply_template"):
        apply_template(surface["apply_template"])
    page = context.new_page()
    name = surface["name"]
    url = surface["url"]
    try:
        resp = page.goto(url, wait_until="load", timeout=45000)
        settle(page, 400)
        status = resp.status if resp else 0
        if status >= 400 and not surface.get("allow_error"):
            results.errors.append(f"{name}: HTTP {status} for {url}")
            return
        if surface.get("auth") != "anon" and any(h in page.url for h in ("/login/?admin_return", "/login/?next=")):
            results.errors.append(f"{name}: redirected to login ({page.url})")
            return
        facts = page.evaluate("window.__contrastProbe.pageFacts()")
        results.pages.append({"name": name, "suite": surface["suite"], "url": page.url,
                              "viewport": args.viewport, "overflow_x": facts["overflowX"]})
        measure(page, results, surface, "rest")
        for action in surface.get("actions", ()):
            run_action(page, action)
            measure(page, results, surface, f"action:{action}")
            page.goto(url, wait_until="load", timeout=45000)
            settle(page, 300)
        if not (args.rest_only or surface.get("rest_only")):
            targets = sweep_hover_active(page, results, surface, args.max_targets)
            page.evaluate("window.scrollTo(0,0)")
            sweep_focus(page, results, surface)
            if not surface.get("no_toggles"):
                page.goto(url, wait_until="load", timeout=45000)
                settle(page, 300)
                targets = page.evaluate("() => window.__contrastProbe.interactiveTargets(2)")
                sweep_toggles(page, results, surface, targets, args.max_toggles)
                sweep_openers(page, results, surface, targets, args.max_toggles)
    except Exception as exc:  # noqa: BLE001
        results.errors.append(f"{name}: {str(exc).splitlines()[0][:200]}")
    finally:
        page.close()


# ---------------------------------------------------------------------------
# environment: sessions, surfaces
# ---------------------------------------------------------------------------
def django_setup():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "shop_core.settings")
    import django

    django.setup()


def make_sessions(owner_username):
    """Server-side session cookies for the owner (portal + store admin) and a platform admin."""
    from django.contrib.auth import get_user_model
    from django.test import Client

    user = get_user_model().objects.get(username=owner_username)
    client = Client()
    client.force_login(user)
    return client.cookies["sessionid"].value


def discover_ids():
    from apps.stores.models import Store

    onboarding = Store.objects.filter(onboarding_completed_at__isnull=True).order_by("-pk").first()
    from apps.catalog.models import Product

    store = Store.objects.filter(slug="rastisi-fashion-test").first()
    product = Product.objects.filter(store=store).order_by("pk").first() if store else None
    return {"product_slug": product.slug if product else None, "onboarding_store": str(onboarding.public_id) if onboarding else None,
            "any_store": str((Store.objects.filter(onboarding_completed_at__isnull=False).exclude(slug="akhlaghi").order_by("pk").first() or Store.objects.order_by("pk").first()).public_id)}


def build_surfaces(suite, ids, port, store_host):
    P = f"http://{PLATFORM_HOST}:{port}"
    S = f"http://{store_host}:{port}"
    A = f"http://{PADMIN_HOST}:{port}"
    out = []

    def add(s, name, base, path, **kw):
        out.append({"suite": s, "name": f"{s}:{name}", "url": base + path, "host": base, **kw})

    public = [("home", "/"), ("features", "/features/"), ("design", "/design/"), ("about", "/about/"),
              ("industries", "/supported-industries/"), ("plans", "/plans/"), ("help", "/help/"),
              ("contact", "/contact/"), ("terms", "/terms/"), ("privacy", "/privacy/")]
    auth = [("register", "/register/", ("submit_empty_form",)), ("login", "/login/", ("submit_empty_form",)),
            ("register-email", "/register-email/", ("submit_empty_form",)),
            ("login-email", "/login-email/", ("submit_empty_form",)),
            ("password-reset", "/reset-password/", ("submit_empty_form",)),
            ("otp-verify", "/verify/", ()), ("signup-complete", "/signup/complete/", ())]
    if suite in ("public", "all"):
        for n, p in public:
            add("public", n, P, p, auth="anon")
    if suite in ("auth", "all"):
        for n, p, acts in auth:
            add("auth", n, P, p, auth="anon", actions=acts, allow_error=True)
    if suite in ("portal", "all"):
        add("portal", "my-stores", P, "/app/", auth="owner")
        add("portal", "store-create", P, "/app/stores/new/", auth="owner", actions=("submit_empty_form",))
        add("portal", "notifications", P, "/app/notifications/", auth="owner")
        sid = ids.get("onboarding_store")
        if sid:
            for step in ("", "identity/", "industry/", "template/", "branding/", "review/"):
                add("portal", f"onboarding-{step.strip('/') or 'start'}", P, f"/app/stores/{sid}/onboarding/{step}", auth="owner")
            add("portal", "store-created", P, f"/app/stores/{sid}/created/", auth="owner")
            add("portal", "billing", P, f"/app/stores/{sid}/billing/", auth="owner")
            add("portal", "domains", P, f"/app/stores/{sid}/domains/", auth="owner")
    if suite in ("platform-admin", "all"):
        for n, p in [("home", "/"), ("stores", "/stores/"), ("users", "/users/"), ("plans", "/plans/"),
                     ("subscriptions", "/subscriptions/"), ("payments", "/payments/"),
                     ("sms-providers", "/sms/providers/"), ("sms-templates", "/sms/templates/"),
                     ("sms-messages", "/sms/messages/"), ("public-photos", "/public-photos/")]:
            add("platform-admin", n, A, p, auth="padmin")
        if ids.get("any_store"):
            add("platform-admin", "store-detail", A, f"/stores/{ids['any_store']}/", auth="padmin")
    if suite in ("dashboard", "all"):
        for n, p in [("home", ""), ("products", "products/"), ("product-new", "products/new/"),
                     ("categories", "categories/"), ("brands", "brands/"), ("collections", "collections/"),
                     ("orders", "orders/"), ("invoices", "invoices/"), ("payments", "payments/"),
                     ("customers", "customers/"), ("segments", "segments/"), ("reports", "reports/"),
                     ("settings", "settings/"), ("campaigns", "campaigns/"),
                     ("campaign-wizard", "campaigns/add/"), ("notifications", "notifications/"),
                     ("pages", "pages/"), ("staff", "staff/"), ("staff-add", "staff/add/"),
                     ("inventory", "inventory/"), ("coupons", "coupons/"), ("coupon-add", "coupons/add/"),
                     ("audit-log", "audit-log/"), ("exports", "exports/"), ("hero", "homepage/hero/"),
                     ("banners", "homepage/banners/"), ("menus", "menus/"), ("footer", "footer/settings/"),
                     ("social-links", "social-links/"), ("attributes", "attributes/")]:
            add("dashboard", n, S, "/admin-portal/" + p, auth="owner")
    if suite in ("builder", "all"):
        for n, p in [("editor-r4", "storefront-builder/r4/"), ("editor", "storefront-builder/"),
                     ("templates-gallery", "storefront-builder/templates/"),
                     ("appearance", "storefront-builder/appearance/"),
                     ("preview", "storefront-builder/preview/"), ("history", "storefront-builder/history/")]:
            add("builder", n, S, "/admin-portal/" + p, auth="owner", allow_error=True)
    if suite == "storefront-templates":
        from apps.storefront_builder import layout_preset_registry as lpr

        slug = ids.get("product_slug")
        for tpl in lpr.list_ready_templates():
            pages = [("home", "/", False), ("listing", "/products/", True), ("cart", "/cart/", True)]
            if slug:
                from urllib.parse import quote

                pages.insert(2, ("pdp", f"/products/{quote(slug)}/", True))
            for i, (n, p, rest_only) in enumerate(pages):
                add("storefront-templates", f"{tpl.key}:{n}", S, p, auth="anon", allow_error=True,
                    template=tpl.key, apply_template=(tpl.key if i == 0 else None), rest_only=rest_only,
                    group_by_surface=False)
    if suite in ("storefront", "all"):
        for n, p in [("home", "/"), ("products", "/products/"), ("collections", "/collections/"),
                     ("cart", "/cart/"), ("checkout", "/checkout/")]:
            add("storefront", n, S, p, auth="anon", allow_error=True)
    return out


def pick_chromium():
    for candidate in CHROMIUM_CANDIDATES:
        if os.path.isfile(candidate):
            return candidate
    return None


def new_context(browser, vp, cookies_for):
    w, h, mobile = VIEWPORTS[vp]
    context = browser.new_context(viewport={"width": w, "height": h}, is_mobile=mobile, has_touch=mobile, locale="fa-IR")
    context.add_init_script(PROBE_JS)
    context.add_cookies(cookies_for)
    return context


def write_report(results, args, started):
    payload = results.to_json()
    payload["meta"] = {"viewport": args.viewport, "suite": args.suite, "seconds": round(time.time() - started, 1)}
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
    return payload


def print_summary(payload, top=40):
    s = payload["summary"]
    print("\n=== contrast audit summary ===")
    for k, v in s.items():
        print(f"  {k}: {v}")
    print(f"\n--- worst {min(top, len(payload['failures']))} distinct failures ---")
    for f in payload["failures"][:top]:
        print(f"  {f['ratio']:>5}:1 (need {f['threshold']}) [{f['state']}] {f['sel']} "
              f"fg {f['fg']} on {f['bg']} ({f['category']}) x{f['count']} :: {f['text']!r}  <{', '.join(f['surfaces'][:2])}>")
    if payload["focus_failures"]:
        print("\n--- focus indicator failures ---")
        for f in payload["focus_failures"][:top]:
            print(f"  {f['sel']} :: {f['detail']} <{', '.join(f['surfaces'][:2])}>")
    if payload["errors"]:
        print(f"\n--- {len(payload['errors'])} errors (first 15) ---")
        for e in payload["errors"][:15]:
            print("  ", e)


def run_template_suite(args, surfaces, contexts):
    """One result file per Ready Template (resumable: finished templates are skipped), then an aggregate."""
    out_dir = os.path.splitext(args.out)[0] + "_per_template"
    os.makedirs(out_dir, exist_ok=True)
    by_key = defaultdict(list)
    for surface in surfaces:
        by_key[surface["template"]].append(surface)
    for key, group in by_key.items():
        path = os.path.join(out_dir, f"{key}.json")
        if os.path.exists(path) and not args.fresh:
            print(f"  [skip] {key} (already audited: {path})", flush=True)
            continue
        results = Results()
        for surface in group:
            audit_surface(contexts, results, surface, args)
        payload = results.to_json()
        payload["meta"] = {"template": key, "viewport": args.viewport}
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=1)
        t = results.templates.get(key, {})
        print(f"  audited template {key:<26} measured={t.get('measured', 0):>5} failing={t.get('failing', 0):>4} "
              f"distinct={len(results.failures)} focus_fail={len(results.focus_failures)}", flush=True)
    return aggregate_templates(out_dir, args)


def aggregate_templates(out_dir, args):
    merged = Results()
    per_template = {}
    for name in sorted(os.listdir(out_dir)):
        if not name.endswith(".json"):
            continue
        data = json.load(open(os.path.join(out_dir, name), encoding="utf-8"))
        key = data["meta"]["template"]
        t = data["templates"].get(key, {"measured": 0, "failing": 0, "worst": 99.0, "worst_text": ""})
        per_template[key] = {**t, "distinct_failures": len(data["failures"]), "focus_failures": len(data["focus_failures"]),
                             "unique_checks": data["summary"]["unique_checks"], "errors": len(data["errors"])}
        for f in data["failures"]:
            merged.failures[(key, f["sel"], f["fg"], f["bg"], f["state_class"], f["category"])] = {**f, "surfaces": set(f["surfaces"])}
        for f in data["focus_failures"]:
            merged.focus_failures[(key, f["sel"])] = {**f, "surfaces": set(f["surfaces"])}
        merged.pages += data["pages"]
        merged.errors += data["errors"]
        merged.raw_items += data["summary"]["raw_text_measurements"]
        merged.checked |= {(key, i) for i in range(data["summary"]["unique_checks"])}
        merged.focus_checked |= {(key, i) for i in range(data["summary"]["focus_components_checked"])}
    merged.templates.update(per_template)
    payload = merged.to_json()
    payload["templates"] = per_template
    payload["meta"] = {"viewport": args.viewport, "suite": args.suite}
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
    print("\n=== Ready Template audit ===")
    passing = [k for k, v in per_template.items() if not v["failing"] and not v["focus_failures"]]
    print(f"  templates audited: {len(per_template)}   fully passing (text + focus): {len(passing)}")
    for k, v in sorted(per_template.items(), key=lambda kv: kv[1]["worst"]):
        if v["failing"] or v["focus_failures"]:
            print(f"  {k:<26} failing={v['failing']:>4} distinct={v['distinct_failures']:>3} focus={v['focus_failures']} worst={v['worst']} {v['worst_text']}")
    return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--suite", default="all", help="public|auth|portal|platform-admin|dashboard|builder|storefront|all")
    parser.add_argument("--viewport", default="1366x768", choices=sorted(VIEWPORTS))
    parser.add_argument("--port", default=DEFAULT_PORT)
    parser.add_argument("--store-host", default=DEFAULT_STORE_HOST)
    parser.add_argument("--owner", default=os.environ.get("AUDIT_OWNER", "09120000001"))
    parser.add_argument("--out", default=os.path.join(os.getcwd(), "contrast_audit.json"))
    parser.add_argument("--only", default="", help="substring filter on surface name")
    parser.add_argument("--rest-only", action="store_true", help="skip hover/active/focus/toggle sweeps")
    parser.add_argument("--max-targets", type=int, default=90)
    parser.add_argument("--max-toggles", type=int, default=8)
    parser.add_argument("--top", type=int, default=40)
    parser.add_argument("--fresh", action="store_true", help="storefront-templates: re-audit templates that already have a result file")
    parser.add_argument("--dump", default="", help="print every measurement whose selector contains this text")
    args = parser.parse_args()

    started = time.time()
    DUMP["needle"] = args.dump
    django_setup()
    session = make_sessions(args.owner)
    ids = discover_ids()
    surfaces = build_surfaces(args.suite, ids, args.port, args.store_host)
    if args.only:
        surfaces = [s for s in surfaces if args.only in s["name"]]

    from playwright.sync_api import sync_playwright

    results = Results()
    hosts = {PLATFORM_HOST, args.store_host, PADMIN_HOST}
    cookies = [{"name": "sessionid", "value": session, "url": f"http://{h}:{args.port}"} for h in hosts]
    launch = {"args": ["--no-sandbox", "--host-resolver-rules=MAP *.rastisi.localhost 127.0.0.1, MAP rastisi.localhost 127.0.0.1"]}
    exe = pick_chromium()
    if exe:
        launch["executable_path"] = exe
    with sync_playwright() as pw:
        browser = pw.chromium.launch(**launch)
        contexts = {"session": new_context(browser, args.viewport, cookies),
                    "anon": new_context(browser, args.viewport, [])}
        if args.suite == "storefront-templates":
            payload = run_template_suite(args, surfaces, contexts)
            browser.close()
            return 1 if payload["failures"] or payload["focus_failures"] else 0
        for surface in surfaces:
            audit_surface(contexts, results, surface, args)
            print(f"  audited {surface['name']:<42} failures so far: {len(results.failures)}", flush=True)
        browser.close()
    payload = write_report(results, args, started)
    print_summary(payload, args.top)
    return 1 if payload["failures"] or payload["focus_failures"] else 0


if __name__ == "__main__":
    sys.exit(main())
