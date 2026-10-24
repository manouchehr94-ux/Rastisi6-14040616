"""Target definition of the two demo stores (``rebuild/manifests/demo_stores.json``)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from django.conf import settings

DEFAULT_TARGETS_PATH = Path(settings.BASE_DIR) / "rebuild" / "manifests" / "demo_stores.json"


@dataclass(frozen=True)
class TargetStore:
    key: str
    slug: str
    name: str
    admin_subdomain: str
    hostname: str
    expected: dict = field(default_factory=dict)


def load_targets(path: Path | None = None) -> dict[str, TargetStore]:
    data = json.loads(Path(path or DEFAULT_TARGETS_PATH).read_text(encoding="utf-8"))
    out = {}
    for key, raw in data["stores"].items():
        out[key] = TargetStore(
            key=key,
            slug=raw["slug"],
            name=raw["name"],
            admin_subdomain=raw["admin_subdomain"],
            hostname=raw["hostname"],
            expected=dict(raw.get("reported_previous_deployment", {})),
        )
    return out
