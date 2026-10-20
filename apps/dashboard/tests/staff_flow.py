"""Test helpers: drive the server-side two-step confirmation (FOLLOWUP-05) the way a browser does."""

import re

_TOKEN_RE = re.compile(r'name="(?:review_token|confirm_token)" value="([^"]+)"')


def token_from(response):
    match = _TOKEN_RE.search(response.content.decode())
    return match.group(1) if match else None


def confirmed_add(client, url, data):
    review = client.post(url, {**data, "step": "review"})
    token = token_from(review)
    if token is None:
        return review
    return client.post(url, {**data, "step": "confirm", "review_token": token}, follow=True)


def confirmed_action(client, url, data=None, extra=None, **kwargs):
    """POST once (gets the confirmation page), then POST again with the issued token (+ any typed confirmation)."""
    data = dict(data or {})
    first = client.post(url, data)
    token = token_from(first)
    if token is None:
        return first
    return client.post(url, {**data, **(extra or {}), "confirm_token": token}, **kwargs)
