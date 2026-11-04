"""Shared test helpers for the notification suites."""

from apps.notifications.mail.fake import FakeTransport
from apps.notifications.models import EmailSenderIdentity


def give_active_sender(store, address="info@sender-example.test"):
    """Store has a verified custom domain at the (fake) provider and an ACTIVE sender identity. No network."""
    domain = address.split("@", 1)[1]
    FakeTransport.reset()
    FakeTransport.identities[domain] = {"status": "verified"}
    identity, _ = EmailSenderIdentity.objects.update_or_create(
        store=store, defaults={
            "domain_name": domain, "local_part": address.split("@", 1)[0], "provider": "fake",
            "provider_ref": f"fake:{domain}", "status": EmailSenderIdentity.Status.ACTIVE,
        },
    )
    return identity
