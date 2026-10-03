#!/usr/bin/env python
"""Local stand-in for the SmsRasti Android app (protocol check WITHOUT a phone). It speaks exactly the public gateway protocol
(`GET /sms/smsrasti/poll/?token=…`, `POST /sms/smsrasti/ack/` with id/status/rec_id/error) — it does NOT send any SMS.

  python tools/smsrasti_simulator.py --base-url https://store.example.com --token <device token> --outcome sent [--once]
  --outcome sent|failed|none   (none = claim but never acknowledge, to watch the bounded re-claim)

Use it against a staging store to verify pairing, queue draining, acknowledgements and the dashboard status. A real phone is
still required to prove that the Android app itself sends SMS through the SIM card."""

import argparse
import sys
import time

import requests


def run_once(base_url: str, token: str, outcome: str = "sent", *, timeout: float = 10, host: str = "") -> dict:
    headers = {"Host": host} if host else {}
    poll = requests.get(f"{base_url}/sms/smsrasti/poll/", params={"token": token}, timeout=timeout, headers=headers)
    if poll.status_code == 401:
        return {"result": "unauthorized"}
    data = poll.json()
    if data.get("status") != "ok":
        return {"result": "empty"}
    if outcome == "none":
        return {"result": "claimed", "id": data["id"], "phone": data["phone"]}
    payload = {"token": token, "id": data["id"], "status": outcome}
    if outcome == "sent":
        payload["rec_id"] = f"sim-{data['id']}"
    else:
        payload["error"] = "simulated device failure"
    ack = requests.post(f"{base_url}/sms/smsrasti/ack/", data=payload, timeout=timeout, headers=headers)
    return {"result": outcome, "id": data["id"], "phone": data["phone"], "ack_http": ack.status_code}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--token", required=True)
    ap.add_argument("--outcome", choices=["sent", "failed", "none"], default="sent")
    ap.add_argument("--host", default="")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--interval", type=float, default=5)
    a = ap.parse_args()
    while True:
        print(run_once(a.base_url.rstrip("/"), a.token, a.outcome, host=a.host), flush=True)
        if a.once:
            return
        time.sleep(a.interval)


if __name__ == "__main__":
    sys.exit(main())
