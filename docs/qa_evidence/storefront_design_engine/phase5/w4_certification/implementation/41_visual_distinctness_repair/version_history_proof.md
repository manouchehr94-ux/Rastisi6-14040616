# Version History Preservation Proof

Verified via the new `OutgoingHistoryRemainsResolvableTests` in
`test_a8_visual_distinctness_repair.py` (13/13, then 17/17 after the
code-review correction — see `tdd_green.txt`) and independently
re-confirmed here:

| key | latest version | v2 resolvable | v1 resolvable |
|---|---|---|---|
| `green_workshop` | 3 | YES (`hero=editorial_split`, byte-identical to the old certified v2) | YES (pre-existing) |
| `laleh_play` | 3 | YES (`hero=image_collage`, byte-identical to the old certified v2) | YES (pre-existing) |
| `parnian_editorial` | 3 | YES (`hero=immersive`, byte-identical to the old certified v2) | YES (pre-existing) |

Mechanism: exact, byte-for-byte outgoing v2 `_RecipeSpec` rows were added
to `_HISTORICAL_SPECS` (the same tuple already holding each of these
three keys' pre-existing v1 row), registered through the identical
`register_layout_preset`/`_build` authority used everywhere else in this
file. `register_layout_preset` raises `InvalidLayoutPresetError` on any
duplicate `(key, version)` identity and always promotes
`LAYOUT_PRESET_REGISTRY[key]` to the numerically-highest registered
version regardless of registration order — so v3 (in `_SPECS`) is
correctly latest, while v2 and v1 (both in `_HISTORICAL_SPECS`) remain
independently resolvable forever via `get_layout_preset_version(key, "2")`
/ `get_layout_preset_version(key, "1")`. No second history registry was
introduced; no existing historical entry (including the pre-existing v1
rows for these same three keys, and every other key's history) was
touched.

Canonical Ready Template count: still exactly 50 (`_SPECS` still has 50
rows; only 3 were edited in place, none added/removed).
