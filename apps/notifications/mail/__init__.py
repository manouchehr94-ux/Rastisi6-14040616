"""Provider-independent outbound-email layer (transport, sender identity, DNS provisioning).

Nothing in this package knows about stores' templates or the outbox; ``notification_service`` calls it.
"""
