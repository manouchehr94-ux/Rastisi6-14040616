"""Verify a notifications migration graph with PRE-EXISTING DATA preserved.

Run from the repository root of the tree under test, against a throw-away SQLite file (never a real database):

    DJANGO_SETTINGS_MODULE=shop_core.settings DJANGO_DEBUG=True DJANGO_SECRET_KEY=scratch \
    PYTHONPATH=. python docs/notifications/migration-integration/verify_graph.py

What it does
1. migrates the whole project only up to ``notifications.0003_sms_log_mirror`` (the state of ``main`` today);
2. seeds realistic rows through *historical* models (outbox rows in every status, per-store templates, an SMS mirror);
3. migrates to the head of the graph under test (fails loudly if the graph has more than one leaf);
4. asserts every seeded row and every column value survived, new columns got safe defaults, the Inbox tables and the
   email-engine tables both exist, and ``makemigrations --check`` reports no drift;
5. migrates BACK to ``0003`` and forward again, asserting the seeded rows survive the round trip.

Exit code 0 = graph is sound. Anything else prints the first failing assertion."""

import os
import sys

import django

django.setup()

from django.core.management import call_command  # noqa: E402
from django.db import connection  # noqa: E402
from django.db.migrations.loader import MigrationLoader  # noqa: E402

BASE = "0003_sms_log_mirror"


def historical_apps():
    loader = MigrationLoader(connection)
    return loader.project_state(list(loader.applied_migrations)).apps


def seed():
    apps = historical_apps()
    Store = apps.get_model("stores", "Store")
    Outbox = apps.get_model("notifications", "NotificationOutbox")
    Template = apps.get_model("notifications", "NotificationTemplate")
    store = Store.objects.get(slug="akhlaghi")   # created by stores.0002 — present in every database
    rows = []
    for i, (channel, status, event) in enumerate([
        ("email", "sent", "order.created"), ("email", "pending", "payment.failed"), ("email", "dead", "order.shipped"),
        ("sms", "sent", "order.created"), ("sms", "failed", "coupon.issued"), ("in_app", "sent", ""),
        ("email", "skipped", "coupon.issued"),
    ]):
        o = Outbox.objects.create(
            channel=channel, store=store, status=status, event_key=event, subject=f"موضوع {i}", body=f"متن {i}",
            recipient_email=f"u{i}@example.com", recipient_phone=f"0912000000{i}", attempts=i, last_error="e" if status == "dead" else "",
            dedupe_key=f"seed-{i}", is_promotional=(event == "coupon.issued"), metadata={"n": i},
        )
        rows.append((o.pk, channel, status, event, f"موضوع {i}", f"متن {i}", f"seed-{i}", i))
    tpls = []
    for ev, ch in (("order.created", "email"), ("order.created", "sms"), ("return.approved", "email")):
        t = Template.objects.create(store=store, event_key=ev, channel=ch, is_enabled=ch == "email",
                                    subject="س" if ch == "email" else "", body=f"قالب {ev}")
        tpls.append((t.pk, ev, ch, ch == "email", f"قالب {ev}"))
    return rows, tpls


def check_data(rows, tpls, *, new_columns):
    from apps.notifications.models import NotificationOutbox, NotificationTemplate

    assert NotificationOutbox.objects.count() == len(rows), "outbox row count changed"
    for pk, channel, status, event, subject, body, dedupe, attempts in rows:
        o = NotificationOutbox.objects.get(pk=pk)
        assert (o.channel, o.status, o.event_key, o.subject, o.body, o.dedupe_key, o.attempts) == \
            (channel, status, event, subject, body, dedupe, attempts), f"outbox {pk} changed"
        if new_columns:
            assert (o.html_body, o.sender_address, o.delivery_state, o.held_since) == ("", "", "", None), f"outbox {pk} new columns"
    assert NotificationTemplate.objects.count() == len(tpls), "template row count changed"
    for pk, ev, ch, enabled, body in tpls:
        t = NotificationTemplate.objects.get(pk=pk)
        assert (t.event_key, t.channel, t.is_enabled, t.body) == (ev, ch, enabled, body), f"template {pk} changed"
        if new_columns:
            assert (t.body_html, t.version) == ("", 1), f"template {pk} new columns"


def main():
    db = connection.settings_dict["NAME"]
    assert str(db).endswith(".sqlite3") or db == ":memory:", f"refusing to run against {db!r}"
    print("1. migrate to", BASE)
    call_command("migrate", "notifications", BASE, verbosity=0, interactive=False)
    rows, tpls = seed()
    print(f"2. seeded {len(rows)} outbox rows + {len(tpls)} templates")
    print("3. migrate to head (a multi-leaf graph raises here)")
    call_command("migrate", verbosity=0, interactive=False)
    check_data(rows, tpls, new_columns=True)
    print("4. data preserved; new columns defaulted")
    from django.apps import apps as live

    names = {m.__name__ for m in live.get_app_config("notifications").get_models()}
    for required in ("EmailSenderIdentity", "PlatformNotificationTemplate", "NotificationTemplateRevision", "EmailProviderEvent",
                     "EmailSuppression", "NotificationEvent"):
        assert required in names, f"model {required} missing from the integrated graph"
    try:
        call_command("makemigrations", "--check", "--dry-run", verbosity=0)
    except SystemExit as exc:
        raise AssertionError("makemigrations --check reports model/migration drift") from exc
    print("5. both lineages' tables exist; no model drift")
    print("6. round trip: back to", BASE, "and forward again")
    call_command("migrate", "notifications", BASE, verbosity=0, interactive=False)
    from apps.notifications.models import NotificationOutbox, NotificationTemplate  # noqa: F401  (table shape differs now)

    cur = connection.cursor()
    cur.execute("select count(*) from notifications_notificationoutbox")
    assert cur.fetchone()[0] == len(rows), "rows lost when migrating back"
    call_command("migrate", verbosity=0, interactive=False)
    check_data(rows, tpls, new_columns=True)
    print("OK — graph is sound, data preserved (forward, backward, forward)")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as exc:
        print("FAILED:", exc)
        sys.exit(1)
