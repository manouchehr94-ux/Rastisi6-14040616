"""Is the platform's industry catalogue (صنف‌ها) actually loaded and offerable?

The registry (``apps.catalog.industry_templates.registry``) lives in code; the sellers pick from ``IndustryTemplate`` ROWS that
``seed_industry_templates`` writes. A database that never got that step shows a new seller «no industry templates» — and, now that choosing
an industry is mandatory, would block them. This module only READS (3 cheap queries, no writes, no network) and answers:

* how many templates the registry defines vs. how many exist in this database vs. how many are offerable to sellers,
* whether the free-form «سایر (صنف آزاد)» choice (``OTHER_SLUG``) is offerable — the guarantee that EVERY seller always has a valid choice,
* which registry entries are missing.

Used by the ``ensure_industry_registry`` management command (the platform bootstrap step), the ``rastisi.W010`` system check
(operator warning) and the onboarding «صنف» step (friendly message + operator log instead of a dead end). It never seeds by itself:
seeding is an explicit platform operation, never something a customer request or a login triggers."""

from __future__ import annotations

from dataclasses import dataclass

from apps.catalog.industry_templates.registry import ALL_INDUSTRY_TEMPLATES
from apps.catalog.models import IndustryTemplate
from apps.catalog.services import industry_catalog_service

#: the free-form choice for a business that is not in the list; the mandatory-industry rule is satisfiable only while this one is offerable
OTHER_SLUG = "other"


@dataclass(frozen=True)
class RegistryStatus:
    registry_total: int
    database_total: int
    missing: tuple[str, ...]
    offerable_total: int
    active_total: int
    other_offerable: bool

    @property
    def is_ready(self) -> bool:
        return not self.missing and self.offerable_total > 0 and self.other_offerable

    @property
    def state(self) -> str:
        if self.is_ready:
            return "ready"
        return "empty" if self.database_total == 0 else "partial"

    @property
    def problems(self) -> list[str]:
        problems = []
        if self.database_total == 0:
            problems.append(f"هیچ الگوی صنفی در پایگاه‌داده نیست (رجیستری: {self.registry_total}). دستور «ensure_industry_registry --apply» را اجرا کنید.")
        elif self.missing:
            problems.append(f"{len(self.missing)} الگوی صنفِ رجیستری هنوز در پایگاه‌داده نیست: {', '.join(self.missing[:8])}{' …' if len(self.missing) > 8 else ''}")
        if not self.other_offerable:
            problems.append("گزینهٔ «سایر (صنف آزاد)» قابل ارائه نیست؛ فروشنده‌ای که صنفش در فهرست نباشد نمی‌تواند ادامه دهد.")
        if self.offerable_total == 0 and self.database_total:
            problems.append("هیچ الگوی «آمادهٔ تولید و فعال» برای ارائه به فروشنده‌ها وجود ندارد.")
        return problems

    def as_dict(self) -> dict:
        return {
            "state": self.state, "is_ready": self.is_ready, "registry_total": self.registry_total, "database_total": self.database_total,
            "active_total": self.active_total, "offerable_total": self.offerable_total, "other_offerable": self.other_offerable,
            "missing": list(self.missing), "problems": self.problems,
        }


def registry_keys() -> set[tuple[str, int]]:
    return {(entry["slug"], entry["version"]) for entry in ALL_INDUSTRY_TEMPLATES}


def check_registry() -> RegistryStatus:
    expected = registry_keys()
    rows = list(IndustryTemplate.objects.values_list("slug", "version", "is_active"))
    present = {(slug, version) for slug, version, _active in rows}
    offerable = industry_catalog_service.offerable_industry_templates()
    return RegistryStatus(
        registry_total=len(expected),
        database_total=len(present & expected),
        missing=tuple(sorted({slug for slug, _version in expected - present})),
        offerable_total=len(offerable),
        active_total=sum(1 for _slug, _version, active in rows if active),
        other_offerable=any(template.slug == OTHER_SLUG for template in offerable),
    )
