"""Validate a bundle without touching the database.

Exit code: 0 = PASS, 1 = FAIL, 2 = BLOCKED (input missing).
"""

import sys

from django.core.management.base import BaseCommand

from apps.stores.services.demo_bundle.targets import load_targets
from apps.stores.services.demo_bundle.validator import validate_bundle


class Command(BaseCommand):
    help = "Validate a RastiSi store bundle (structure, hashes, references, Studio completeness)."

    def add_arguments(self, parser):
        parser.add_argument("bundle")
        parser.add_argument("--targets", default=None)
        parser.add_argument("--strict-expected", action="store_true")
        parser.add_argument("--no-decode", action="store_true", help="skip Pillow decoding of images")
        parser.add_argument("--json", action="store_true")

    def handle(self, *args, **opts):
        report = validate_bundle(
            opts["bundle"], targets=load_targets(opts["targets"]),
            strict_expected=opts["strict_expected"], decode_images=not opts["no_decode"],
        )
        self.stdout.write(report.to_json() if opts["json"] else report.to_text())
        sys.exit({"PASS": 0, "FAIL": 1, "BLOCKED": 2}[report.status])
