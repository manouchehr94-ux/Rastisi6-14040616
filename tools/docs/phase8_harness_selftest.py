#!/usr/bin/env python3
"""Phase 8.2/8.3 — archive execution harness self-test (documentation tooling only).

Builds a THROWAWAY git repository in a temporary directory that mimics the
Phase-8 archive-execution manifest layout, then exercises the lifecycle-aware
``--phase8-state`` validation, the sequential current-sub-batch delta model
(``--phase8-current-sub-batch`` / ``--phase8-state-before``), and the
``--phase8-verify-staged`` blob-identity verifier of
``tools/docs/validate_architecture_docs.py`` in every required state and failure
mode — including the Phase-8.3 SEQUENTIAL cases (a second staged sub-batch after
the first is committed).

It NEVER touches the real repository tree, performs NO archive move in the real
repo, and creates NO docs/archive/** in the real repo. All git operations happen
inside a ``tempfile.mkdtemp()`` sandbox that is removed on exit.

Run:  python3 tools/docs/phase8_harness_selftest.py
Exit 0 if all cases behave as expected; 1 otherwise.
"""
import os
import shutil
import subprocess
import sys
import tempfile

TOOL = os.path.abspath(__file__).replace("phase8_harness_selftest.py",
                                         "validate_architecture_docs.py")

EXEC_HEADER = (
    "source_path,target_path,source_manifest_record,disposition,batch,sub_batch,"
    "source_root,retained_sibling_exists,incoming_reference_count,canonical_reference,"
    "code_reference,link_break_risk,safe_to_move,reason\n"
)

# Fixture uses the SAME canonical unit ids as the real plan. Small-first order
# means A6 executes before A5. We model two sequential units A6 (2 files) then
# A5 (2 files), plus one retained sibling that must never move.
#   sub_batch A6: 2 files   |   sub_batch A5: 2 files
FIXTURE_ROWS = [
    # source, target, batch, sub_batch
    ("docs/qa_evidence/uiux/a6_one.md", "docs/archive/qa_evidence/uiux/a6_one.md", "A", "A6"),
    ("docs/qa_evidence/uiux/a6_two.md", "docs/archive/qa_evidence/uiux/a6_two.md", "A", "A6"),
    ("docs/qa_evidence/site/a5_one.md", "docs/archive/qa_evidence/site/a5_one.md", "A", "A5"),
    ("docs/qa_evidence/site/a5_two.md", "docs/archive/qa_evidence/site/a5_two.md", "A", "A5"),
]
RETAINED = "docs/qa_evidence/uiux/KEEP_readme.md"


def run(cmd, cwd=None):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def git(repo, *args):
    return run(["git", "-C", repo, *args])


def write(repo, relpath, content):
    p = os.path.join(repo, relpath)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(content)


def validate(repo, *extra):
    r = run(["python3", TOOL, "--phase8-fixture", repo, *extra])
    out = r.stdout + r.stderr
    passed = ("RESULT: PASS" in out) and (r.returncode == 0)
    return passed, out


def build_fixture(rows=FIXTURE_ROWS):
    repo = tempfile.mkdtemp(prefix="p8seq_")
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "harness@example.com")
    git(repo, "config", "user.name", "harness")
    lines = [EXEC_HEADER]
    for src, tgt, b, sb in rows:
        root = "/".join(src.split("/")[:2])
        lines.append(
            f"{src},{tgt},{src},ARCHIVE_CANDIDATE,{b},{sb},{root},FALSE,0,0,0,NONE,TRUE,fixture\n")
    write(repo,
          "docs/architecture_knowledge_system/phase8_archive_dry_run/13_ARCHIVE_EXECUTION_PATH_MANIFEST.csv",
          "".join(lines))
    for i, (src, _t, _b, _sb) in enumerate(rows):
        write(repo, src, f"content-{i}\nline2-{i}\n")
    write(repo, RETAINED, "retained sibling — must never move\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "fixture baseline")
    return repo


def head(repo):
    return git(repo, "rev-parse", "HEAD").stdout.strip()


def do_move(repo, src, tgt):
    os.makedirs(os.path.dirname(os.path.join(repo, tgt)), exist_ok=True)
    git(repo, "mv", src, tgt)


results = []


def check(name, condition):
    results.append((name, bool(condition)))
    print(f"  [{'PASS' if condition else 'FAIL'}] {name}")


def rows_for(repo, unit):
    return [(s, t) for s, t, _b, sb in FIXTURE_ROWS if sb == unit]


def main():
    # ================= SEQUENTIAL PASS PATH (A6 then A5) =================
    repo = build_fixture()
    try:
        # 1. PRE -> PASS
        ok, out = validate(repo, "--phase8-state", "pre")
        check("PRE -> PASS", ok and "pending=4" in out)

        # 2. stage A6 (current=A6, before=pre, after=A6) -> staged verify PASS
        pre = head(repo)
        for s, t in rows_for(repo, "A6"):
            do_move(repo, s, t)
        ok, out = validate(repo, "--phase8-state", "A6", "--phase8-state-before", "pre",
                           "--phase8-current-sub-batch", "A6",
                           "--phase8-verify-staged", "--phase8-pre-head", pre)
        check("stage A6 (current=A6) blob-identity -> PASS", ok)

        # 3. commit A6
        git(repo, "commit", "-q", "-m", "sub-batch A6")

        # 4. lifecycle A6 -> PASS (A6 moved; A5 pending)
        ok, out = validate(repo, "--phase8-state", "A6")
        check("lifecycle A6 -> PASS", ok and "completed=2 pending=2" in out)

        # 5. stage A5 (before=A6, current=A5, after=A6A5) -> staged verify PASS
        pre2 = head(repo)
        for s, t in rows_for(repo, "A5"):
            do_move(repo, s, t)
        ok, out = validate(repo, "--phase8-state", "A6A5", "--phase8-state-before", "A6",
                           "--phase8-current-sub-batch", "A5",
                           "--phase8-verify-staged", "--phase8-pre-head", pre2)
        check("stage A5 after A6 committed (current=A5) -> PASS", ok)

        # 6. prove A6 is NOT required/allowed to be staged during A5:
        #    the staged tree contains ONLY A5 moves; verifier expected exactly A5.
        #    (Confirm no A6 path is staged now.)
        staged = git(repo, "diff", "--cached", "--name-only").stdout
        check("A6 NOT staged during A5",
              ("a6_one.md" not in staged) and ("a5_one.md" in staged))

        # 7. commit A5
        git(repo, "commit", "-q", "-m", "sub-batch A5")

        # 8. lifecycle A6A5 -> PASS (all four moved)
        ok, out = validate(repo, "--phase8-state", "A6A5")
        check("lifecycle A6A5 -> PASS", ok and "completed=4 pending=0" in out)

        # retained sibling never moved across the whole sequence
        check("retained sibling untouched", os.path.exists(os.path.join(repo, RETAINED)))
    finally:
        shutil.rmtree(repo, ignore_errors=True)

    # ================= SEQUENTIAL FAIL: WRONG CURRENT =================
    # A6 committed, A5 staged, but verifier is told current=A6 (the already-done unit).
    repo = build_fixture()
    try:
        pre = head(repo)
        for s, t in rows_for(repo, "A6"):
            do_move(repo, s, t)
        git(repo, "commit", "-q", "-m", "A6")
        pre2 = head(repo)
        for s, t in rows_for(repo, "A5"):
            do_move(repo, s, t)
        # WRONG: current=A6 while A5 is what's staged
        ok, out = validate(repo, "--phase8-state", "A6A5", "--phase8-state-before", "A6",
                           "--phase8-current-sub-batch", "A6",
                           "--phase8-verify-staged", "--phase8-pre-head", pre2)
        check("A5 staged but current=A6 -> FAIL",
              (not ok) and ("PHASE8-DELTA" in out or "PHASE8-STAGED" in out))
    finally:
        shutil.rmtree(repo, ignore_errors=True)

    # ================= SEQUENTIAL FAIL: PRIOR UNIT RE-STAGED =================
    # A6 committed; while staging A5, also re-stage an A6 file (target modified back).
    repo = build_fixture()
    try:
        pre = head(repo)
        for s, t in rows_for(repo, "A6"):
            do_move(repo, s, t)
        git(repo, "commit", "-q", "-m", "A6")
        pre2 = head(repo)
        for s, t in rows_for(repo, "A5"):
            do_move(repo, s, t)
        # re-touch a committed A6 target and stage it (a prior-unit path in the delta)
        a6_tgt = rows_for(repo, "A6")[0][1]
        write(repo, a6_tgt, "content-0\nline2-0\nEXTRA\n")
        git(repo, "add", a6_tgt)
        ok, out = validate(repo, "--phase8-state", "A6A5", "--phase8-state-before", "A6",
                           "--phase8-current-sub-batch", "A5",
                           "--phase8-verify-staged", "--phase8-pre-head", pre2)
        check("A5 staged + re-staged A6 file -> FAIL",
              (not ok) and "PHASE8-STAGED" in out)
    finally:
        shutil.rmtree(repo, ignore_errors=True)

    # ================= SEQUENTIAL FAIL: UNRELATED STAGED =================
    repo = build_fixture()
    try:
        pre = head(repo)
        for s, t in rows_for(repo, "A6"):
            do_move(repo, s, t)
        git(repo, "commit", "-q", "-m", "A6")
        pre2 = head(repo)
        for s, t in rows_for(repo, "A5"):
            do_move(repo, s, t)
        write(repo, "docs/qa_evidence/site/UNRELATED.md", "surprise\n")
        git(repo, "add", "docs/qa_evidence/site/UNRELATED.md")
        ok, out = validate(repo, "--phase8-state", "A6A5", "--phase8-state-before", "A6",
                           "--phase8-current-sub-batch", "A5",
                           "--phase8-verify-staged", "--phase8-pre-head", pre2)
        check("A5 staged + unrelated file -> FAIL",
              (not ok) and "unexplained staged addition" in out)
    finally:
        shutil.rmtree(repo, ignore_errors=True)

    # ================= SEQUENTIAL FAIL: TARGET BLOB MODIFIED =================
    repo = build_fixture()
    try:
        pre = head(repo)
        for s, t in rows_for(repo, "A6"):
            do_move(repo, s, t)
        git(repo, "commit", "-q", "-m", "A6")
        pre2 = head(repo)
        s0, t0 = rows_for(repo, "A5")[0]
        do_move(repo, s0, t0)
        # stage the other A5 move cleanly
        s1, t1 = rows_for(repo, "A5")[1]
        do_move(repo, s1, t1)
        # tamper t0 content and re-stage -> blob mismatch
        write(repo, t0, "TAMPERED\n")
        git(repo, "add", t0)
        ok, out = validate(repo, "--phase8-state", "A6A5", "--phase8-state-before", "A6",
                           "--phase8-current-sub-batch", "A5",
                           "--phase8-verify-staged", "--phase8-pre-head", pre2)
        check("A5 target blob modified -> FAIL", (not ok) and "blob mismatch" in out)
    finally:
        shutil.rmtree(repo, ignore_errors=True)

    # ================= TRANSITION-ORDER FAIL (skip A6, do A5 first) =============
    repo = build_fixture()
    try:
        pre = head(repo)
        for s, t in rows_for(repo, "A5"):
            do_move(repo, s, t)
        # Illegal: before=pre, current=A5 (A6 must be first per canonical order)
        ok, out = validate(repo, "--phase8-state", "A5", "--phase8-state-before", "pre",
                           "--phase8-current-sub-batch", "A5",
                           "--phase8-verify-staged", "--phase8-pre-head", pre)
        check("out-of-order (A5 before A6) -> FAIL",
              (not ok) and "out-of-sequence" in out)
    finally:
        shutil.rmtree(repo, ignore_errors=True)

    # ================= PARSER FAIL CASES (garbage states) =================
    repo = build_fixture()
    try:
        for bad in ["A1XYZ", "A1-BOGUS", "Q1", "A99", "A6A6", "A5A6", "A6X"]:
            ok, out = validate(repo, "--phase8-state", bad)
            check(f"invalid state '{bad}' -> FAIL", (not ok) and "invalid state" in out)
        # a VALID cumulative state still parses/PASSes at pre-move fixture? No — files
        # for A6 are not moved in this fresh fixture, so lifecycle would FAIL; instead
        # assert the PARSER accepts it (no 'invalid state' error) even if lifecycle fails.
        ok, out = validate(repo, "--phase8-state", "A6A5")
        check("valid state 'A6A5' parses (no parser error)",
              "invalid state" not in out)
    finally:
        shutil.rmtree(repo, ignore_errors=True)

    # ================= WRONG-CURRENT: verify-staged without current =============
    repo = build_fixture()
    try:
        pre = head(repo)
        for s, t in rows_for(repo, "A6"):
            do_move(repo, s, t)
        ok, out = validate(repo, "--phase8-state", "A6", "--phase8-state-before", "pre",
                           "--phase8-verify-staged", "--phase8-pre-head", pre)
        check("verify-staged without --phase8-current-sub-batch -> FAIL",
              (not ok) and "requires --phase8-current-sub-batch" in out)
    finally:
        shutil.rmtree(repo, ignore_errors=True)

    print()
    passed = sum(1 for _n, ok in results if ok)
    total = len(results)
    print(f"=== SEQUENTIAL HARNESS SELF-TEST: {passed}/{total} cases behaved as expected ===")
    if passed == total:
        print("=== RESULT: PASS ===")
        return 0
    print("=== RESULT: FAIL ===")
    for n, ok in results:
        if not ok:
            print(f"  UNEXPECTED: {n}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
