"""Test helper: finish the «اطلاعات حساب» (credentials) step of the owner signup journey.

A brand-new Owner can only be created through ``/signup/complete/`` (reached after OTP verification) with a
REQUIRED email + password (+ confirmation). Most journey tests only care about what happens AFTER the account
exists, so they use :func:`complete_account` right after ``/verify/``; the credential behaviour itself is
pinned in ``test_owner_signup_credentials.py``."""

import re
from datetime import timedelta

from django.db.models import F

from apps.portal.models import OwnerOtpChallenge
from apps.portal.services import owner_otp_service

#: A password that satisfies AUTH_PASSWORD_VALIDATORS (length, not common, not numeric, not similar to phone/email).
GOOD_PASSWORD = "Rasti-Journey-pass-93!"
HOST = "rastisi.localhost"
SIGNUP_COMPLETE_URL = "/signup/complete/"


def email_for(phone: str) -> str:
    return f"owner{re.sub(r'[^0-9]', '', phone)}@example.com"


def complete_account(client, *, phone: str, email: str | None = None, password: str = GOOD_PASSWORD,
                     confirm: str | None = None, host: str = HOST, follow: bool = False, **extra):
    """POST the credential step. Includes only the fields the page asks for are accepted by the form; extra
    keys (``full_name``, ``accept_terms``) can be passed through ``extra``."""
    data = {
        "email": email if email is not None else email_for(phone),
        "password": password,
        "password_confirm": password if confirm is None else confirm,
        **extra,
    }
    return client.post(SIGNUP_COMPLETE_URL, data, HTTP_HOST=host, follow=follow)


def finish_signup_if_needed(client, response, *, phone: str, host: str = HOST, **kwargs):
    """If ``response`` (the reply to ``/verify/``) redirects to the credential step, complete it and return the
    final response; otherwise return ``response`` unchanged (existing owner / login / error paths)."""
    if response.status_code == 302 and response["Location"].endswith(SIGNUP_COMPLETE_URL):
        return complete_account(client, phone=phone, host=host, **kwargs)
    return response


def age_otp_cooldown(phone: str | None = None, purpose: str | None = None, seconds: int | None = None) -> None:
    """Move already-issued challenges ``seconds`` into the past (default: just past the server resend cooldown)
    so a test can legitimately request another code — the cooldown itself is enforced by the SERVER and is
    pinned in ``test_owner_otp_resend_cooldown.py``; here we only advance the clock."""
    queryset = OwnerOtpChallenge.objects.all()
    if phone:
        queryset = queryset.filter(phone=phone)
    if purpose:
        queryset = queryset.filter(purpose=purpose)
    queryset.update(created_at=F("created_at") - timedelta(seconds=seconds or owner_otp_service.RESEND_COOLDOWN_SECONDS + 1))
