from django.conf import settings


def platform_enamad_verification(request):
    """Expose the platform's eNamad state to templates: the technical
    verification meta only on the platform marketing homepage, and the
    final issued badge (independent lifecycle — may be on/off regardless
    of the meta's state) sitewide on platform pages. Both are strictly
    scoped to the platform's own marketing host — never rendered on a
    merchant storefront or the admin host."""
    try:
        host = request.get_host().split(":", 1)[0].lower().rstrip(".")
    except Exception:
        return {}

    platform_hosts = {
        str(value).lower().rstrip(".")
        for value in getattr(settings, "RASTISI_PLATFORM_HOSTS", ())
    }
    if host not in platform_hosts:
        return {}

    from apps.portal.services.platform_config_service import (
        get_platform_configuration,
    )
    from apps.stores.services.enamad_verification_service import (
        EnamadBadgeError,
        EnamadVerificationMetaError,
        parse_enamad_badge_identifiers,
        parse_enamad_verification_meta_tag,
    )

    config = get_platform_configuration()
    context = {}

    if getattr(request, "path", "") == "/":
        try:
            meta = parse_enamad_verification_meta_tag(config.enamad_verification_meta_tag)
        except EnamadVerificationMetaError:
            meta = None
        if meta is not None:
            context["PLATFORM_ENAMAD_VERIFICATION_META_NAME"] = meta.name
            context["PLATFORM_ENAMAD_VERIFICATION_META_CONTENT"] = meta.content

    if config.enamad_badge_enabled:
        try:
            badge = parse_enamad_badge_identifiers(config.enamad_id, config.enamad_auth_code)
        except EnamadBadgeError:
            badge = None
        if badge is not None:
            context["PLATFORM_ENAMAD_BADGE_PROFILE_URL"] = badge.profile_url
            context["PLATFORM_ENAMAD_BADGE_LOGO_URL"] = badge.logo_url

    return context
