"""Merge migration: joins the two notification-migration lineages that both descend from ``0003_sms_log_mirror``.

* ``0004_inbox_engine``                                  — Admin Inbox engine (payment-engine / Claude lineage)
* ``0005`` -> ``0006_expiry_status_and_dns_automation``  — unified SMS+email engine (Kiro lineage)

The two lineages touch disjoint tables (Inbox: NotificationEvent/InboxItem/...; email engine: EmailSenderIdentity/
PlatformNotificationTemplate/... plus four columns and a status choice on NotificationOutbox, which the Inbox lineage does not
touch). This migration therefore has NO operations: it only makes the graph linear again so ``migrate`` has a single leaf.

Why a merge instead of re-pointing 0005's dependency: re-pointing rewrites an already-published migration, which is unsafe for any
database that has applied it. A merge migration changes nothing that was ever applied. See docs/notifications/MIGRATION_INTEGRATION.md.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("notifications", "0004_inbox_engine"),
        ("notifications", "0006_expiry_status_and_dns_automation"),
    ]

    operations = []
