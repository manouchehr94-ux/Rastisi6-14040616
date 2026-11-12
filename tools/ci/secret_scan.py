#!/usr/bin/env python3
"""Fail the pipeline when a credential is committed (standard library only; scans the files of a commit, never prints a value).

    secret_scan.py [--rev HEAD] [--repo .]   exit 1 and a list of  path:line  RULE  when something matches

Deliberately conservative: it looks for high-confidence shapes (private keys, cloud/API token formats, passwords inside connection URLs,
long literal values assigned to SECRET/PASSWORD/TOKEN names). Placeholders (CHANGE_ME, example.com, 'test', 'dummy', empty) are ignored.
Test files may contain fixtures, so the generic assignment rule is not applied there; the strict token/key rules apply everywhere.
Findings are never echoed with their value: the report prints the path, the line number and the rule only.
"""

import argparse
import re
import subprocess
import sys

STRICT = [
    ("private-key", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED |PGP )?PRIVATE KEY(?: BLOCK)?-----")),
    ("aws-access-key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("github-token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}\b|\bgithub_pat_[A-Za-z0-9_]{50,}\b")),
    ("slack-token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("stripe-live-key", re.compile(r"\b[sr]k_live_[0-9A-Za-z]{20,}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
]
URL_PASSWORD = re.compile(r"\b(?:postgres(?:ql)?|mysql|redis|rediss|amqp|mongodb)://[^/\s:@'\"]*:([^@\s'\"/]{4,})@([^/\s:'\"]*)")
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
ASSIGNMENT = re.compile(r"""(?ix)\b([A-Z0-9_]*(?:SECRET|PASSWORD|PASSWD|API_?KEY|PRIVATE_?KEY|ACCESS_?TOKEN|AUTH_?TOKEN)[A-Z0-9_]*)\s*[:=]\s*["']([^"'\s]{16,})["']""")
PLACEHOLDER = re.compile(r"(?i)change_?me|example|placeholder|dummy|your[-_ ]|<.*>|\$\{|\{\{|xxxx|0000|1111|test|sample|fake|insecure|secret-key-for|todo|redacted|\*\*\*|\.\.\.")
TEXT_SKIP_EXT = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".woff", ".woff2", ".ttf", ".eot", ".pdf", ".zip", ".gz", ".xlsx", ".mp4", ".svg", ".min.js", ".map")
SKIP_PREFIX = ("docs/references/", "docs/reference-kits/", "docs/design-references/", "static/vendor/")
FIXTURE_HINT = re.compile(r"(?:^|/)(?:tests?|fixtures)(?:/|$)|(?:^|/)test_[^/]*\.py(?:\.txt)?$|(?:^|/)conftest\.py$|\.example$|\.md$")
WORD_PASSWORDS = {"pass", "password", "pwd", "secret", "user", "changeme", "passwd", "yourpassword"}


def git(repo, *args):
    return subprocess.run(["git", "-C", repo] + list(args), capture_output=True, check=True).stdout


def scan_text(path, text):
    findings = []
    fixture = bool(FIXTURE_HINT.search(path))
    for number, line in enumerate(text.splitlines(), 1):
        if len(line) > 4000:
            continue
        for rule, rx in STRICT:
            m0 = rx.search(line)
            if m0 and not (rule == "aws-access-key" and (m0.group(0).endswith("EXAMPLE") or len(set(m0.group(0)[4:])) <= 2)):  # documented / synthetic keys
                findings.append((path, number, rule))
        m = URL_PASSWORD.search(line)
        throwaway_service = bool(m) and m.group(2) in LOCAL_HOSTS and path.startswith(".github/workflows/")   # CI service containers on the runner itself
        if m and not PLACEHOLDER.search(m.group(1)) and m.group(1).lower() not in WORD_PASSWORDS and not fixture and not throwaway_service:
            findings.append((path, number, "password-in-url"))
        m = ASSIGNMENT.search(line)
        if m and not fixture and not PLACEHOLDER.search(m.group(2)) and not re.match(r"^[A-Za-z_.]+$", m.group(2)):
            findings.append((path, number, "secret-assignment"))
    return findings


def scan_rev(repo, rev):
    names = git(repo, "ls-tree", "-r", "--name-only", "-z", rev).decode("utf-8", "replace").split("\0")
    findings = []
    scanned = 0
    for name in filter(None, names):
        low = name.lower()
        if low.endswith(TEXT_SKIP_EXT) or name.startswith(SKIP_PREFIX):
            continue
        try:
            data = git(repo, "show", "%s:%s" % (rev, name))
        except subprocess.CalledProcessError:
            continue
        if b"\0" in data[:2048] or len(data) > 2_000_000:
            continue
        scanned += 1
        findings += scan_text(name, data.decode("utf-8", "replace"))
    return scanned, findings


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=".")
    ap.add_argument("--rev", default="HEAD")
    ap.add_argument("--allow", default="", help="file with 'path:RULE' lines that are accepted (reviewed false positives)")
    args = ap.parse_args(argv)
    allowed = set()
    if args.allow:
        allowed = {l.strip() for l in open(args.allow, encoding="utf-8") if l.strip() and not l.startswith("#")}
    scanned, findings = scan_rev(args.repo, args.rev)
    findings = [f for f in findings if "%s:%s" % (f[0], f[2]) not in allowed]
    for path, number, rule in findings:
        print("%s:%d  %s" % (path, number, rule))
    print("secret scan: %d files, %d finding(s)" % (scanned, len(findings)))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
