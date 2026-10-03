"""Backfill the promotional-consent policy for customers that existed before it.

Evidence audit: ``accepts_promotional_*`` was added (0004) with ``default=True`` and there is no
record anywhere (no audit event, no consent timestamp, no signup/checkout checkbox) of a customer
explicitly ticking it. A stored ``True`` therefore proves nothing and is **not** carried over:

* ``True``  → ``False`` and source ``legacy_unverified`` (kept as a marker; nothing is deleted).
* ``False`` → stays ``False``; with the old default of True this can only be an explicit opt-out
  (or an explicit programmatic False), so source ``legacy_opt_out`` records it as withdrawal.

Idempotent (only rows with an empty source are touched) and set-based (two UPDATEs). Data
reversibility: the reverse restores ``True`` for rows still marked ``legacy_unverified`` — i.e. the
pre-policy state; rows changed by customers/staff after the policy are never touched.
"""

from django.db import migrations


def backfill(apps, schema_editor):
    Customer = apps.get_model("customers", "Customer")
    for channel in ("sms", "email"):
        flag, source = f"accepts_promotional_{channel}", f"promo_{channel}_consent_source"
        Customer.objects.filter(**{flag: True, source: ""}).update(**{flag: False, source: "legacy_unverified"})
        Customer.objects.filter(**{flag: False, source: ""}).update(**{source: "legacy_opt_out"})


def restore(apps, schema_editor):
    Customer = apps.get_model("customers", "Customer")
    for channel in ("sms", "email"):
        flag, source = f"accepts_promotional_{channel}", f"promo_{channel}_consent_source"
        Customer.objects.filter(**{flag: False, source: "legacy_unverified"}).update(**{flag: True, source: ""})
        Customer.objects.filter(**{source: "legacy_opt_out"}).update(**{source: ""})


class Migration(migrations.Migration):
    dependencies = [("customers", "0006_promotional_consent_policy")]
    operations = [migrations.RunPython(backfill, restore)]
