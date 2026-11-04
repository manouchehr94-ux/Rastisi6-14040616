"""Chooses the active :class:`EmailTransport` from settings — mirrors ``apps.sms.services.backends`` /
``apps.sms.services.sms_service.get_backend``: nothing else in the codebase imports ``ses``/``fake`` directly."""

from __future__ import annotations

from django.conf import settings

from .base import EmailTransport
from .fake import FakeTransport


def get_transport() -> EmailTransport:
    provider = getattr(settings, "RASTISI_EMAIL_PROVIDER", "fake")
    if provider == "ses":
        from .ses import SesTransport

        return SesTransport()
    if provider == "fake":
        return FakeTransport()
    raise ValueError(f"ارائه‌دهنده‌ی ایمیلِ ناشناخته: {provider}")
