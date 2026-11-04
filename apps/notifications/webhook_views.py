"""Public webhook for SES (via SNS) bounce / complaint / delivery events.

Unauthenticated by session by design (it is called by AWS), therefore: every request is rejected unless the SNS
signature verifies AND the TopicArn is allowlisted; the body size is capped; nothing from the body is trusted for
tenant attribution (see ``events_service``). SubscriptionConfirmation is confirmed only for an allowlisted topic."""

import json
import logging

from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.notifications.mail import events_service
from apps.notifications.mail.sns import SnsVerificationError, verify_sns_message

logger = logging.getLogger(__name__)
MAX_BODY_BYTES = 256 * 1024

#: replaceable in tests (no network): ``(url) -> None``
confirm_subscription = None


def _confirm(url: str) -> None:
    import requests

    requests.get(url, timeout=5).raise_for_status()


@csrf_exempt
@require_POST
def ses_sns_webhook(request):
    if len(request.body) > MAX_BODY_BYTES:
        return HttpResponseBadRequest("too large")
    try:
        payload = json.loads(request.body.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError
    except (ValueError, UnicodeDecodeError):
        return HttpResponseBadRequest("invalid json")
    try:
        verify_sns_message(payload, cert_fetcher=getattr(ses_sns_webhook, "cert_fetcher", None))
    except SnsVerificationError:
        logger.warning("rejected an unverifiable SNS message")
        return HttpResponseForbidden("unverified")

    kind = payload.get("Type")
    if kind == "SubscriptionConfirmation":
        (confirm_subscription or _confirm)(payload.get("SubscribeURL", ""))
        return HttpResponse("confirmed")
    if kind != "Notification":
        return HttpResponse("ignored")
    try:
        message = json.loads(payload.get("Message", "{}"))
    except ValueError:
        return HttpResponseBadRequest("invalid message")
    stored = 0
    for item in events_service.parse_ses_notification(message):
        key = item.pop("key")
        event = events_service.ingest(provider="ses", event_id=key, **item)
        stored += 1 if event is not None else 0
    return HttpResponse(f"ok {stored}")
