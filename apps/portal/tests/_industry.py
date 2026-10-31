"""Test support for the MANDATORY industry rule (owner decision): a shop must choose an industry before it can leave the «صنف» onboarding
step, and a business that is not in the list chooses «سایر (صنف آزاد)». Tests that only need a shop that is already PAST that step install the
free-form ``other`` template through the real service."""

from apps.catalog.models import IndustryTemplate, IndustryTemplateCategory, StoreIndustryInstallation
from apps.catalog.services.industry_template_service import install_industry_template

OTHER_SLUG = "other"


def ensure_other_template() -> IndustryTemplate:
    """The registry's «سایر (صنف آزاد)» entry as an offerable row (same slug / one generic category as ``approved_catalog``)."""
    template, _ = IndustryTemplate.objects.get_or_create(
        slug=OTHER_SLUG, version=1,
        defaults={"name": "سایر (صنف آزاد)", "icon": "✨", "sector": IndustryTemplate.Sector.OTHER, "display_order": 101,
                  "readiness": IndustryTemplate.Readiness.PRODUCTION_READY, "is_active": True,
                  "default_section_keys": ["announcement_bar", "hero_banner", "category_grid"]},
    )
    IndustryTemplateCategory.objects.get_or_create(industry_template=template, code="other", defaults={"name": "سایر", "icon": "✨"})
    return template


def install_other_industry(store, *, drop_categories: bool = False) -> StoreIndustryInstallation:
    """Idempotent: a shop that already has an installation is left alone. ``drop_categories`` simulates a seller who deleted the one generic
    category the free-form template creates (tests about a genuinely EMPTY catalogue)."""
    existing = StoreIndustryInstallation.objects.filter(store=store).first()
    if existing is not None:
        return existing
    installation = install_industry_template(store, ensure_other_template()).installation
    if drop_categories:
        store.categories.all().delete()
    return installation


def choose_other_industry(client, industry_url: str, host: str = "rastisi.localhost"):
    """Pick «سایر (صنف آزاد)» through the real «صنف» step (what a seller whose business is not listed does)."""
    template = ensure_other_template()
    return client.post(industry_url, {"industry_template_id": template.pk, "confirm_industry_install": "1"}, HTTP_HOST=host)
