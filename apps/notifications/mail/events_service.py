"""Delivery / bounce / complaint ingestion + suppression. Provider-neutral: the SES webhook parses its own payload
and calls :func:`ingest`; tests with the fake provider call :func:`ingest` directly.

Tenant attribution comes ONLY from our own outbox row (matched by provider message id) — never from anything in
the webhook body — so a forged/foreign event can never create a suppression for the wrong Store."""

from __future__ import annotations

import logging

from django.db import IntegrityError, transaction

from apps.notifications.models import EmailProviderEvent, EmailSuppression, NotificationOutbox

logger = logging.getLogger(__name__)

DELIVERY, BOUNCE, COMPLAINT = "delivery", "bounce", "complaint"
_STATE = {DELIVERY: "delivered", BOUNCE: "bounced", COMPLAINT: "complained"}
_RANK = {"": 0, "delivered": 1, "bounced": 2, "complained": 3}  # a worse outcome is never overwritten by a better one


@transaction.atomic
def ingest(*, provider: str, event_id: str, event_type: str, message_id: str, recipient: str = "",
           permanent: bool = False, detail: dict | None = None):
    """Idempotent (same ``event_id`` is a no-op). Returns the stored event, or ``None`` for a duplicate."""
    if event_type not in _STATE:
        raise ValueError("unknown event type")
    outbox = None
    if message_id:
        outbox = NotificationOutbox.objects.select_for_update().filter(
            channel=NotificationOutbox.Channel.EMAIL, provider_ref=message_id,
        ).first()
    try:
        with transaction.atomic():
            event = EmailProviderEvent.objects.create(
                provider=provider, event_id=event_id[:200], event_type=event_type, message_id=message_id[:120],
                recipient=(recipient or (outbox.recipient_email if outbox else ""))[:254],
                store=outbox.store if outbox else None, outbox=outbox,
                detail=_safe_detail(detail or {}),
            )
    except IntegrityError:
        return None
    if outbox is None:
        logger.info("email provider event %s for an unknown message id was stored without attribution", event_type)
        return event

    new_state = _STATE[event_type]
    if _RANK[new_state] > _RANK[outbox.delivery_state]:
        outbox.delivery_state = new_state
        outbox.save(update_fields=["delivery_state", "updated_at"])

    suppress = (event_type == BOUNCE and permanent) or event_type == COMPLAINT
    if suppress and outbox.store_id and outbox.recipient_email:
        EmailSuppression.objects.get_or_create(
            store_id=outbox.store_id, email=outbox.recipient_email.lower(),
            defaults={"reason": "bounce" if event_type == BOUNCE else "complaint"},
        )
    return event


def _safe_detail(detail: dict) -> dict:
    """Keep only small, non-sensitive diagnostic keys (no headers/body/IP)."""
    allowed = ("bounceType", "bounceSubType", "complaintFeedbackType", "diagnosticCode", "status", "action")
    return {k: str(v)[:200] for k, v in detail.items() if k in allowed}


def parse_ses_notification(message: dict) -> list[dict]:
    """SES notification JSON (the SNS ``Message``) -> list of ``ingest`` kwargs. One entry per recipient."""
    kind = message.get("notificationType") or message.get("eventType")
    mail = message.get("mail") or {}
    message_id = mail.get("messageId", "")
    out = []
    if kind == "Delivery":
        for rcpt in (message.get("delivery") or {}).get("recipients", []):
            out.append(dict(event_type=DELIVERY, message_id=message_id, recipient=rcpt, detail={}, key=f"{message_id}:delivery:{rcpt}"))
    elif kind == "Bounce":
        bounce = message.get("bounce") or {}
        for rcpt in bounce.get("bouncedRecipients", []):
            out.append(dict(
                event_type=BOUNCE, message_id=message_id, recipient=rcpt.get("emailAddress", ""),
                permanent=bounce.get("bounceType") == "Permanent",
                detail={"bounceType": bounce.get("bounceType"), "bounceSubType": bounce.get("bounceSubType"),
                        "diagnosticCode": rcpt.get("diagnosticCode", "")},
                key=f"{message_id}:bounce:{rcpt.get('emailAddress', '')}",
            ))
    elif kind == "Complaint":
        complaint = message.get("complaint") or {}
        for rcpt in complaint.get("complainedRecipients", []):
            out.append(dict(
                event_type=COMPLAINT, message_id=message_id, recipient=rcpt.get("emailAddress", ""),
                detail={"complaintFeedbackType": complaint.get("complaintFeedbackType")},
                key=f"{message_id}:complaint:{rcpt.get('emailAddress', '')}",
            ))
    return out
