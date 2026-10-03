# W4B — Certified W4A historical fingerprint capture

**Captured at:** git HEAD `fac7e3653ad07d5df5c9e4210137171134d7f90f` on
`feature/phase5-w4b-template-curation` (docs-only commit; `apps/` was, at
capture time, byte-identical to the certified official checkpoint
`707dd631e851bdd13173bf3950489142f3e526b1` — no production file had been
touched yet).

**Environment:** `/usr/bin/python3` (3.11.15) + Django 5.2.17, installed
this session (`pip3 install --user Django jdatetime Pillow requests
cryptography` — `psycopg` intentionally left uninstalled; it is a
production-only Postgres driver per `requirements.txt`'s own comment and
is not needed for SQLite-backed tests). `python manage.py check` and
`makemigrations --check --dry-run` both passed clean against the
certified base before this capture, confirming the environment matches
production expectations.

**Method:** exactly the fingerprint algorithm from the approved design
(`docs/superpowers/specs/2026-09-16-phase5-w4b-50-template-curation-design.md`
§11 / inventory §7): `dataclasses.asdict(preset)` → deterministic
recursive freeze (dict → sorted tuple of (key, frozen-value) pairs;
list/tuple → tuple of frozen items; set/frozenset → sorted tuple of frozen
items; everything else passed through) → `repr(...)` → SHA-256 hex digest.
Run via `manage.py`-equivalent Django setup
(`DJANGO_SETTINGS_MODULE=shop_core.settings`), reading
`lpr.get_layout_preset_version(key, "1")` for each of the 21 curated
keys directly from the untouched, certified `layout_preset_registry.py` +
`a8_ready_templates.py`.

**Script** (kept here as evidence, not committed as a tool — it duplicates
the approved design's own fingerprint function verbatim and introduces no
new production logic):

```python
import os, django, dataclasses, hashlib
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "shop_core.settings")
django.setup()

from apps.storefront_builder import layout_preset_registry as lpr

CURATED_KEYS = (
    "premium_leather_noir", "artisan_grain", "coastal_product", "handmade_luxe",
    "watchmaker_round", "horizon_story", "silk_editorial", "city_classic",
    "kamand_artisan", "parnian_editorial", "niloufar_glass", "beauty_dew",
    "laleh_play", "almas_luxury", "green_workshop", "pine_eco", "mirror_beauty",
    "cedar_home", "simorgh_market", "rayan_tech", "harbor_imports",
)
assert len(CURATED_KEYS) == 21

def _deep_freeze(value):
    if isinstance(value, dict):
        return tuple(sorted((k, _deep_freeze(v)) for k, v in value.items()))
    if isinstance(value, (list, tuple)):
        return tuple(_deep_freeze(v) for v in value)
    if isinstance(value, (set, frozenset)):
        return tuple(sorted(_deep_freeze(v) for v in value))
    return value

def fingerprint(preset) -> str:
    frozen = _deep_freeze(dataclasses.asdict(preset))
    return hashlib.sha256(repr(frozen).encode()).hexdigest()

result = {}
for key in CURATED_KEYS:
    preset = lpr.get_layout_preset_version(key, "1")
    assert preset is not None, key
    assert preset.version == "1", (key, preset.version)
    result[(key, "1")] = fingerprint(preset)
```

**Raw captured output:** `00_certified_w4a_fingerprints_output.txt`
(same directory) — the exact `CERTIFIED_W4A_FINGERPRINT` dict literal
pasted verbatim into the new RED test module
(`apps/storefront_builder/tests/test_w4b_template_curation.py`,
`test_historical_fingerprint_contract`). These values are captured **once,
here, before curation**, and are never regenerated after
`a8_ready_templates.py` is edited — per the design's explicit rule.
