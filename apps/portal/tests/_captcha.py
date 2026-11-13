"""Solve the real official ALTCHA PoW, without consulting server signing secrets.

The answer_delta argument remains a compatibility name for existing security
regressions: a nonzero value corrupts the derived key, never bypasses the check.
"""

import base64
import copy
import json
from bs4 import BeautifulSoup
from altcha import Challenge, Payload, solve_challenge
from django.core.cache import caches
from django.test import override_settings
from apps.portal.services import captcha_service

ENABLED = {"RASTISI_CAPTCHA_ENABLED": True, "RASTISI_CAPTCHA_TTL_SECONDS": 300}


def captcha_enabled(**extra):
    return override_settings(**{**ENABLED, **extra})


def reset_store():
    caches["ratelimit"].clear()


def encode(data):
    return base64.b64encode(json.dumps(data, separators=(",", ":")).encode()).decode()


def decode(fields):
    return json.loads(base64.b64decode(fields[captcha_service.PAYLOAD_FIELD]))


def nonce(fields):
    return decode(fields)["challenge"]["parameters"]["nonce"]


def solve_data(challenge, *, answer_delta=0):
    challenge = Challenge.from_dict(copy.deepcopy(challenge))
    solution = solve_challenge(challenge, timeout=5)
    assert solution is not None, "official ALTCHA solver timed out"
    data = Payload(challenge, solution).to_dict()
    if answer_delta:
        data["solution"]["derivedKey"] = "0" * 64
    return {captcha_service.PAYLOAD_FIELD: encode(data)}


def challenge_for(client, path, action, host, **extra):
    page = client.get(path, HTTP_HOST=host, **extra)
    assert page.status_code == 200
    widget = BeautifulSoup(page.content, "html.parser").find(
        "altcha-widget", id="captcha-" + action
    )
    assert widget is not None, "no ALTCHA widget for " + action
    result = client.get(widget["challenge"], HTTP_HOST=host, **extra)
    assert result.status_code == 200, result.content
    return result.json()


def solve(client, path, action, host, *, answer_delta=0, **extra):
    return solve_data(
        challenge_for(client, path, action, host, **extra), answer_delta=answer_delta
    )
