"""Trial/purchase E2E server: real Django app + an in-process FAKE Zibal (no network, dummy credentials). Control endpoints under /__e2e__/ — DISPOSABLE QA ONLY.
Run with DJANGO_DEBUG=True RASTISI_DEV_OTP_CODE=123456 (owner OTP without any SMS provider) and a throw-away DATABASE_URL."""
import json, os, sys, threading
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "shop_core.settings")
sys.path.insert(0, os.environ.get("REPO", os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
import django
django.setup()
from django.conf import settings
from django.contrib.staticfiles.handlers import StaticFilesHandler
from django.core.wsgi import get_wsgi_application
from unittest import mock
from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIServer, WSGIRequestHandler, make_server

PORT = int(os.environ.get("E2E_PORT", "8020"))
settings.RASTISI_BILLING_CALLBACK_BASE_URL = f"http://rastisi.localhost:{PORT}"
settings.ALLOWED_HOSTS = ["*"]

STATE = {"next": 5000, "tracks": {}, "paid": set(), "calls": []}

class _Resp:
    def __init__(self, payload): self._p = payload; self.status_code = 200
    def json(self): return self._p

def fake_post(url, json=None, timeout=None, **kw):
    path = url.rsplit("/", 1)[-1]
    STATE["calls"].append((path, dict(json or {})))
    if path == "request":
        STATE["next"] += 1
        tid = STATE["next"]
        STATE["tracks"][tid] = {"orderId": json["orderId"], "amount": json["amount"], "callbackUrl": json["callbackUrl"]}
        return _Resp({"result": 100, "trackId": tid, "message": "success"})
    if path == "verify":
        tid = int(json["trackId"]); t = STATE["tracks"].get(tid)
        if t and tid in STATE["paid"]:
            return _Resp({"result": 100, "amount": t["amount"], "status": 1, "refNumber": str(900000 + tid), "orderId": t["orderId"]})
        return _Resp({"result": 202, "message": "not paid"})
    raise AssertionError(url)

mock.patch("apps.billing.providers.zibal.requests.post", fake_post).start()
app = StaticFilesHandler(get_wsgi_application())

def wsgi(environ, start):
    p = environ.get("PATH_INFO", "")
    if p.startswith("/__e2e__/"):
        parts = p.split("/")
        hdr = [("Content-Type", "application/json"), ("Access-Control-Allow-Origin", "*")]
        if parts[2] == "info":
            t = STATE["tracks"].get(int(parts[3]), {})
            start("200 OK", hdr); return [json.dumps(t).encode()]
        if parts[2] == "pay":
            STATE["paid"].add(int(parts[3])); start("200 OK", hdr); return [b"{}"]
        if parts[2] == "wrong_amount":                      # next verify will report a different amount
            tid = int(parts[3]); STATE["tracks"][tid]["amount"] = 1000; STATE["paid"].add(tid); start("200 OK", hdr); return [b"{}"]
        if parts[2] in ("pay_return", "cancel_return", "wrong_return"):
            tid = int(parts[3]); t = STATE["tracks"][tid]
            if parts[2] == "pay_return":
                STATE["paid"].add(tid); q = f"success=1&status=2&trackId={tid}"
            elif parts[2] == "wrong_return":
                t["amount"] = 1000; STATE["paid"].add(tid); q = f"success=1&status=2&trackId={tid}"
            else:
                q = f"success=0&status=3&trackId={tid}"
            start("302 Found", [("Location", t["callbackUrl"] + "?" + q)]); return [b""]
        if parts[2] == "calls":
            start("200 OK", hdr); return [json.dumps(STATE["calls"], default=str).encode()]
    return app(environ, start)

class Threaded(ThreadingMixIn, WSGIServer):
    daemon_threads = True

class Quiet(WSGIRequestHandler):
    def log_message(self, *a): pass

srv = make_server("0.0.0.0", PORT, wsgi, server_class=Threaded, handler_class=Quiet)
print("E2E server on", PORT, flush=True)
srv.serve_forever()
