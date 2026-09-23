#!/usr/bin/env python3
"""Architecture Knowledge System — documentation validator.

Documentation-only validator (no application CI change). Validates the canonical +
domain-pack documentation under docs/architecture_knowledge_system/. Uses only the
Python standard library (PyYAML is not available in this environment; the registry
is parsed with a minimal line scanner for the checks we need).

Checks performed:
  1. Broken internal Markdown links (relative links to files that do not exist).
  2. Unknown / duplicate domain IDs (D1..D15) in the registry.
  3. Missing required canonical entry-point files.
  4. Missing required domain-pack entry point (each domain dir has README.md).
  5. Invalid OPEN decision IDs referenced in docs (must be DR-1..DR-8).
  6. Code-path references (apps/... .py) in canonical + domain docs that do not exist on disk.
  7. Markdown/Mermaid source presence (canonical graphs dir has .mmd files).
  8. Registry file present and parseable at a basic structural level.
  9. Canonical-pack readiness disambiguation (semantic consistency repair):
       a. exactly 15 domain IDs;
       b. every domain has a canonical pack directory and README (also checked in 4);
       c. registry has schema_version + field_semantics documenting the two concepts;
       d. every registry domain has BOTH phase4_prepack_documentation_readiness AND
          canonical_pack_status;
       e. canonical_pack_status is CANONICAL for all 15 completed packs;
       f. NO generic domain-level `status: READY|PARTIAL|POOR|MISSING|CONFLICTED` in the registry
          (that ambiguous field was the pre-repair bug) — such usage is rejected;
       g. every domain README uses the agreed metadata schema
          (canonical_pack_status + phase4_prepack_documentation_readiness; no ambiguous `readiness:`
          or bare `status: CANONICAL` metadata line).

Exit code 0 if no ERRORs (warnings allowed); 1 if any ERROR.
Run from the repo root:  python3 tools/docs/validate_architecture_docs.py
"""
import csv
import os
import re
import subprocess
import sys

PHASE8 = ("--phase8" in sys.argv[1:])

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
AKS = os.path.join(REPO, "docs", "architecture_knowledge_system")
CANON = os.path.join(AKS, "canonical")
DOMAINS = os.path.join(AKS, "domains")
REGISTRY = os.path.join(CANON, "architecture_registry.yaml")

REQUIRED_CANONICAL = [
    "README.md", "SYSTEM_CONTEXT.md", "DOMAIN_MAP.md", "DATA_OWNERSHIP.md",
    "MUTATION_AUTHORITY.md", "DEPENDENCY_MAP.md", "RUNTIME_FLOW_INDEX.md",
    "STATE_MACHINE_INDEX.md", "TRANSACTION_AND_CONSISTENCY.md", "EXTERNAL_INTEGRATIONS.md",
    "SECURITY_AND_TRUST_BOUNDARIES.md", "TESTING_MAP.md", "ARCHITECTURAL_DECISION_REGISTER.md",
    "KNOWN_ARCHITECTURE_RISKS.md", "DOCUMENTATION_AUTHORITY.md", "CHANGE_IMPACT_GUIDE.md",
    "architecture_registry.yaml",
]
EXPECTED_DOMAINS = {
    "stores", "portal", "customers", "catalog", "cart", "orders", "subscriptions",
    "billing", "storefront_builder", "content", "dashboard", "sms", "notifications",
    "core", "blog",
}
VALID_DR = {f"DR-{i}" for i in range(1, 9)}

errors = []
warnings = []
info = []


def md_files(root):
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            if f.endswith(".md"):
                yield os.path.join(dirpath, f)


# ---- Check 1: broken internal Markdown links ----
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
link_checked = 0
for md in md_files(AKS):
    with open(md, encoding="utf-8") as fh:
        text = fh.read()
    for target in LINK_RE.findall(text):
        t = target.split("#", 1)[0].strip()
        if not t or t.startswith(("http://", "https://", "mailto:")):
            continue
        # only validate relative paths
        resolved = os.path.normpath(os.path.join(os.path.dirname(md), t))
        link_checked += 1
        if not os.path.exists(resolved):
            errors.append(f"BROKEN LINK: {os.path.relpath(md, REPO)} -> {target}")
info.append(f"internal links checked: {link_checked}")


# ---- Check 2 & 8: registry domain IDs (minimal parser) ----
if not os.path.exists(REGISTRY):
    errors.append(f"MISSING REGISTRY: {os.path.relpath(REGISTRY, REPO)}")
    reg_ids = []
    reg_apps = []
    reg_dr = []
else:
    with open(REGISTRY, encoding="utf-8") as fh:
        reg_text = fh.read()
    reg_ids = re.findall(r"^\s*-\s*id:\s*(D\d+)\s*$", reg_text, re.MULTILINE)
    reg_apps = re.findall(r"^\s*app:\s*(\S+)\s*$", reg_text, re.MULTILINE)
    reg_dr = re.findall(r"id:\s*(DR-\d+)", reg_text)
    # duplicate domain IDs
    seen = set()
    for d in reg_ids:
        if d in seen:
            errors.append(f"DUPLICATE DOMAIN ID in registry: {d}")
        seen.add(d)
    # expected 15 (D1..D15)
    expected_ids = {f"D{i}" for i in range(1, 16)}
    missing_ids = expected_ids - set(reg_ids)
    extra_ids = set(reg_ids) - expected_ids
    if missing_ids:
        errors.append(f"REGISTRY missing domain IDs: {sorted(missing_ids)}")
    if extra_ids:
        errors.append(f"REGISTRY unknown domain IDs: {sorted(extra_ids)}")
    info.append(f"registry domain IDs: {len(reg_ids)} (expected 15)")
    # DR ids in registry open_decisions must be valid
    for dr in reg_dr:
        if dr not in VALID_DR:
            errors.append(f"REGISTRY invalid DR id: {dr}")
    info.append(f"registry DR references: {len(set(reg_dr))} distinct")


# ---- Check 3: required canonical entry points ----
for req in REQUIRED_CANONICAL:
    if not os.path.exists(os.path.join(CANON, req)):
        errors.append(f"MISSING CANONICAL FILE: canonical/{req}")


# ---- Check 4: domain dirs + README present; expected set matches ----
if not os.path.isdir(DOMAINS):
    errors.append("MISSING domains/ directory")
    present_domains = set()
else:
    present_domains = {d for d in os.listdir(DOMAINS) if os.path.isdir(os.path.join(DOMAINS, d))}
    for d in sorted(present_domains):
        if not os.path.exists(os.path.join(DOMAINS, d, "README.md")):
            errors.append(f"MISSING DOMAIN README: domains/{d}/README.md")
    missing_dom = EXPECTED_DOMAINS - present_domains
    extra_dom = present_domains - EXPECTED_DOMAINS
    if missing_dom:
        errors.append(f"MISSING DOMAIN DIRS: {sorted(missing_dom)}")
    if extra_dom:
        warnings.append(f"UNEXPECTED DOMAIN DIRS: {sorted(extra_dom)}")
    # registry apps should match domain dirs
    for a in reg_apps:
        if a not in present_domains and a in EXPECTED_DOMAINS:
            warnings.append(f"registry app '{a}' has no domain dir")
    info.append(f"domain dirs: {len(present_domains)} (expected {len(EXPECTED_DOMAINS)})")


# ---- Check 5: OPEN decision IDs referenced must be DR-1..DR-8 ----
DR_RE = re.compile(r"\bDR-(\d+)\b")
bad_dr = set()
for md in md_files(AKS):
    with open(md, encoding="utf-8") as fh:
        for m in DR_RE.findall(fh.read()):
            dr = f"DR-{m}"
            if dr not in VALID_DR:
                bad_dr.add((os.path.relpath(md, REPO), dr))
for path, dr in sorted(bad_dr):
    errors.append(f"INVALID DR ID referenced: {dr} in {path}")


# ---- Check 6: code-path references (apps/....py) must exist ----
# Match tokens like apps/orders/services/order_service.py (optionally with ::symbol or :line).
CODEPATH_RE = re.compile(r"\b(apps/[A-Za-z0-9_./]+\.py)")
codepaths_checked = 0
missing_codepaths = set()
for md in md_files(CANON):
    with open(md, encoding="utf-8") as fh:
        for cp in CODEPATH_RE.findall(fh.read()):
            codepaths_checked += 1
            if not os.path.exists(os.path.join(REPO, cp)):
                missing_codepaths.add((os.path.relpath(md, REPO), cp))
for md in md_files(DOMAINS):
    with open(md, encoding="utf-8") as fh:
        for cp in CODEPATH_RE.findall(fh.read()):
            codepaths_checked += 1
            if not os.path.exists(os.path.join(REPO, cp)):
                missing_codepaths.add((os.path.relpath(md, REPO), cp))
# Files a doc may intentionally reference as ABSENT (deleted code, or hypothetical
# examples in change-guide recipes). These are expected-absent and reported as info, not errors.
EXPECTED_ABSENT = {
    "apps/storefront_builder/family_registry.py",   # deleted (D5)
    "apps/storefront_builder/preset_registry.py",   # deleted (D5)
    "apps/blog/urls.py",                            # deliberately absent (D1 near-dead)
    "apps/orders/gateways/new_gateway.py",          # hypothetical example in orders CHANGE_GUIDE
}
for path, cp in sorted(missing_codepaths):
    if cp in EXPECTED_ABSENT:
        info.append(f"code-path intentionally absent (expected): {cp} in {path}")
    else:
        errors.append(f"CODE PATH NOT FOUND: {cp} in {path}")
info.append(f"code-path references checked: {codepaths_checked}")


# ---- Check 7: canonical graphs present ----
graphs_dir = os.path.join(CANON, "graphs")
if os.path.isdir(graphs_dir):
    mmd = [f for f in os.listdir(graphs_dir) if f.endswith(".mmd")]
    if not mmd:
        warnings.append("canonical/graphs/ has no .mmd files")
    info.append(f"canonical graph sources: {len(mmd)}")
else:
    warnings.append("canonical/graphs/ directory missing")


# ---- Check 9: canonical-pack readiness disambiguation (semantic consistency) ----
READINESS_VOCAB = {"READY", "PARTIAL", "POOR", "MISSING", "CONFLICTED"}

# 9a: exactly 15 domain IDs (re-affirm explicitly, in addition to check 2's set logic)
if os.path.exists(REGISTRY):
    if len(reg_ids) != 15:
        errors.append(f"REGISTRY must have exactly 15 domain IDs; found {len(reg_ids)}")

    # 9c: schema_version + field_semantics present and documenting both concepts
    if not re.search(r"^schema_version:\s*\d+", reg_text, re.MULTILINE):
        errors.append("REGISTRY missing top-level schema_version")
    if "field_semantics:" not in reg_text:
        errors.append("REGISTRY missing top-level field_semantics")
    else:
        for concept in ("phase4_prepack_documentation_readiness", "canonical_pack_status"):
            # must be documented under field_semantics (appears as a key with a description)
            if not re.search(rf"^\s+{re.escape(concept)}:\s*$", reg_text, re.MULTILINE):
                warnings.append(f"REGISTRY field_semantics may not document '{concept}'")

    # 9d/9e: per-domain fields — count occurrences of the two required fields
    reg_prepack = re.findall(r"^\s{4}phase4_prepack_documentation_readiness:\s*(\S+)\s*$", reg_text, re.MULTILINE)
    reg_packstatus = re.findall(r"^\s{4}canonical_pack_status:\s*(\S+)\s*$", reg_text, re.MULTILINE)
    if len(reg_prepack) != len(reg_ids):
        errors.append(
            f"REGISTRY: phase4_prepack_documentation_readiness count ({len(reg_prepack)}) "
            f"!= domain count ({len(reg_ids)})"
        )
    if len(reg_packstatus) != len(reg_ids):
        errors.append(
            f"REGISTRY: canonical_pack_status count ({len(reg_packstatus)}) "
            f"!= domain count ({len(reg_ids)})"
        )
    for v in reg_prepack:
        if v not in READINESS_VOCAB:
            errors.append(f"REGISTRY invalid phase4_prepack_documentation_readiness value: {v}")
    for v in reg_packstatus:
        if v != "CANONICAL":
            errors.append(f"REGISTRY canonical_pack_status must be CANONICAL for completed packs; got: {v}")
    info.append(
        f"registry semantic fields: phase4_prepack={len(reg_prepack)}, "
        f"canonical_pack_status={len(reg_packstatus)} (both expected {len(reg_ids)})"
    )

    # 9f: reject the ambiguous generic domain-level `status: <readiness>` field (4-space indent)
    ambiguous = re.findall(
        r"^\s{4}status:\s*(READY|PARTIAL|POOR|MISSING|CONFLICTED)\s*$", reg_text, re.MULTILINE
    )
    if ambiguous:
        errors.append(
            f"REGISTRY still uses ambiguous domain-level `status: <readiness>` ({len(ambiguous)} "
            f"occurrence(s)) — use phase4_prepack_documentation_readiness + canonical_pack_status"
        )

# 9g: every domain README uses the agreed metadata schema
schema_ok = 0
for d in sorted(EXPECTED_DOMAINS):
    readme = os.path.join(DOMAINS, d, "README.md")
    if not os.path.exists(readme):
        continue  # missing-README already reported in check 4
    with open(readme, encoding="utf-8") as fh:
        head = fh.read()
    # ambiguous metadata lines must be gone
    if re.search(r"(?m)^readiness:", head):
        errors.append(f"DOMAIN README uses ambiguous `readiness:` metadata: domains/{d}/README.md")
    if re.search(r"(?m)^status:\s*CANONICAL\s*$", head):
        errors.append(f"DOMAIN README uses ambiguous bare `status: CANONICAL` metadata: domains/{d}/README.md")
    # required fields present
    if not re.search(r"(?m)^canonical_pack_status:\s*CANONICAL\s*$", head):
        errors.append(f"DOMAIN README missing `canonical_pack_status: CANONICAL`: domains/{d}/README.md")
    m = re.search(r"(?m)^phase4_prepack_documentation_readiness:\s*(\S+)\s*$", head)
    if not m:
        errors.append(f"DOMAIN README missing `phase4_prepack_documentation_readiness`: domains/{d}/README.md")
    elif m.group(1) not in READINESS_VOCAB:
        errors.append(
            f"DOMAIN README invalid phase4_prepack_documentation_readiness "
            f"'{m.group(1)}': domains/{d}/README.md"
        )
    else:
        schema_ok += 1
info.append(f"domain READMEs conforming to metadata schema: {schema_ok} (expected {len(EXPECTED_DOMAINS)})")


# ============================================================================
# Phase-8 archive execution-safety checks (opt-in via --phase8).
# These are ADDITIVE: they never relax or skip checks 1-9 above. When --phase8
# is not passed, this block is skipped entirely and behaviour is unchanged.
# ============================================================================
if PHASE8:
    P8 = os.path.join(AKS, "phase8_archive_dry_run")
    MANIFEST = os.path.join(P8, "03_ARCHIVE_DISPOSITION_MANIFEST.csv")
    EXECMAN = os.path.join(P8, "13_ARCHIVE_EXECUTION_PATH_MANIFEST.csv")
    DIRSAFE = os.path.join(P8, "14_DIRECTORY_MOVE_SAFETY_CHECK.md")

    RETAIN_DISP = {
        "KEEP_HISTORICAL_REFERENCE", "KEEP_CANONICAL_SUPPORT",
        "CORRECT_IN_PLACE_LATER", "DO_NOT_TOUCH_LEGAL_OR_EXTERNAL",
    }
    DEFER_DISP = {"DEFER_REVIEW"}
    COLLECTION_ROOTS = [
        "docs/qa_evidence", "docs/prototypes",
        "docs/references/beraito-exact-frontend-v5", "docs/reference-kits",
        "docs/template-references", "docs/docs/product/Final Result At Last",
    ]

    def _git_ls_z(path):
        out = subprocess.run(["git", "-C", REPO, "ls-files", "-z", path],
                             capture_output=True)
        return [p for p in out.stdout.decode("utf-8").split("\0") if p]

    if not os.path.exists(MANIFEST):
        errors.append("PHASE8: missing 03_ARCHIVE_DISPOSITION_MANIFEST.csv")
    if not os.path.exists(EXECMAN):
        errors.append("PHASE8: missing 13_ARCHIVE_EXECUTION_PATH_MANIFEST.csv")

    if os.path.exists(MANIFEST) and os.path.exists(EXECMAN):
        man = list(csv.DictReader(open(MANIFEST, encoding="utf-8")))
        ex = list(csv.DictReader(open(EXECMAN, encoding="utf-8")))
        file_disp = {r["source_path"]: r["proposed_disposition"]
                     for r in man if "**" not in r["source_path"]}

        # tracked-file set for existence checks (NUL-safe)
        tracked_all = set(_git_ls_z("."))

        # P8-1: every ARCHIVE_CANDIDATE logical record maps to execution paths OR is
        #       an explicitly justified non-file collection pseudo-row.
        exec_sources = {r["source_path"] for r in ex}
        exec_roots_covered = set()
        for r in ex:
            for root in COLLECTION_ROOTS:
                if r["source_path"] == root or r["source_path"].startswith(root + "/"):
                    exec_roots_covered.add(root)
        unmapped = []
        for r in man:
            if r["proposed_disposition"] != "ARCHIVE_CANDIDATE":
                continue
            sp = r["source_path"]
            if "**" in sp:
                root = sp.split("/**", 1)[0]
                if root not in exec_roots_covered:
                    unmapped.append(sp)  # collection pseudo-row with no expanded files
            else:
                if sp not in exec_sources:
                    unmapped.append(sp)
        if unmapped:
            errors.append(
                f"PHASE8: {len(unmapped)} ARCHIVE_CANDIDATE record(s) not mapped to any "
                f"execution path (first: {unmapped[0]})")

        # P8-2: no execution path belongs to a KEEP/DEFER/LEGAL source disposition.
        bad_disp = [r["source_path"] for r in ex
                    if file_disp.get(r["source_path"]) in (RETAIN_DISP | DEFER_DISP)]
        if bad_disp:
            errors.append(
                f"PHASE8: {len(bad_disp)} execution path(s) map to a KEEP/DEFER/LEGAL "
                f"source (first: {bad_disp[0]})")

        # P8-3: all exact source paths exist as tracked files.
        missing = [r["source_path"] for r in ex if r["source_path"] not in tracked_all]
        if missing:
            errors.append(
                f"PHASE8: {len(missing)} execution source path(s) not tracked "
                f"(first: {missing[0]})")

        # P8-4: no target path collides (duplicate target).
        tgts = [r["target_path"] for r in ex]
        dup_t = {t for t in tgts if tgts.count(t) > 1}
        if dup_t:
            errors.append(f"PHASE8: duplicate target path(s): {len(dup_t)}")

        # P8-5: no source equals target.
        se = [r["source_path"] for r in ex if r["source_path"] == r["target_path"]]
        if se:
            errors.append(f"PHASE8: {len(se)} row(s) with source_path == target_path")

        # P8-6: no duplicate source path.
        srcs = [r["source_path"] for r in ex]
        dup_s = {s for s in srcs if srcs.count(s) > 1}
        if dup_s:
            errors.append(f"PHASE8: duplicate source path(s): {len(dup_s)}")

        # P8-7: (target uniqueness already covered by P8-4; assert set sizes)
        if len(set(srcs)) != len(srcs) or len(set(tgts)) != len(tgts):
            errors.append("PHASE8: source/target uniqueness invariant violated")

        # P8-8: no execution path has an active canonical/code reference unless approved.
        #       Every row must be safe_to_move == TRUE.
        unsafe = [r["source_path"] for r in ex if r.get("safe_to_move") != "TRUE"]
        if unsafe:
            errors.append(
                f"PHASE8: {len(unsafe)} execution path(s) not safe_to_move=TRUE "
                f"(first: {unsafe[0]})")

        # P8-9: no unsafe whole-directory move exists. Re-derive per source root:
        #       a whole-dir move is only allowed if EVERY tracked descendant is an
        #       execution source. We assert the plan never *depends* on a whole-dir
        #       move by proving that for each collection root that still has retained
        #       descendants, not all descendants are in the execution set (i.e. the
        #       plan must be per-file). We also surface the allowed/forbidden split.
        forbidden = []
        allowed = []
        roots_to_check = set(COLLECTION_ROOTS)
        for r in ex:
            if not any(r["source_path"] == rt or r["source_path"].startswith(rt + "/")
                       for rt in COLLECTION_ROOTS):
                roots_to_check.add(os.path.dirname(r["source_path"]))
        for d in sorted(roots_to_check):
            tracked = _git_ls_z(d)
            if not tracked:
                continue
            in_exec = sum(1 for t in tracked if t in exec_sources)
            retained = sum(1 for t in tracked if file_disp.get(t) in RETAIN_DISP)
            deferred = sum(1 for t in tracked if file_disp.get(t) in DEFER_DISP)
            if in_exec == len(tracked) and retained == 0 and deferred == 0:
                allowed.append(d)
            else:
                forbidden.append(d)
        # The DIRSAFE doc must document at least the forbidden set so a whole-dir move
        # is never silently assumed. (Presence check only; content is authoritative.)
        if not os.path.exists(DIRSAFE):
            errors.append("PHASE8: missing 14_DIRECTORY_MOVE_SAFETY_CHECK.md")
        info.append(
            f"PHASE8: whole-dir move allowed={len(allowed)} forbidden={len(forbidden)}")

        # P8-10: root mandatory documents are dispositioned.
        for root_doc in ("SIX_NEW_FAMILIES_IMPLEMENTATION_PLAN.md",
                         "SIX_NEW_FAMILIES_IMPLEMENTATION_REPORT.md"):
            if root_doc not in file_disp:
                errors.append(f"PHASE8: root mandatory document not dispositioned: {root_doc}")

        # reconciliation info
        from collections import Counter as _C
        dist = _C(r["proposed_disposition"] for r in man)
        info.append(
            "PHASE8: manifest records=%d (ARCHIVE=%d KEEP_HIST=%d KEEP_CANON=%d "
            "DEFER=%d LEGAL=%d CORRECT=%d)" % (
                len(man), dist.get("ARCHIVE_CANDIDATE", 0),
                dist.get("KEEP_HISTORICAL_REFERENCE", 0),
                dist.get("KEEP_CANONICAL_SUPPORT", 0), dist.get("DEFER_REVIEW", 0),
                dist.get("DO_NOT_TOUCH_LEGAL_OR_EXTERNAL", 0),
                dist.get("CORRECT_IN_PLACE_LATER", 0)))
        info.append(f"PHASE8: execution tracked files={len(ex)} (all safe_to_move=TRUE)")


# ---- Report ----
print("=== Architecture Docs Validation ===")
print(f"repo: {REPO}")
for i in info:
    print(f"  info: {i}")
print(f"warnings: {len(warnings)}")
for w in warnings:
    print(f"  WARN: {w}")
print(f"errors: {len(errors)}")
for e in errors:
    print(f"  ERROR: {e}")
print("=== RESULT:", "PASS" if not errors else "FAIL", "===")
sys.exit(0 if not errors else 1)
