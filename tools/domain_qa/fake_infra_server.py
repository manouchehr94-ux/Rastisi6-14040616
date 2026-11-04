"""QA-ONLY development server with FAKE DNS and FAKE HTTPS for the custom-domain flow.

Why: the QA host names (``*.rastisi.localhost``) are not public, so the real ownership / DNS / HTTPS checks can never succeed there — and a QA
run must not send real DNS or TLS requests. This script starts the normal Django dev server but, inside THAT process only, replaces the three
network primitives of ``apps.stores.services.domain_verification_service`` (TXT look-up, A/CNAME look-up, TLS probe) with answers read from a
small JSON state file you flip from another terminal. Nothing else changes: the real views, permissions, tenant scoping, anti-hijack rules,
rate limit, audit log and the owner-level Step-Up for the final activation all run exactly as in production.

Safety: refuses to start unless DEBUG is on and the database is SQLite; patches nothing outside this process; sends no network traffic.

    python tools/domain_qa/fake_infra_server.py runserver 127.0.0.1:8009     # start (uses the project's normal settings / SQLite db)
    python tools/domain_qa/fake_infra_server.py status                       # show the fake internet
    python tools/domain_qa/fake_infra_server.py set txt on                   # the TXT ownership record «appears» in DNS
    python tools/domain_qa/fake_infra_server.py set routing on               # the A record now points at RastiSi
    python tools/domain_qa/fake_infra_server.py set tls on                   # HTTPS is ready
    python tools/domain_qa/fake_infra_server.py reset                        # everything off again

State file: ``$RASTISI_FAKE_INFRA_STATE`` or ``<temp dir>/rastisi_fake_infra.json`` (read on every check, so a running server follows it).
The fake A record target is 203.0.113.10 (TEST-NET-3, reserved for documentation)."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

STATE_FILE = Path(os.environ.get("RASTISI_FAKE_INFRA_STATE") or Path(tempfile.gettempdir()) / "rastisi_fake_infra.json")
DEFAULTS = {"txt": False, "routing": False, "tls": False}
FAKE_A_TARGET = "203.0.113.10"


def read_state() -> dict:
    try:
        return {**DEFAULTS, **json.loads(STATE_FILE.read_text(encoding="utf-8"))}
    except (OSError, ValueError):
        return dict(DEFAULTS)


def write_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps({key: bool(state.get(key)) for key in DEFAULTS}), encoding="utf-8")


def install_fakes():
    """Replace the network primitives (this process only). Returns the module for tests."""
    from apps.stores.services import domain_verification_service as dvs

    def fake_txt(hostname, expected_value):
        return read_state()["txt"]

    def fake_routing(hostname):
        configured = bool(dvs.custom_domain_connection_instructions(hostname)["configured"])
        connected = configured and read_state()["routing"]
        return dvs.DnsRoutingCheck(
            configured=configured, connected=connected, expected_a_targets=(FAKE_A_TARGET,),
            observed_a_targets=(FAKE_A_TARGET,) if connected else (), expected_cname="", observed_cname="", error="")

    def fake_tls(hostname):
        ready = read_state()["tls"]
        return dvs.SslConnectionCheck(reachable=ready, certificate_expires_at=None, error="" if ready else "fake: HTTPS not ready")

    dvs._txt_records_match = fake_txt
    dvs.check_dns_routing = fake_routing
    dvs.check_ssl_connection = fake_tls
    return dvs


def run_server(args: list[str]) -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "shop_core.settings")
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    import django

    django.setup()
    from django.conf import settings
    from django.core.management import call_command

    if not settings.DEBUG or "sqlite" not in settings.DATABASES["default"]["ENGINE"]:
        raise SystemExit("refusing to start: this QA tool only runs with DEBUG on and a SQLite database")
    settings.RASTISI_CUSTOM_DOMAIN_A_TARGETS = (FAKE_A_TARGET,)
    settings.RASTISI_CUSTOM_DOMAIN_CNAME_TARGET = ""
    install_fakes()
    write_state(read_state())
    print(f"FAKE DNS/HTTPS active (state file: {STATE_FILE}); no real DNS or TLS request will be made.", flush=True)
    call_command("runserver", *(args or ["127.0.0.1:8000"]), "--noreload")


def main(argv: list[str]) -> int:
    command = argv[0] if argv else "status"
    if command == "runserver":
        run_server(argv[1:])
    elif command == "status":
        print(json.dumps(read_state(), indent=2))
    elif command == "reset":
        write_state(dict(DEFAULTS))
        print(json.dumps(read_state()))
    elif command == "set" and len(argv) == 3 and argv[1] in DEFAULTS and argv[2] in ("on", "off"):
        state = read_state()
        state[argv[1]] = argv[2] == "on"
        write_state(state)
        print(json.dumps(read_state()))
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
