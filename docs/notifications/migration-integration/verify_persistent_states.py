"""Option A (merge migration) rehearsed against three realistic DATABASE HISTORIES, each seeded with data.

Run one scenario per throw-away SQLite file (the caller deletes db.sqlite3 between runs; see rehearse_states.sh):

    DJANGO_SETTINGS_MODULE=shop_core.settings DJANGO_DEBUG=True DJANGO_SECRET_KEY=scratch PYTHONPATH=. \
        python docs/notifications/migration-integration/verify_persistent_states.py payment_db|pr37_db|fresh_db

* payment_db — a database that only ever ran the payment-engine/Inbox lineage:   notifications applied up to 0004_inbox_engine.
* pr37_db    — a database that only ever ran the email-engine PR (e.g. the product owner's Windows QA DB): applied 0005 + 0006, but NOT 0004.
               This is exactly the state in which re-pointing 0005's dependency (Option B) would raise InconsistentMigrationHistory.
* fresh_db   — an empty database migrated straight to head.

Every scenario then migrates to the head of the INTEGRATED graph and asserts: no migration error, a single notifications leaf, every seeded
row/column unchanged, both lineages' tables usable, no model drift. payment_db/pr37_db also round-trip the outbox back to 0003 and forward."""

import sys

import django

django.setup()

from django.core.management import call_command  # noqa: E402
from django.db import connection  # noqa: E402
from django.db.migrations.loader import MigrationLoader  # noqa: E402
from django.utils import timezone  # noqa: E402


def hist():
    loader = MigrationLoader(connection)
    return loader.project_state(list(loader.applied_migrations)).apps


def migrate(*args):
    call_command("migrate", *args, verbosity=0, interactive=False)


def seed_common(apps):
    Store = apps.get_model("stores", "Store")
    User = apps.get_model("auth", "User")
    store = Store.objects.get(slug="akhlaghi")
    other = Store.objects.create(name="other", slug="qa-mig-other", status="active")
    user = User.objects.create(username="mig-user", is_staff=True)
    Outbox = apps.get_model("notifications", "NotificationOutbox")
    rows = []
    for i, (ch, st, st_store) in enumerate([("email", "sent", store), ("sms", "failed", store), ("email", "pending", other)]):
        o = Outbox.objects.create(channel=ch, store=st_store, status=st, event_key="order.created", subject=f"s{i}", body=f"b{i}",
                                  recipient_email=f"u{i}@example.com", dedupe_key=f"mig-{i}", attempts=i)
        rows.append((o.pk, ch, st, st_store.pk, f"s{i}", f"b{i}", f"mig-{i}", i))
    return store, other, user, rows


def check_common(rows):
    from apps.notifications.models import NotificationOutbox

    assert NotificationOutbox.objects.count() == len(rows), "outbox row count changed"
    for pk, ch, st, store_pk, subj, body, dedupe, attempts in rows:
        o = NotificationOutbox.objects.get(pk=pk)
        assert (o.channel, o.status, o.store_id, o.subject, o.body, o.dedupe_key, o.attempts) == (ch, st, store_pk, subj, body, dedupe, attempts), f"outbox {pk} changed"


def leaf_check():
    leaves = [n for n in MigrationLoader(connection).graph.leaf_nodes() if n[0] == "notifications"]
    assert leaves == [("notifications", "0007_merge_inbox_and_email_identity")], f"unexpected notifications leaves: {leaves}"


def drift_check():
    try:
        call_command("makemigrations", "--check", "--dry-run", verbosity=0)
    except SystemExit as exc:
        raise AssertionError("makemigrations --check reports drift") from exc


def scenario_payment_db():
    migrate("notifications", "0004_inbox_engine")
    applied = {n for a, n in MigrationLoader(connection).applied_migrations if a == "notifications"}
    assert "0004_inbox_engine" in applied and "0005_email_sender_identity_platform_templates" not in applied, applied
    apps = hist()
    store, other, user, rows = seed_common(apps)
    Event, Item, Pref = (apps.get_model("notifications", n) for n in ("NotificationEvent", "InboxItem", "NotificationPreference"))
    ev1 = Event.objects.create(type_key="payment.succeeded", category="payments", scope="store", scope_key=f"store:{store.pk}", store=store,
                               title="پرداخت موفق", occurred_at=timezone.now(), dedupe_key="pay-1")
    ev2 = Event.objects.create(type_key="payment.failed", category="payments", scope="store", scope_key=f"store:{other.pk}", store=other,
                               title="پرداخت ناموفق", occurred_at=timezone.now(), dedupe_key="pay-2")
    Item.objects.create(event=ev1, user=user, scope_key=ev1.scope_key, read_at=timezone.now(), pinned=True)
    Item.objects.create(event=ev2, user=user, scope_key=ev2.scope_key)
    Pref.objects.create(user=user, scope_key=ev1.scope_key, toast_enabled=False, disabled_categories=["orders"])
    print(f"  seeded: {len(rows)} outbox, 2 inbox events, 2 inbox items (1 read+pinned), 1 preference, 2 tenants")
    migrate()                                  # upgrade to the integrated head: applies 0005, 0006, 0007 (+ every other app)
    leaf_check()
    check_common(rows)
    from apps.notifications.models import InboxItem, NotificationEvent, NotificationOutbox, NotificationPreference
    from apps.notifications.models_email import EmailSenderIdentity, EmailSuppression  # noqa: F401

    assert NotificationEvent.objects.count() == 2 and InboxItem.objects.count() == 2, "Inbox rows lost"
    one = InboxItem.objects.get(event__dedupe_key="pay-1")
    assert one.pinned and one.read_at is not None and one.scope_key == f"store:{store.pk}", "Inbox item state changed"
    assert NotificationPreference.objects.get().disabled_categories == ["orders"], "preference changed"
    assert not NotificationEvent.objects.filter(scope_key=f"store:{other.pk}").filter(store_id=store.pk).exists(), "tenant mixing"
    o = NotificationOutbox.objects.first()
    assert (o.html_body, o.sender_address, o.delivery_state, o.held_since) == ("", "", "", None), "new columns not defaulted"
    drift_check()
    print("  upgraded: Inbox rows/flags/preferences intact, outbox intact, new columns defaulted, tenants not mixed, single leaf, no drift")
    migrate("notifications", "0003_sms_log_mirror")
    cur = connection.cursor()
    cur.execute("select count(*) from notifications_notificationoutbox")
    assert cur.fetchone()[0] == len(rows), "outbox rows lost on reverse"
    migrate()
    check_common(rows)
    print("  round trip (reverse to 0003 and forward): outbox rows survive (rolling back 0004 intentionally drops the Inbox tables it created)")


def scenario_pr37_db():
    migrate("notifications", "0006_expiry_status_and_dns_automation")
    applied = {n for a, n in MigrationLoader(connection).applied_migrations if a == "notifications"}
    assert "0006_expiry_status_and_dns_automation" in applied and "0004_inbox_engine" not in applied, applied
    apps = hist()
    store, other, user, rows = seed_common(apps)
    Ident = apps.get_model("notifications", "EmailSenderIdentity")
    Supp = apps.get_model("notifications", "EmailSuppression")
    Ident.objects.create(store=store, domain_name="mybikestore.test", local_part="info", provider="fake", status="active")
    Ident.objects.create(store=other, domain_name="", local_part="info", status="inactive", reason_code="no_custom_domain")
    Supp.objects.create(store=store, email="gone@example.com", reason="bounce")
    Outbox = apps.get_model("notifications", "NotificationOutbox")
    spec = Outbox.objects.create(channel="email", store=store, status="expired", event_key="order.created", subject="x", body="y",
                                 html_body="<p>y</p>", sender_address="info@mybikestore.test", delivery_state="bounced",
                                 dedupe_key="mig-spec")
    rows.append((spec.pk, "email", "expired", store.pk, "x", "y", "mig-spec", 0))
    print("  seeded: 3 outbox + 1 email-engine outbox row (expired/bounced/html), 2 sender identities, 1 suppression")
    migrate()                                  # THE point of Option A: 0004 and 0007 are applied AFTER 0005/0006 without touching them
    leaf_check()
    check_common(rows)
    from apps.notifications.models import NotificationEvent, NotificationOutbox
    from apps.notifications.models_email import EmailSenderIdentity, EmailSuppression

    s = NotificationOutbox.objects.get(pk=spec.pk)
    assert (s.status, s.html_body, s.sender_address, s.delivery_state) == ("expired", "<p>y</p>", "info@mybikestore.test", "bounced"), "email-engine columns changed"
    assert EmailSenderIdentity.objects.count() == 2 and EmailSuppression.objects.get().email == "gone@example.com", "email-engine rows changed"
    assert NotificationEvent.objects.count() == 0, "Inbox table should exist and be empty"
    NotificationEvent.objects.create(type_key="t", category="c", scope="platform", scope_key="platform", title="t", occurred_at=timezone.now())
    drift_check()
    print("  upgraded: 0004 + merge applied after 0005/0006 with NO inconsistent-history error; email-engine rows intact; Inbox tables now usable")
    migrate("notifications", "0003_sms_log_mirror")
    migrate()
    check_common(rows)
    print("  round trip OK")


def scenario_fresh_db():
    migrate()
    leaf_check()
    from django.apps import apps as live

    names = {m.__name__ for m in live.get_app_config("notifications").get_models()}
    for need in ("NotificationEvent", "InboxItem", "EmailSenderIdentity", "PlatformNotificationTemplate", "EmailSuppression"):
        assert need in names, need
    drift_check()
    print("  fresh DB: single leaf, both lineages' models present, no drift")


if __name__ == "__main__":
    name = sys.argv[1]
    db = connection.settings_dict["NAME"]
    assert str(db).endswith(".sqlite3") or db == ":memory:", f"refusing to run against {db!r}"
    print(f"[{name}]")
    try:
        globals()[f"scenario_{name}"]()
    except AssertionError as exc:
        print("FAILED:", exc)
        sys.exit(1)
    print("OK")
