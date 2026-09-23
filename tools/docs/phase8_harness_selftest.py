#!/usr/bin/env python3
"""Phase 8.2 — archive execution harness self-test (documentation tooling only).

Builds a THROWAWAY git repository in a temporary directory that mimics the
Phase-8 archive-execution manifest layout, then exercises the lifecycle-aware
`--phase8-state` validation and the `--phase8-verify-staged` blob-identity
verifier of ``tools/docs/validate_architecture_docs.py`` in every required
state and failure mode.

It NEVER touches the real repository tree, performs NO archive move in the real
repo, and creates NO docs/archive/** in the real repo. All git operations happen
inside a `tempfile.mkdtemp()` sandbox that is removed on exit.

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

# The fixture manifest header mirrors 13_ARCHIVE_EXECUTION_PATH_MANIFEST.csv.
EXEC_HEADER = (
    "source_path,target_path,source_manifest_record,disposition,batch,sub_batch,"
    "source_root,retained_sibling_exists,incoming_reference_count,canonical_reference,"
    "code_reference,link_break_risk,safe_to_move,reason\n"
)

# A tiny but representative set: two batches (A with sub-batches A1/A2, and B),
# plus one retained sibling that must never move.
FIXTURE_ROWS = [
    # source, target, batch, sub_batch, safe
    ("docs/qa_evidence/dna/a1_one.md", "docs/archive/qa_evidence/dna/a1_one.md", "A", "A1", "TRUE"),
    ("docs/qa_evidence/dna/a1_two.md", "docs/archive/qa_evidence/dna/a1_two.md", "A", "A1", "TRUE"),
    ("docs/qa_evidence/conv/a2_one.md", "docs/archive/qa_evidence/conv/a2_one.md", "A", "A2", "TRUE"),
    ("docs/audits/b_one.md", "docs/archive/audits/b_one.md", "B", "B", "TRUE"),
]
# A retained sibling in the same qa_evidence tree that must stay put.
RETAINED = "docs/qa_evidence/dna/KEEP_readme.md"


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
    """Invoke the real validator against the fixture repo; return (passed, output)."""
    r = run(["python3", TOOL, "--phase8-fixture", repo, *extra])
    out = r.stdout + r.stderr
    passed = ("RESULT: PASS" in out) and (r.returncode == 0)
    return passed, out


def build_fixture():
    repo = tempfile.mkdtemp(prefix="p8harness_")
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "harness@example.com")
    git(repo, "config", "user.name", "harness")
    # manifest
    lines = [EXEC_HEADER]
    for src, tgt, b, sb, safe in FIXTURE_ROWS:
        root = "/".join(src.split("/")[:2])
        lines.append(
            f"{src},{tgt},{src},ARCHIVE_CANDIDATE,{b},{sb},{root},FALSE,0,0,0,NONE,{safe},fixture\n")
    write(repo,
          "docs/architecture_knowledge_system/phase8_archive_dry_run/13_ARCHIVE_EXECUTION_PATH_MANIFEST.csv",
          "".join(lines))
    # source files (unique content so blob identity is meaningful)
    for i, (src, _tgt, _b, _sb, _s) in enumerate(FIXTURE_ROWS):
        write(repo, src, f"content-{i}\nline2-{i}\n")
    write(repo, RETAINED, "retained sibling — must never move\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "fixture baseline")
    return repo


def head(repo):
    return git(repo, "rev-parse", "HEAD").stdout.strip()


def do_move(repo, src, tgt):
    """Perform a real git mv INSIDE THE FIXTURE ONLY (never the real repo)."""
    os.makedirs(os.path.dirname(os.path.join(repo, tgt)), exist_ok=True)
    git(repo, "mv", src, tgt)


results = []


def check(name, condition):
    results.append((name, bool(condition)))
    print(f"  [{'PASS' if condition else 'FAIL'}] {name}")


def main():
    repo = build_fixture()
    try:
        # 1) PRE state: nothing moved -> PASS
        ok, out = validate(repo, "--phase8-state", "pre")
        check("PRE state -> PASS", ok and "completed=0 pending=4" in out)

        # 2) Simulate completing sub-batch A1: move its two files, commit.
        pre = head(repo)
        do_move(repo, FIXTURE_ROWS[0][0], FIXTURE_ROWS[0][1])
        do_move(repo, FIXTURE_ROWS[1][0], FIXTURE_ROWS[1][1])
        # staged-tree verifier BEFORE commit, state A1, pre-head=pre -> PASS
        ok, out = validate(repo, "--phase8-state", "A1",
                           "--phase8-verify-staged", "--phase8-pre-head", pre)
        check("staged A1 pure relocation (blob identity) -> PASS", ok)
        git(repo, "commit", "-q", "-m", "batch A1")

        # 3) After A1 commit, lifecycle state A1 -> PASS (A1 moved; A2,B pending)
        ok, out = validate(repo, "--phase8-state", "A1")
        check("A1 completed lifecycle -> PASS", ok and "completed=2 pending=2" in out)

        # 4) FAIL: completed-batch target missing.
        #    Delete a moved target then re-check state A1 -> FAIL.
        os.remove(os.path.join(repo, FIXTURE_ROWS[0][1]))
        ok, out = validate(repo, "--phase8-state", "A1")
        check("completed target missing -> FAIL", (not ok) and "target absent" in out)
        # restore
        git(repo, "checkout", "-q", "--", FIXTURE_ROWS[0][1])

        # 5) FAIL: pending source missing before its batch is completed.
        #    Remove an A2 source from worktree+index, check state A1 (A2 pending) -> FAIL.
        git(repo, "rm", "-q", FIXTURE_ROWS[2][0])
        ok, out = validate(repo, "--phase8-state", "A1")
        check("pending source missing -> FAIL", (not ok) and "source absent" in out)
        git(repo, "reset", "-q", "--hard", "HEAD")

        # 6) FAIL: extra unrelated staged path during a batch step.
        pre2 = head(repo)
        do_move(repo, FIXTURE_ROWS[2][0], FIXTURE_ROWS[2][1])  # legit A2 move
        write(repo, "docs/qa_evidence/conv/UNRELATED_new.md", "surprise\n")
        git(repo, "add", "docs/qa_evidence/conv/UNRELATED_new.md")
        ok, out = validate(repo, "--phase8-state", "A2",
                           "--phase8-verify-staged", "--phase8-pre-head", pre2)
        check("extra staged path -> FAIL",
              (not ok) and ("unexplained staged addition" in out or "not in authorized batch" in out))
        git(repo, "reset", "-q", "--hard", pre2)

        # 7) FAIL: source/target content mismatch (not a pure relocation).
        pre3 = head(repo)
        do_move(repo, FIXTURE_ROWS[2][0], FIXTURE_ROWS[2][1])
        # corrupt the staged target content, re-stage
        write(repo, FIXTURE_ROWS[2][1], "TAMPERED CONTENT\n")
        git(repo, "add", FIXTURE_ROWS[2][1])
        ok, out = validate(repo, "--phase8-state", "A2",
                           "--phase8-verify-staged", "--phase8-pre-head", pre3)
        check("staged blob content mismatch -> FAIL", (not ok) and "blob mismatch" in out)
        git(repo, "reset", "-q", "--hard", pre3)

        # 8) FAIL: duplicate target in manifest.
        dup_repo = build_fixture()
        try:
            man = os.path.join(
                dup_repo,
                "docs/architecture_knowledge_system/phase8_archive_dry_run/13_ARCHIVE_EXECUTION_PATH_MANIFEST.csv")
            with open(man, "a", encoding="utf-8") as fh:
                # duplicate target of row A2 with a different source
                s, t, b, sb = "docs/qa_evidence/conv/dup_src.md", FIXTURE_ROWS[2][1], "A", "A2"
                fh.write(f"{s},{t},{s},ARCHIVE_CANDIDATE,{b},{sb},docs/qa_evidence,FALSE,0,0,0,NONE,TRUE,dup\n")
            write(dup_repo, "docs/qa_evidence/conv/dup_src.md", "dup\n")
            git(dup_repo, "add", "-A")
            git(dup_repo, "commit", "-q", "-m", "add dup")
            ok, out = validate(dup_repo, "--phase8-state", "pre")
            check("duplicate target -> FAIL", (not ok) and "duplicate target" in out)
        finally:
            shutil.rmtree(dup_repo, ignore_errors=True)

        # 9) FAIL: a row marked safe_to_move != TRUE.
        unsafe_repo = build_fixture()
        try:
            man = os.path.join(
                unsafe_repo,
                "docs/architecture_knowledge_system/phase8_archive_dry_run/13_ARCHIVE_EXECUTION_PATH_MANIFEST.csv")
            txt = open(man, encoding="utf-8").read().replace(
                "docs/audits/b_one.md,docs/archive/audits/b_one.md,docs/audits/b_one.md,"
                "ARCHIVE_CANDIDATE,B,B,docs/audits,FALSE,0,0,0,NONE,TRUE,fixture",
                "docs/audits/b_one.md,docs/archive/audits/b_one.md,docs/audits/b_one.md,"
                "ARCHIVE_CANDIDATE,B,B,docs/audits,FALSE,0,0,0,NONE,FALSE,fixture")
            open(man, "w", encoding="utf-8").write(txt)
            git(unsafe_repo, "add", "-A")
            git(unsafe_repo, "commit", "-q", "-m", "unsafe row")
            ok, out = validate(unsafe_repo, "--phase8-state", "pre")
            check("unsafe row -> FAIL", (not ok) and "safe_to_move=TRUE" in out)
        finally:
            shutil.rmtree(unsafe_repo, ignore_errors=True)

        # 10) Full completion state (all batches) -> PASS.
        #     Complete A2 and B on the main fixture, then check state ABCD-equivalent "AB".
        do_move(repo, FIXTURE_ROWS[2][0], FIXTURE_ROWS[2][1])
        do_move(repo, FIXTURE_ROWS[3][0], FIXTURE_ROWS[3][1])
        git(repo, "commit", "-q", "-m", "batches A2 + B")
        ok, out = validate(repo, "--phase8-state", "AB")
        check("all batches completed (AB) -> PASS",
              ok and "completed=4 pending=0" in out)

        # retained sibling never moved
        check("retained sibling untouched",
              os.path.exists(os.path.join(repo, RETAINED)))
    finally:
        shutil.rmtree(repo, ignore_errors=True)

    print()
    passed = sum(1 for _n, ok in results if ok)
    total = len(results)
    print(f"=== HARNESS SELF-TEST: {passed}/{total} cases behaved as expected ===")
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
