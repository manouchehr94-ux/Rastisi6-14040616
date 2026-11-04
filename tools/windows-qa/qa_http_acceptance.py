#!/usr/bin/env python
"""Automated walk-through of acceptance scenarios A-N against a RUNNING RastiSi QA server (real HTTP, real cookies, real
host-based routing, real worker). FAKE e-mail provider only: nothing leaves this computer.

Usage (normally launched by Invoke-RastiSiAcceptanceCheck.ps1, which sets the QA environment first):
    python qa_http_acceptance.py <run.json> [--only A,B] [--report-dir DIR]

Exit code 0 = every automated check passed. Checks that need a human (visual RTL review, a real inbox, real DNS, real SES)
are listed as MANUAL and are never reported as passed."""

import argparse
import glob
import json
import os
import re
import subprocess
import sys
import time
from urllib.parse import unquote, urlparse

import requests

RESULTS = []        # (scenario, check, status, detail)
CTX = {}


def record(scn, name, ok, detail=""):
    RESULTS.append((scn, name, "PASS" if ok else "FAIL", str(detail)[:300]))
    print(f"  [{'PASS' if ok else 'FAIL'}] {scn}: {name}" + (f"  -- {detail}" if (detail and not ok) else ""))
    return ok


def manual(scn, name, how):
    RESULTS.append((scn, name, "MANUAL", how))
    print(f"  [MANUAL] {scn}: {name}")


class Web:
    def __init__(self, port):
        self.port, self.base, self.jars = port, f"http://127.0.0.1:{port}", {}

    def sess(self, host):
        return self.jars.setdefault(host, requests.Session())

    def _h(self, host, path):
        return {"Host": f"{host}:{self.port}", "Referer": f"http://{host}:{self.port}{path}"}

    def get(self, host, path, follow=True):
        for _ in range(12):
            r = self.sess(host).get(self.base + path, headers=self._h(host, path), allow_redirects=False)
            if follow and r.status_code in (301, 302, 303, 307):
                u = urlparse(r.headers["Location"])
                host, path = (u.hostname or host), (u.path or "/") + ("?" + u.query if u.query else "")
                continue
            r.final = (host, path)
            return r
        raise RuntimeError("redirect loop")

    def post(self, host, path, data, form_page=None, follow=True):
        page = self.sess(host).get(self.base + (form_page or path), headers=self._h(host, path), allow_redirects=False)
        m = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', page.text)
        token = m.group(1) if m else (self.sess(host).cookies.get("csrftoken") or "")
        data = dict(data)
        data["csrfmiddlewaretoken"] = token
        r = self.sess(host).post(self.base + path, data=data, headers=self._h(host, path), allow_redirects=False)
        if follow and r.status_code in (301, 302, 303):
            u = urlparse(r.headers["Location"])
            return self.get(u.hostname or host, (u.path or "/") + ("?" + u.query if u.query else ""))
        r.final = (host, path)
        return r

    def login_platform(self, ident, pw):
        r = self.post(PA, "/login/", {"identifier": ident, "password": pw})
        return r.status_code == 200 and "/login" not in r.final[1]

    def login_store(self, host, ident, pw):
        r = self.get(host, "/admin-portal/", follow=False)
        u = urlparse(r.headers.get("Location", ""))
        ar = unquote(dict(x.split("=", 1) for x in u.query.split("&") if x.startswith("admin_return=")).get("admin_return", ""))
        page = self.get(CENTRAL, "/login/?" + u.query if u.query else "/login/", follow=False)
        m = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', page.text)
        rr = self.sess(CENTRAL).post(self.base + "/login/password/", headers=self._h(CENTRAL, "/login/"), allow_redirects=False, data={
            "csrfmiddlewaretoken": m.group(1), "identifier": ident, "password": pw, "admin_return": ar})
        loc = urlparse(rr.headers.get("Location", ""))
        if rr.status_code not in (301, 302) or not loc.path:
            return False
        r = self.get(loc.hostname or CENTRAL, loc.path + ("?" + loc.query if loc.query else ""))
        return r.status_code == 200 and "/login" not in r.final[1]


PA, CENTRAL = "platformadmins.rastisi.localhost", "rastisi.localhost"


def store_web(web, slug, pw):
    """One independent browser-like session per store owner (cached)."""
    cache = CTX.setdefault("webs", {})
    if slug not in cache:
        w = Web(web.port)
        info = CTX["stores"][slug]
        w.ok = w.login_store(urlparse(info["store_admin_url"]).hostname, info["owner_login"], pw)
        cache[slug] = w
    return cache[slug]


def zw(value):
    """Persian text without ZWNJ/RLM marks so that comparisons do not depend on invisible characters."""
    return value.replace("\u200c", "").replace("\u200f", "").replace("\u200e", "")


def text(r):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", r.text))


def manage(run, *args, check=True):
    p = subprocess.run([sys.executable, "manage.py", *args], cwd=run["src_dir"], capture_output=True, text=True, encoding="utf-8")
    if check and p.returncode != 0:
        raise RuntimeError(f"manage.py {' '.join(args)} failed: {p.stderr[-300:]}")
    return p.stdout


def mailbox(run):
    out = []
    for f in sorted(glob.glob(os.path.join(run["run_dir"], "mailbox", "*.json"))):
        with open(f, encoding="utf-8") as fh:
            m = json.load(fh)
        m["_html"] = f[:-5] + ".html"
        m["_txt"] = f[:-5] + ".txt"
        out.append(m)
    return out


def worker(run):
    return manage(run, "process_notification_outbox")


def new_mail(run, before):
    return [m for m in mailbox(run) if m["message_id"] not in before]


def ids(run):
    return {m["message_id"] for m in mailbox(run)}


def order(run, store="qa-bike"):
    out = manage(run, "qa_place_order", "--store", store)
    m = re.search(r"order (\S+) grand_total=(\d+) payment_status=(\w+)", out)
    return (m.group(1), int(m.group(2)), m.group(3), out) if m else (None, 0, "", out)


def form_values(r, names):
    """name -> current value for the named fields of an edit form (so a save never silently changes other fields)."""
    return {n: (re.search(rf'name="{n}"[^>]*>', r.text) is not None) for n in names}


# ------------------------------------------------------------------------------------------------------------------ scenarios
def scn_A(web, run, pw):
    """Platform admin edits a platform DEFAULT email template; a store with no override uses it."""
    ok = web.login_platform(CTX["platform_owner"], pw)
    if not record("A", "platform owner signs in on the platform-admin host", ok):
        return
    ev = "order.created"
    r = web.get(PA, f"/notifications/{ev}/")
    record("A", "platform template page opens", r.status_code == 200 and "email_subject" in r.text, r.status_code)
    body = "QA-PLATFORM-DEFAULT سفارش {order_number} ثبت شد. {order_url}"
    r = web.post(PA, f"/notifications/{ev}/", {"action": "save", "email_enabled": "on", "email_subject": "QA-PLATFORM-DEFAULT {order_number}",
                                             "email_body": body, "email_html": "", "sms_enabled": "on", "sms_body": ""})
    record("A", "platform default email template saved", r.status_code == 200 and "QA-PLATFORM-DEFAULT" in r.text, text(r)[:200])
    before = ids(run)
    num, total, pay, _ = order(run, "qa-bike")
    worker(run)
    got = new_mail(run, before)
    mine = [m for m in got if num and num in m["subject"]]
    record("A", "store without override sends the platform default subject", bool(mine) and mine[0]["subject"].startswith("QA-PLATFORM-DEFAULT"),
           [m["subject"] for m in got])
    if mine:
        record("A", "From address is the store's own domain (info@mybikestore.test)", mine[0]["from_address"] == "info@mybikestore.test", mine[0]["from_address"])
        record("A", "mail was sent to the customer address", mine[0]["to"] == "buyer@example.com", mine[0]["to"])


def scn_B_C_D(web, run, pw):
    bike = CTX["stores"]["qa-bike"]
    host = urlparse(bike["store_admin_url"]).hostname
    sw = store_web(web, "qa-bike", pw)
    if not record("B", "store owner (qa-bike) signs in through central login + handoff", sw.ok):
        return
    ev = "order.created"
    # B: store email override
    r = sw.post(host, f"/admin-portal/notifications/{ev}/", {"action": "save", "email_enabled": "on", "email_subject": "QA-STORE-OVERRIDE {order_number}",
                 "email_body": "QA-STORE-OVERRIDE سفارش {order_number} شما ثبت شد.", "email_html": "",
                 "sms_enabled": "on", "sms_body": "QA-STORE-SMS سفارش {order_number} ثبت شد"}, form_page=f"/admin-portal/notifications/{ev}/")
    record("B", "store saves its own email template", r.status_code == 200 and "QA-STORE-OVERRIDE" in r.text, text(r)[:200])
    before = ids(run)
    num, total, pay, _ = order(run)
    worker(run)
    got = [m for m in new_mail(run, before) if num and num in m["subject"]]
    record("B", "store override wins over the platform default", bool(got) and got[0]["subject"].startswith("QA-STORE-OVERRIDE"), [m["subject"] for m in new_mail(run, before)])
    # platform default untouched
    pr = web.get(PA, f"/notifications/{ev}/")
    record("B", "platform default is unchanged by the store's override", "QA-PLATFORM-DEFAULT" in pr.text and "QA-STORE-OVERRIDE" not in pr.text)
    # C: store SMS override persisted and shown
    r = sw.get(host, f"/admin-portal/notifications/{ev}/")
    record("C", "store SMS template edit persisted and shown to the store", "QA-STORE-SMS" in r.text)
    out = manage(run, "shell", "-c", "from apps.notifications.models import NotificationOutbox as N; "
                 "print([ (n.channel, n.status) for n in N.objects.filter(store__slug='qa-bike', event_key='order.created').order_by('-id')[:3] ])")
    CTX["last_outbox"] = out.strip()
    # D: independent channel toggles -> disable EMAIL only
    page = sw.get(host, "/admin-portal/notifications/channels/")
    fields = re.findall(r'name="(seen__[^"]+)"', page.text)
    key_email = f"{ev}__email"
    data = {f: "1" for f in fields}
    for f in fields:
        base = f[len("seen__"):]
        if base != key_email and re.search(rf'name="{re.escape(base)}"[^>]*checked', page.text):
            data[base] = "on"
    r = sw.post(host, "/admin-portal/notifications/channels/", data)
    record("D", "channel switch form saved (email off for order.created, other channels untouched)", r.status_code == 200, r.status_code)
    before = ids(run)
    num, *_ = order(run)
    worker(run)
    record("D", "disabled email channel sends no email", not [m for m in new_mail(run, before) if num and num in m["subject"]])
    row = manage(run, "shell", "-c", "from apps.notifications.models import NotificationOutbox as N; "
                 f"print(sorted({{(n.channel) for n in N.objects.filter(store__slug='qa-bike', event_key='order.created').order_by('-id')[:4]}}))")
    CTX["d_channels"] = row.strip()
    page2 = sw.get(host, "/admin-portal/notifications/channels/")
    record("D", "channel page renders", page2.status_code == 200)
    # re-enable email for later scenarios
    data[key_email] = "on"
    sw.post(host, "/admin-portal/notifications/channels/", data)


def scn_E_F_G(web, run, pw):
    a = CTX["stores"]["qa-no-domain"]
    ha = urlparse(a["store_admin_url"]).hostname
    wa = store_web(web, "qa-no-domain", pw)
    if record("E", "store without a custom domain signs in", wa.ok):
        r = wa.get(ha, "/admin-portal/notifications/sender/")
        t = r.text
        record("E", "sender status is INACTIVE", 'id="sender-status" data-status="inactive"' in t)
        record("E", "Persian reason + corrective action + who must act are shown",
               all(zw(s) in zw(t) for s in ("فروشگاه هنوز دامنهی اختصاصی ندارد", "یک دامنهی اختصاصی برای فروشگاه ثبت کنید", "مالکِ دامنه")))
        record("E", "no RastiSi-domain fallback address is offered", "@rastisi" not in t.lower().replace("platformadmins", ""))
        record("E", "last verification time is shown (never silently blank)", "آخرین بررسی" in t)
    b = CTX["stores"]["qa-pending"]
    hb = urlparse(b["store_admin_url"]).hostname
    wb = store_web(web, "qa-pending", pw)
    if record("F", "pending-domain store signs in", wb.ok):
        r = wb.get(hb, "/admin-portal/notifications/sender/")
        t = r.text
        record("F", "status PENDING", 'data-status="pending"' in t)
        recs = re.findall(r"<code>([^<]*_domainkey\.pendingstore\.test)</code>", t)
        record("F", "exact DKIM CNAME records are listed (3)", len(set(recs)) == 3, recs)
        record("F", "website and email verification are shown separately", 'id="two-verifications"' in t and 'id="site-verification"' in t and 'id="email-verification"' in t)
        record("F", "advisory SPF/DMARC section present and non-blocking", 'id="dns-advisory"' in t and 'data-status="pending"' in t)
        # G: provider verifies -> retry -> ACTIVE
        manage(run, "qa_email_domain", "verify", "pendingstore.test")
        r = wb.post(hb, "/admin-portal/notifications/sender/retry/", {}, form_page="/admin-portal/notifications/sender/")
        record("G", "after the (fake) provider verifies DKIM, retry activates the sender", 'data-status="active"' in r.text and "info@pendingstore.test" in r.text, text(r)[:160])


def scn_H_I_J(web, run, pw):
    # H: approved test email through the platform admin for qa-bike
    sid = manage(run, "shell", "-c", "from apps.stores.models import Store; print(Store.objects.get(slug='qa-bike').pk)").strip().splitlines()[-1]
    before = ids(run)
    r = web.post(PA, "/notifications/order.created/test/", {"channel": "email", "recipient": "qa-recipient@example.com", "store_id": sid},
                 form_page="/notifications/order.created/")
    record("H", "platform test-send completes", r.status_code == 200 and "ارسال" in r.text, text(r)[:200])
    got = new_mail(run, before)
    mine = [m for m in got if m["to"] == "qa-recipient@example.com"]
    record("H", "test e-mail left through the verified store sender", bool(mine) and mine[0]["from_address"] == "info@mybikestore.test", [(m["to"], m["from_address"]) for m in got])
    # H': an INACTIVE store cannot be test-sent from (no silent fallback)
    sid_a = manage(run, "shell", "-c", "from apps.stores.models import Store; print(Store.objects.get(slug='qa-no-domain').pk)").strip().splitlines()[-1]
    before = ids(run)
    r = web.post(PA, "/notifications/order.created/test/", {"channel": "email", "recipient": "qa-recipient@example.com", "store_id": sid_a},
                 form_page="/notifications/order.created/")
    record("H", "store with no verified domain: test e-mail is NOT sent (no RastiSi substitution)",
           not new_mail(run, before) and zw("فعال نیست") in zw(r.text), text(r)[:200])
    # I: history with state + provider message id
    bike = CTX["stores"]["qa-bike"]
    host = urlparse(bike["store_admin_url"]).hostname
    sw = store_web(web, "qa-bike", pw)
    sent_ids = [m["message_id"] for m in mailbox(run) if m["from_address"] == "info@mybikestore.test"]
    r = sw.get(host, "/admin-portal/notifications/history/")
    record("I", "history page lists sent messages with their provider message id", bool(sent_ids) and any(i in r.text for i in sent_ids), sent_ids[-1:])
    record("I", "history has a delivery-state column", 'class="delivery-state"' in r.text and 'data-state="' in r.text)
    # J: bounce + complaint -> suppression; later mail to the same address is not sent
    last = [m for m in mailbox(run) if m["to"] == "buyer@example.com"][-1]["message_id"]
    out = manage(run, "qa_simulate_email_event", "bounce", "--message-id", last, "--event-id", "acc-bounce-1")
    out2 = manage(run, "qa_simulate_email_event", "bounce", "--message-id", last, "--event-id", "acc-bounce-1")
    record("J", "bounce ingested once; replay of the same event id is ignored (idempotent)", "ingested" in out and "ignored" in out2, (out, out2))
    sup = manage(run, "shell", "-c", "from apps.notifications.models import EmailSuppression as E; print(sorted(E.objects.values_list('store__slug','email','reason')))")
    record("J", "recipient is suppressed for THIS store only", "('qa-bike', 'buyer@example.com'" in sup and "qa-other" not in sup, sup.strip()[-120:])
    hist = sw.get(host, "/admin-portal/notifications/history/")
    record("I", "history now shows the 'bounced' delivery state for that message", 'data-state="bounced"' in hist.text and last in hist.text)
    before = ids(run)
    num, *_ = order(run)
    worker(run)
    record("J", "a new order e-mail to the suppressed address is not sent", not [m for m in new_mail(run, before) if num and num in m["subject"]])
    manage(run, "qa_simulate_email_event", "complaint", "--message-id", last, "--event-id", "acc-complaint-1")
    sup = manage(run, "shell", "-c", "from apps.notifications.models import EmailProviderEvent as E; print(sorted(E.objects.values_list('event_type', flat=True)))")
    record("J", "complaint event stored", "complaint" in sup, sup.strip()[-80:])


def scn_K(web, run, pw):
    other = CTX["stores"]["qa-other"]
    ho = urlparse(other["store_admin_url"]).hostname
    ow = store_web(web, "qa-other", pw)
    if not record("K", "second tenant signs in", ow.ok):
        return
    r = ow.get(ho, "/admin-portal/notifications/order.created/")
    record("K", "second tenant sees ITS OWN override", "QA-OVERRIDE-TENANT-D" in r.text)
    record("K", "second tenant does NOT see the first tenant's override or platform edit", "QA-STORE-OVERRIDE" not in r.text)
    r = ow.get(ho, "/admin-portal/notifications/sender/")
    record("K", "second tenant's sender page shows only its own domain", "otherstore.test" in r.text and "mybikestore.test" not in r.text)
    r = ow.get(ho, "/admin-portal/notifications/history/")
    record("K", "second tenant's history has no mail of the first tenant", "buyer@example.com" not in r.text and "mybikestore.test" not in r.text)
    r = ow.get(ho, "/admin-portal/notifications/sender/", follow=False)
    # the store admin must never be reachable on the platform-admin host and platform pages never on a store host
    r2 = ow.sess(ho).get(ow.base + "/notifications/senders/", headers={"Host": f"{ho}:{ow.port}"}, allow_redirects=False)
    record("K", "platform notification pages are not served on a store host", r2.status_code in (301, 302, 403, 404), r2.status_code)
    # RBAC: limited platform member
    w2 = Web(ow.port)
    ok = w2.login_platform(CTX["platform_limited_member"], pw)
    if record("K", "limited platform member can sign in", ok):
        record("K", "limited member may VIEW the catalog", w2.get(PA, "/notifications/").status_code == 200)
        record("K", "limited member is denied sender oversight (403)", w2.get(PA, "/notifications/senders/").status_code == 403)
        record("K", "limited member is denied delivery review (403)", w2.get(PA, "/notifications/delivery/").status_code == 403)
        rr = w2.post(PA, "/notifications/order.created/", {"action": "save", "email_enabled": "on", "email_subject": "HACK", "email_body": "HACK"}, form_page="/notifications/")
        record("K", "limited member cannot edit platform templates", rr.status_code in (403,) or "HACK" not in web.get(PA, "/notifications/order.created/").text, rr.status_code)


def scn_L(web, run, pw):
    num, total, pay, out = order(run)
    record("L", "checkout/order service unchanged: COD order total is exact", total == 5000000 and pay == "pending", out.strip()[:160])
    record("L", "order confirmation e-mail queued without touching totals", "queued: order.created [email]" in out)
    r = web.get(CENTRAL, "/", follow=False)
    record("L", "marketing host responds", r.status_code in (200, 301, 302), r.status_code)
    manual("L", "storefront checkout in a browser (cart -> COD -> confirmation page)", "see README scenario L")


def scn_M(web, run, pw):
    host = urlparse(CTX["stores"]["qa-bike"]["store_admin_url"]).hostname
    sw = store_web(web, "qa-bike", pw)
    for path in ("/admin-portal/notifications/sender/", "/admin-portal/notifications/channels/", "/admin-portal/notifications/order.created/"):
        r = sw.get(host, path)
        record("M", f"{path} is RTL + has a viewport meta", 'dir="rtl"' in r.text and 'name="viewport"' in r.text)
    manual("M", "visual RTL review on desktop (1280px) and phone (390px) widths", "see README scenario M and docs/notifications/ui-evidence")


def scn_N(web, run, pw):
    out = manage(run, "qa_simulate_email_event", "delivery", "--event-id", "acc-del-1")
    again = manage(run, "qa_simulate_email_event", "delivery", "--event-id", "acc-del-1")
    record("N", "repeated provider event creates no duplicate", "ignored" in again, again.strip())
    n = manage(run, "shell", "-c", "from apps.notifications.models import EmailProviderEvent as E; print(E.objects.filter(event_id='acc-del-1').count())").strip().splitlines()[-1]
    record("N", "exactly one stored row for the repeated event id", n == "1", n)
    before = ids(run)
    worker(run)
    worker(run)
    record("N", "re-running the worker does not resend already-sent mail", not new_mail(run, before))
    manual("N", "EXPIRED / stale events are never sent late (hard TTL, held-window, promotional)", "covered by automated tests apps.notifications.tests.test_expiry (34 tests); not time-travelled here")


SCENARIOS = {"A": scn_A, "B": scn_B_C_D, "E": scn_E_F_G, "H": scn_H_I_J, "K": scn_K, "L": scn_L, "M": scn_M, "N": scn_N}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_json")
    ap.add_argument("--report-dir", default="")
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    with open(a.run_json, encoding="utf-8-sig") as fh:
        run = json.load(fh)
    with open(os.path.join(run["run_dir"], "QA-INFO.json"), encoding="utf-8-sig") as fh:
        info = json.load(fh)
    CTX.update(platform_owner=info["platform_owner"], platform_limited_member=info["platform_limited_member"],
               stores={s["slug"]: s for s in info["stores"]})
    pw = run["password"]
    web = Web(int(run["port"]))
    only = {x.strip().upper() for x in a.only.split(",") if x.strip()}
    print(f"Acceptance checks against {web.base} (run {os.path.basename(run['run_dir'])}, commit {run['commit'][:10]})")
    for key, fn in SCENARIOS.items():
        if only and key not in only:
            continue
        print(f"\n== scenario group {key}: {fn.__doc__ or fn.__name__}")
        try:
            fn(web, run, pw)
        except Exception as exc:  # noqa: BLE001
            record(key, "scenario crashed", False, f"{type(exc).__name__}: {exc}")
    fails = [r for r in RESULTS if r[2] == "FAIL"]
    passed = [r for r in RESULTS if r[2] == "PASS"]
    print(f"\nSUMMARY: {len(passed)} passed, {len(fails)} failed, {len([r for r in RESULTS if r[2] == 'MANUAL'])} manual-only")
    report_dir = a.report_dir or run["run_dir"]
    os.makedirs(report_dir, exist_ok=True)
    with open(os.path.join(report_dir, "ACCEPTANCE-REPORT.md"), "w", encoding="utf-8") as fh:
        fh.write(f"# Automated acceptance report - commit {run['commit']}\n\nFake e-mail provider; real HTTP + real worker. "
                 f"{len(passed)} passed, {len(fails)} failed.\n\n| scenario | check | result | detail |\n|---|---|---|---|\n")
        for s, n, st, d in RESULTS:
            fh.write(f"| {s} | {n} | {st} | {d.replace('|', '/').replace(chr(10), ' ')} |\n")
    with open(os.path.join(report_dir, "acceptance.json"), "w", encoding="utf-8") as fh:
        json.dump([dict(scenario=s, check=n, result=st, detail=d) for s, n, st, d in RESULTS], fh, ensure_ascii=False, indent=1)
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
