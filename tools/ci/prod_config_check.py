#!/usr/bin/env python3
"""Boot the application with a complete, production-LIKE environment built from dummy values and fail on any error (standard library only).

Checks, in separate processes so that one failure cannot hide another:
  1. `manage.py check --deploy --fail-level ERROR`                    production system checks (rastisi.E00x included)
  2. `manage.py makemigrations --check --dry-run`                     models and migrations agree (nothing to generate)
  3. the settings that must be safe by default really are             simulation off, refund kill switches off, QA simulator off,
                                                                      dev OTP empty, secure cookies, DEBUG off
  4. startup FAILS closed when a protection is removed                no CAPTCHA, no Redis URL, DEBUG on with a production-style host

Nothing here connects to a database or Redis (the checks do not open connections), and no real secret is involved.
"""

import argparse
import json
import os
import secrets
import subprocess
import sys
from pathlib import Path


def base_env(extra=None):
    keep = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "VIRTUAL_ENV", "PYTHONPATH")}
    from cryptography.fernet import Fernet
    env = dict(keep, DJANGO_DEBUG="False", DJANGO_SECRET_KEY=secrets.token_urlsafe(60), DJANGO_ALLOWED_HOSTS="rastisi.example,www.rastisi.example",
               DJANGO_CSRF_TRUSTED_ORIGINS="https://rastisi.example", DATABASE_URL="postgresql://u:p@127.0.0.1:5432/x",
               RASTISI_RATE_LIMIT_CACHE_URL="redis://:p@127.0.0.1:6379/0", PAYMENT_CREDENTIAL_KEY=Fernet.generate_key().decode(),
               DJANGO_STATIC_ROOT="/tmp/rastisi-static", DJANGO_MEDIA_ROOT="/tmp/rastisi-media",
               DJANGO_SECURE_SSL_REDIRECT="True", DJANGO_SECURE_HSTS_SECONDS="3600",
               TURNSTILE_SITE_KEY="1x00000000000000000000AA", TURNSTILE_SECRET_KEY="1x0000000000000000000000000000AA", TURNSTILE_EXPECTED_HOSTNAMES="rastisi.example")
    env.update(extra or {})
    return env


def manage(args, env, repo):
    return subprocess.run([sys.executable, "manage.py"] + args, cwd=repo, env=env, capture_output=True, text=True, timeout=300)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=".")
    args = ap.parse_args(argv)
    repo = str(Path(args.repo).resolve())
    problems = []

    def expect(name, ok, detail=""):
        print(("PASS  " if ok else "FAIL  ") + name + ("" if ok else "  -> " + detail[-400:]))
        if not ok:
            problems.append(name)

    env = base_env()
    proc = manage(["check", "--deploy", "--fail-level", "ERROR"], env, repo)
    expect("check --deploy (production-like environment)", proc.returncode == 0, proc.stderr + proc.stdout)
    proc = manage(["makemigrations", "--check", "--dry-run"], env, repo)
    expect("no missing migrations", proc.returncode == 0, proc.stdout + proc.stderr)

    probe = ("import json,os,django;os.environ['DJANGO_SETTINGS_MODULE']='shop_core.settings';django.setup();from django.conf import settings as s;"
             "g=lambda n,d=None:getattr(s,n,d);print(json.dumps({'debug':s.DEBUG,'prod':g('RASTISI_PRODUCTION_MODE'),'sim':g('PAYMENTS_SIMULATION_ENABLED'),"
             "'sms_refund':g('RASTISI_SMS_REFUND_ENABLED'),'bank_refund':g('RASTISI_BANK_AUTOMATIC_REFUND_GATEWAYS'),'qa_sim':g('RASTISI_QA_PAYMENT_SIMULATOR'),"
             "'dev_otp':g('RASTISI_DEV_OTP_CODE'),'sess_secure':s.SESSION_COOKIE_SECURE,'csrf_secure':s.CSRF_COOKIE_SECURE,'ssl_redirect':s.SECURE_SSL_REDIRECT}))")
    proc = subprocess.run([sys.executable, "-c", probe], cwd=repo, env=env, capture_output=True, text=True, timeout=120)
    try:
        v = json.loads(proc.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        v = {}
        expect("settings load in production mode", False, proc.stderr)
    if v:
        expect("production mode is on and DEBUG is off", v["prod"] is True and v["debug"] is False, str(v))
        expect("payment simulation, QA simulator and dev OTP are off", not v["sim"] and not v["qa_sim"] and not v["dev_otp"], str(v))
        expect("refund kill switches are off by default", not v["sms_refund"] and not v["bank_refund"], str(v))
        expect("session and CSRF cookies are Secure", v["sess_secure"] and v["csrf_secure"], str(v))

    for label, extra, drop in (
        ("startup refuses a missing shared Redis URL", {}, ["RASTISI_RATE_LIMIT_CACHE_URL"]),
        ("startup refuses a missing secret key", {}, ["DJANGO_SECRET_KEY"]),
        ("startup refuses missing allowed hosts", {}, ["DJANGO_ALLOWED_HOSTS"]),
        ("startup refuses the CAPTCHA being switched off (or, on older commits, Turnstile)", {"RASTISI_CAPTCHA_ENABLED": "false", "TURNSTILE_ENABLED": "false"}, []),
        ("startup refuses a development OTP code", {"RASTISI_DEV_OTP_CODE": "123456"}, []),
        ("startup refuses insecure cookies", {"DJANGO_SESSION_COOKIE_SECURE": "false"}, []),
    ):
        bad = base_env(extra)
        for key in drop:
            bad.pop(key, None)
        proc = manage(["check"], bad, repo)
        expect(label, proc.returncode != 0, "the application started although a protection was removed")

    print("\nproduction config check: %s" % ("FAILED (%d)" % len(problems) if problems else "OK"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
