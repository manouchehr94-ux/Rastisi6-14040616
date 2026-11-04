"""Operator warning: the industry catalogue is not loaded / not offerable in this database.

Tagged ``database`` so it only runs where a database check is wanted (``manage.py check --database default``, ``migrate``, deploy pipelines) and
never on a plain ``check``/``runserver`` start. Read-only, and silent on a database that has no tables yet (before the first ``migrate``) and
while the test runner is building its own empty database (same ``"test" in sys.argv`` rule ``shop_core.settings`` already uses)."""

import sys

from django.core.checks import Tags, Warning, register
from django.db.utils import DatabaseError


def industry_registry_warnings() -> list:
    from apps.catalog.services import industry_registry_readiness as readiness

    try:
        status = readiness.check_registry()
    except DatabaseError:
        return []                                   # tables do not exist yet: nothing to warn about
    if status.is_ready:
        return []
    return [Warning(
        "؛ ".join(status.problems), id="rastisi.W010",
        hint="Run `python manage.py ensure_industry_registry --apply` once after `migrate` (loads only the missing templates; existing rows untouched).",
    )]


@register(Tags.database)
def check_industry_registry_ready(app_configs, databases=None, **kwargs):
    if "test" in sys.argv:
        return []
    return industry_registry_warnings()
