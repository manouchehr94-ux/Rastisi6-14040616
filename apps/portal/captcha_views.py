"""Same-origin, uncached ALTCHA challenge endpoint. No external verifier."""

from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET
from django.utils.cache import patch_vary_headers
from apps.core.services.rate_limit import UNAVAILABLE_MESSAGE
from apps.portal.services import captcha_service


@require_GET
@never_cache
def challenge(request, action):
    if action not in captcha_service.ACTIONS:
        return JsonResponse({"error": "unknown action"}, status=404)
    result = captcha_service.issue(request, action)
    if not result.get("enabled"):
        response = JsonResponse({"error": "captcha disabled"}, status=503)
    elif result.get("unavailable"):
        response = JsonResponse(
            {"error": UNAVAILABLE_MESSAGE},
            status=429 if result.get("rate_limited") else 503,
        )
    else:
        response = JsonResponse(result["challenge"])
    patch_vary_headers(response, ["Cookie"])
    response["X-Content-Type-Options"] = "nosniff"
    return response
