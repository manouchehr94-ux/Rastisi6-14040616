"""Guards shared by the QA-only management commands (Windows/local acceptance tooling).

These commands exist so a person can verify the notification engine on a laptop with NO AWS credentials, NO DNS access and
NO outbound network. They are refused unless ALL of the following hold, so they cannot run against a real deployment:

* ``DEBUG`` is on, and
* the environment variable ``RASTISI_QA_MODE=1`` is set (the QA launcher sets it for its own process only), and
* the email provider is the in-process ``fake`` provider (``ses_smoke_test`` is the one deliberate exception — it has its
  own, stricter opt-in).
"""

from __future__ import annotations

import os

from django.conf import settings
from django.core.management.base import CommandError

QA_ENV = "RASTISI_QA_MODE"


def require_qa(*, fake_provider: bool = True) -> None:
    if not settings.DEBUG:
        raise CommandError("این دستور فقط برای QA محلی است و با DEBUG=False اجرا نمی‌شود.")
    if os.environ.get(QA_ENV) != "1":
        raise CommandError(f"این دستور فقط برای QA محلی است؛ متغیر محیطی {QA_ENV}=1 تنظیم نشده است.")
    if fake_provider and getattr(settings, "RASTISI_EMAIL_PROVIDER", "fake") != "fake":
        raise CommandError("این دستور فقط با ارائه‌دهنده‌ی ایمیلِ «fake» اجرا می‌شود (هیچ ایمیل واقعی نباید ارسال شود).")
