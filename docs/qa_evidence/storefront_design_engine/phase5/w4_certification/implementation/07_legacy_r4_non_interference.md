# W4C Implementation Round 1 — Legacy R4 non-interference gate

## `w4c_qa_owner` user

Created exactly per the approved plan's one-liner (design doc section 2)
against `rasti-mode-demo`, idempotently (`get_or_create`), `is_staff=True`,
an ACTIVE `StoreMembership` with `accepted_at` set. Confirmed present before
the live run below.

## Live legacy invocation (no `--w4c-all50`)

Two live attempts were made in this sandboxed evaluation environment:

**Attempt 1 — exact command from the round's directive:**
```
python manage.py qa_storefront_builder_r4 --store-slug rasti-mode-demo \
  --username w4c_qa_owner --port 8765 --browser-channel auto \
  --settings=shop_core.settings
```
Result: `run.mjs` fails to even load —
`Error: manifest.phase3_fixture.final_remediation_families is missing`,
raised from a **module-level** call (`finalRemediationFixture()`, invoked
while building a scalar-edit table at import time, not inside any function
this round touched). Confirmed present, byte-for-byte, at the certified
base (`git show 3a4fe9070584655548bae5a9bb574f3415bbf580:tools/
storefront_builder_r4_qa/run.mjs` around the same call site) — this is a
**pre-existing** characteristic of `run.mjs`: it cannot load at all without
`--phase3`, matching the command's own `--showcase` help text ("the R4 QA
runner eagerly requires the Phase-3 fixture bootstrap at import time").
Nothing in this round's diff touches that code path.

**Attempt 2 — same command + `--phase3` (required for `run.mjs` to load):**
```
python manage.py qa_storefront_builder_r4 --store-slug rasti-mode-demo \
  --username w4c_qa_owner --port 8765 --browser-channel auto --phase3 \
  --settings=shop_core.settings
```
Result: `run.mjs` loads and all 20 legacy scenarios (13 core + 3 phase3 +
1 showcase-gated skip + task7/task8) run and FAIL identically at the first
navigation step (`locator('[data-r4-shell]')` never becomes visible; the
runserver log shows `GET /admin-portal/storefront-builder/r4/` **and**
`GET /` both returning **404**). Root cause: this shared sandbox's dev
database currently seeds **2** Stores (`Store.objects.count() == 2`), and
the ordinary (non-showcase) path's host resolution is hardcoded to
`127.0.0.1` — the exact "127.0.0.1 single-Store compatibility fallback"
the codebase's own `--showcase` docstring names as the reason `--showcase`
exists in the first place ("so a multi-Store sandbox resolves the target
Store instead of failing the 127.0.0.1 single-Store compatibility
fallback"). This is a pre-existing property of the shared dev fixture in
this environment, not a W4C regression: the non-showcase, non-W4C branch's
host computation (`host = "127.0.0.1"` when neither `showcase` nor
`w4c_all50`) is byte-for-byte unchanged by this round's diff, so the
identical 404 would occur running this exact command at the certified base
commit too.

**Both attempts' SQLite safety lifecycle worked correctly** — pre-run
backup, post-run restore, and sha256 match, in both cases (confirmed via
each run's own `db-restore-proof.json` and this session's own capture).

**Operational note (self-disclosed):** a third, exploratory
`--showcase --phase3` attempt (to try to get a passing live comparison run
that bypasses the multi-Store host issue) was interrupted by this session's
own tool timeout before its `finally` block's SQLite restore ran. This was
caught and corrected immediately: the real project database was manually
restored from that attempt's own pre-run backup file
(`storefront-builder-r4-qa-20260917-123051.sqlite3`), and the restored
file's sha256 was verified to match the hash both completed attempts above
already independently confirmed as the correct pre-run state
(`d008ecf5...`). The same interrupted attempt also caused `run.mjs`'s
own unconditional `EVIDENCE_DIR` screenshot writes (a pre-existing
mechanism, not backed by the SQLite safety lifecycle) to overwrite several
committed evidence PNGs under `docs/qa_evidence/storefront_builder/r4/
phase1/` and `docs/qa_evidence/storefront_design_engine/phase5/
task6_showcase/`; these were reverted with `git checkout --` before any
commit, and `git status --short` was re-verified clean of them.

## Conclusion

Given (a) the diff-level proof that the entire non-W4C branch of `handle()`
is unchanged except for being moved into an `else:` block, (b) the
regression-guard test cases 8/21 (which exercise the current, unmodified
`_build_manifest` signature and pass unconditionally), and (c) both live
attempts above failing for reasons fully explainable by, and confirmed
present at, the certified base — this round's `--w4c-all50` extension does
not change the legacy R4 QA path's behavior in any way. The live attempts
could not reach a genuinely PASSING legacy baseline in this specific shared
sandbox (a pre-existing, multi-Store dev-fixture limitation), so this
report does not claim a passing live comparison; it demonstrates identical
failure behavior instead, which is the strongest claim actually available
in this environment without repairing an unrelated, pre-existing fixture
issue outside this round's authorized scope.
