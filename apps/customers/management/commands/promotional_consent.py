"""Operator tool for the promotional-consent policy (``customers.services.consent_service``).

  manage.py promotional_consent report
      read-only counts per channel/source (verification after migration 0007).

  manage.py promotional_consent import --file consent.csv --channel sms|email|both --evidence "<ref>" [--apply]
      grant consent for customers WITH external, documented evidence of opt-in (e.g. a signed form,
      a verified legacy list). CSV: one phone per line (header "phone" optional). Dry-run unless
      ``--apply``. Source recorded as ``import``; the evidence reference is stored in the audit trail
      of ``--store``. Never grants anything implicitly and never withdraws consent.
"""

import csv

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count

from apps.core.phone import InvalidPhoneError, normalize_iranian_phone
from apps.customers.models import Customer
from apps.customers.services import consent_service
from apps.stores.models import Store


class Command(BaseCommand):
    help = "Report or import promotional consent (no implicit grants)."

    def add_arguments(self, parser):
        sub = parser.add_subparsers(dest="action", required=True)
        sub.add_parser("report")
        imp = sub.add_parser("import")
        imp.add_argument("--file", required=True)
        imp.add_argument("--channel", choices=["sms", "email", "both"], required=True)
        imp.add_argument("--evidence", required=True, help="reference to the documented consent evidence")
        imp.add_argument("--store", help="store slug for the audit trail (required with --apply)")
        imp.add_argument("--apply", action="store_true")

    def handle(self, *args, **opts):
        if opts["action"] == "report":
            return self.report()
        return self.import_consent(opts)

    def report(self):
        total = Customer.objects.count()
        self.stdout.write(f"customers: {total}")
        for channel in ("sms", "email"):
            flag, source = f"accepts_promotional_{channel}", f"promo_{channel}_consent_source"
            rows = Customer.objects.values(flag, source).annotate(n=Count("pk")).order_by(flag, source)
            for r in rows:
                self.stdout.write(f"{channel:5} consent={str(r[flag]):5} source={r[source] or '(none)':18} count={r['n']}")

    def import_consent(self, opts):
        store = None
        if opts["apply"]:
            if not opts["store"]:
                raise CommandError("--store is required with --apply (audit trail)")
            store = Store.objects.filter(slug=opts["store"]).first()
            if store is None:
                raise CommandError("unknown store")
        phones, bad = [], 0
        with open(opts["file"], newline="", encoding="utf-8") as fh:
            for row in csv.reader(fh):
                if not row or not row[0].strip() or row[0].strip().lower() == "phone":
                    continue
                try:
                    phones.append(normalize_iranian_phone(row[0].strip()))
                except InvalidPhoneError:
                    bad += 1
        sms = opts["channel"] in ("sms", "both")
        email = opts["channel"] in ("email", "both")
        found = granted = 0
        for customer in Customer.objects.filter(phone__in=set(phones)).iterator():
            found += 1
            if not opts["apply"]:
                continue
            if consent_service.set_promotional_consent(
                customer, source=Customer.ConsentSource.IMPORT, sms=True if sms else None,
                email=True if email else None, store=store,
            ):
                granted += 1
        mode = "APPLIED" if opts["apply"] else "DRY-RUN (nothing changed)"
        self.stdout.write(
            f"{mode}: rows={len(phones)} invalid={bad} matched_customers={found} granted={granted} evidence={opts['evidence'][:80]}"
        )
