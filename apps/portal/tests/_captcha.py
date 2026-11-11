"""Test helpers for the server-side math CAPTCHA (``apps.portal.services.captcha_service``).

Tests solve the challenge the way a visitor does: they GET the real page, read the two operands and the opaque token from the HTML, and
send back the sum. Nothing here reaches into the service to learn the answer.
"""

import re

from django.core.cache import caches
from django.test import override_settings

from apps.portal.services import captcha_service

_PERSIAN = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")

#: Settings that switch the CAPTCHA on (it is off by default outside production).
ENABLED = {"RASTISI_CAPTCHA_ENABLED": True, "RASTISI_CAPTCHA_TTL_SECONDS": 300}


def captcha_enabled(**extra):
    return override_settings(**{**ENABLED, **extra})


def reset_store():
    """Forget every challenge and budget counter (the dev rate-limit store is process-local LocMem)."""
    caches["ratelimit"].clear()


def read_challenge(html, action):
    """Return ``(left, right, token)`` of the question shown for ``action`` on a rendered page."""
    marker = f'id="captcha-label-{action}"'
    start = html.index(marker)
    block = html[start:start + 2500]
    question = re.search(r'<bdi dir="ltr">(\S+) \+ (\S+) = ؟</bdi>', block)
    token = re.search(r'name="captcha_token" value="([^"]+)"', block)
    assert question and token, "no CAPTCHA question found for " + action
    return int(question.group(1).translate(_PERSIAN)), int(question.group(2).translate(_PERSIAN)), token.group(1)


def solve(client, path, action, host, *, answer_delta=0, **extra):
    """GET ``path`` and return the POST fields (token + answer) for ``action``; ``answer_delta`` makes the answer wrong on purpose."""
    page = client.get(path, HTTP_HOST=host, **extra)
    assert page.status_code == 200
    left, right, token = read_challenge(page.content.decode(), action)
    return {
        captcha_service.TOKEN_FIELD: token,
        captcha_service.ANSWER_FIELD: str(left + right + answer_delta),
    }
