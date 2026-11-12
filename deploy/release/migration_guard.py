#!/usr/bin/env python3
"""Classify the Django migrations a release would apply (standard library only).

Used twice, with the same rules:
  * in CI / the release workflow, on the git diff between the currently deployed commit and the commit to release;
  * on the server, to check that the migrations Django is about to apply are exactly the ones the reviewed report announced.

Levels (worst wins):
  NONE         no migration file added, changed or removed
  ADDITIVE     only operations that an N-1 application can run next to (new tables, new nullable or db_default columns, new indexes)
  REVIEW       data migrations, constraints, field alterations, anything the guard cannot prove additive
  DESTRUCTIVE  drops or renames data, edits an already-published migration, raw SQL that deletes, or anything irreversible

Rollback policy that follows from the level (see ``rollback_safe``): only NONE and ADDITIVE allow an automatic code rollback.
"""

import argparse
import ast
import json
import re
import subprocess
import sys
from pathlib import Path

LEVELS = ("NONE", "ADDITIVE", "REVIEW", "DESTRUCTIVE")

_DESTRUCTIVE_OPS = {
    "RemoveField", "DeleteModel", "RenameField", "RenameModel", "AlterModelTable", "AlterOrderWithRespectTo",
}
_ADDITIVE_OPS = {
    "CreateModel", "AddIndex", "AlterModelOptions", "AlterModelManagers",
    "CreateExtension", "AlterIndexTogether",
}
_REVIEW_OPS = {
    "AlterField", "AddConstraint", "AlterUniqueTogether", "RunPython", "RunSQL", "SeparateDatabaseAndState", "AlterModelTableComment",
    "RenameIndex", "RemoveConstraint", "RemoveIndex",
}
_SQL_DESTRUCTIVE = re.compile(r"(?i)\b(DROP|TRUNCATE|DELETE\s+FROM|ALTER\s+TABLE\s+\S+\s+DROP|UPDATE\s+\S+\s+SET)\b")


def _op_name(call):
    func = call.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def _kw(call, name):
    for kw in call.keywords:
        if kw.arg == name:
            return kw.value
    return None


def _field_is_n_minus_1_safe(field_call):
    """True when the PREVIOUS release can keep INSERTing rows without knowing the new column.

    Only ``null=True`` and ``db_default=...`` qualify. A plain ``default=...`` does NOT: Django adds the column with that default and then
    DROPS the database default, so an older application that omits the column hits a NOT NULL violation. Many-to-many fields live in
    their own table and are always safe."""
    if not isinstance(field_call, ast.Call):
        return False
    null = _kw(field_call, "null")
    if isinstance(null, ast.Constant) and null.value is True:
        return True
    default = _kw(field_call, "db_default")
    if isinstance(default, ast.Constant) and default.value is not None:
        return True
    return _op_name(field_call) in {"ManyToManyField"}


def _string_args(node):
    out = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            out.append(sub.value)
    return out


def analyze_source(source, filename="<migration>"):
    """Return a list of findings ``{"op", "level", "why"}`` for one migration's source code."""
    try:
        tree = ast.parse(source, filename)
    except SyntaxError as exc:
        return [{"op": "<syntax>", "level": "DESTRUCTIVE", "why": "migration does not parse: %s" % exc.msg}]
    findings = []
    # Resolve imports without executing migration code. Only recognised Django
    # operations in a literal list can establish N-1 compatibility.
    aliases = {}
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module:
            for item in node.names:
                aliases[item.asname or item.name] = node.module + "." + item.name
        elif isinstance(node, ast.Import):
            for item in node.names:
                aliases[item.asname or item.name.split('.')[0]] = item.name if item.asname else item.name.split('.')[0]

    def canonical(node):
        if isinstance(node, ast.Name):
            return aliases.get(node.id, node.id)
        if isinstance(node, ast.Attribute):
            return canonical(node.value) + '.' + node.attr
        return ''

    known = _DESTRUCTIVE_OPS | _ADDITIVE_OPS | _REVIEW_OPS | {'AddField'}
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'Migration']
    operations = []
    def review(op, why):
        findings.append({'op': op, 'level': 'REVIEW', 'why': why})
    if len(classes) != 1 or not any(canonical(b) == 'django.db.migrations.Migration' for b in classes[0].bases):
        review('<structure>', 'unrecognised Migration class')
    for cls in classes:
        assignments = {t.id: n.value for n in cls.body if isinstance(n, ast.Assign) for t in n.targets if isinstance(t, ast.Name)}
        atomic = assignments.get('atomic')
        if atomic is not None and not (isinstance(atomic, ast.Constant) and atomic.value is True):
            review('<atomic>', 'non-atomic or dynamic transaction policy')
        ops = assignments.get('operations')
        if not isinstance(ops, (ast.List, ast.Tuple)):
            review('<operations>', 'operations must be a literal list')
            continue
        for operation in ops.elts:
            full = canonical(operation.func) if isinstance(operation, ast.Call) else ''
            name = full.rsplit('.', 1)[-1]
            if name not in known or not full.startswith('django.db.migrations.'):
                review(name or '<dynamic>', 'unknown or dynamic operation')
            else:
                operations.append(operation)
        for key in assignments:
            if key not in {'operations', 'dependencies', 'initial', 'atomic', 'replaces', 'run_before'}:
                review('<class-binding>', 'unexpected Migration class binding')
        for node in cls.body:
            if not isinstance(node, (ast.Assign, ast.Pass)) and not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)):
                review('<class-code>', 'dynamic Migration class needs review')
            if isinstance(node, ast.Assign) and any(not isinstance(t, ast.Name) for t in node.targets):
                review('<assignment>', 'dynamic class assignment')
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name != 'Migration':
            review('<helper-class>', 'executable helper class needs review')
        if isinstance(node, ast.ImportFrom) and not (node.module or '').startswith('django.'):
            review('<import>', 'non-Django import needs review')
        if isinstance(node, ast.Import) and any(not n.name.startswith('django.') and n.name != 'django' for n in node.names):
            review('<import>', 'non-Django import needs review')
        if not isinstance(node, (ast.Import, ast.ImportFrom, ast.ClassDef)) and not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)):
            review('<module-code>', 'executable module code needs review')
    for node in operations:
        if not isinstance(node, ast.Call):
            continue
        name = canonical(node.func).rsplit(".", 1)[-1]
        if name == "AddField":
            field = node.args[2] if len(node.args) >= 3 else _kw(node, "field")
            field_type = canonical(field.func) if isinstance(field, ast.Call) else ''
            if not field_type.startswith('django.db.models.'):
                findings.append({'op': name, 'level': 'REVIEW', 'why': 'custom or dynamic field'})
            elif _field_is_n_minus_1_safe(field):
                findings.append({"op": name, "level": "ADDITIVE", "why": "new nullable (or db_default) column"})
            else:
                findings.append({"op": name, "level": "REVIEW", "why": "new NOT NULL column without a database default: the previous release's INSERTs omit it and would fail"})
        elif name in _DESTRUCTIVE_OPS:
            findings.append({"op": name, "level": "DESTRUCTIVE", "why": "drops or renames existing data/structure"})
        elif name == "RunPython":
            reverse = _kw(node, "reverse_code")
            if reverse is None and len(node.args) < 2:
                findings.append({"op": name, "level": "DESTRUCTIVE", "why": "data migration without reverse_code (irreversible)"})
            else:
                findings.append({"op": name, "level": "REVIEW", "why": "data migration; read the code"})
        elif name == "RunSQL":
            forward = node.args[0] if node.args else _kw(node, "sql")          # reverse_sql legitimately contains DROP
            sql = " ".join(_string_args(forward)) if forward is not None else ""
            reverse = _kw(node, "reverse_sql")
            if _SQL_DESTRUCTIVE.search(sql):
                findings.append({"op": name, "level": "DESTRUCTIVE", "why": "raw SQL that drops, deletes or rewrites rows"})
            elif reverse is None and len(node.args) < 2:
                findings.append({"op": name, "level": "DESTRUCTIVE", "why": "raw SQL without reverse_sql (irreversible)"})
            else:
                findings.append({"op": name, "level": "REVIEW", "why": "raw SQL; read the code"})
        elif name in _REVIEW_OPS:
            findings.append({"op": name, "level": "REVIEW", "why": "cannot be proven compatible with the previous release"})
        elif name in _ADDITIVE_OPS:
            findings.append({"op": name, "level": "ADDITIVE", "why": "additive"})
        elif name in {"AlterField"}:
            findings.append({"op": name, "level": "REVIEW", "why": "field alteration"})
    return findings


def worst(levels):
    rank = {lvl: i for i, lvl in enumerate(LEVELS)}
    return max(levels, key=lambda x: rank[x]) if levels else "NONE"


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo)] + list(args), capture_output=True, text=True, check=False)


def analyze_range(repo, from_sha, to_sha):
    """Compare two commits. ``from_sha`` may be empty (first release): every migration is then treated as new."""
    if from_sha:
        proc = _git(repo, "diff", "--name-status", "--no-renames", "%s..%s" % (from_sha, to_sha), "--", "*/migrations/*.py")
        if proc.returncode != 0:
            raise RuntimeError("git diff failed: " + proc.stderr.strip())
        lines = proc.stdout.splitlines()
    else:                                    # first release: every migration in the tree counts as new
        proc = _git(repo, "ls-tree", "-r", "--name-only", to_sha)
        if proc.returncode != 0:
            raise RuntimeError("git ls-tree failed: " + proc.stderr.strip())
        lines = ["A\t" + n for n in proc.stdout.splitlines() if "/migrations/" in n and n.endswith(".py")]
    files = []
    levels = []
    for line in lines:
        status, _, path = line.partition("\t")
        if not path or path.endswith("__init__.py"):
            continue
        entry = {"path": path, "status": status, "findings": []}
        if status == "A":
            show = _git(repo, "show", "%s:%s" % (to_sha, path))
            entry["findings"] = analyze_source(show.stdout, path)
            entry["level"] = worst([f["level"] for f in entry["findings"]]) if entry["findings"] else "REVIEW"
        elif status == "M":
            entry["level"] = "DESTRUCTIVE"
            entry["findings"] = [{"op": "<edited>", "level": "DESTRUCTIVE",
                                  "why": "an already-published migration was edited; databases that applied it will not re-run it"}]
        elif status == "D":
            entry["level"] = "DESTRUCTIVE"
            entry["findings"] = [{"op": "<deleted>", "level": "DESTRUCTIVE", "why": "a published migration was removed"}]
        else:
            entry["level"] = "REVIEW"
        levels.append(entry["level"])
        files.append(entry)
    level = worst(levels)
    new_names = sorted("%s.%s" % (app_label_of(f["path"]), Path(f["path"]).stem) for f in files if f["status"] == "A")
    return {
        "from_sha": from_sha, "to_sha": to_sha, "level": level, "files": files,
        "new_migrations": new_names,
        "rollback_safe": level in ("NONE", "ADDITIVE"),
        "requires_allow_migrations": level in ("REVIEW", "DESTRUCTIVE"),
        "requires_destructive_ack": level == "DESTRUCTIVE",
        "destructive_ack_phrase": "I-ACCEPT-DESTRUCTIVE-MIGRATION-%s" % to_sha[:12] if level == "DESTRUCTIVE" else "",
    }


def app_label_of(path):
    """``apps/billing/migrations/0011_x.py`` -> ``billing``."""
    parts = Path(path).parts
    return parts[parts.index("migrations") - 1]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", default=".")
    ap.add_argument("--from", dest="from_sha", default="", help="commit currently deployed (empty = first release)")
    ap.add_argument("--to", dest="to_sha", required=True)
    ap.add_argument("--out", help="write the JSON report here")
    args = ap.parse_args(argv)
    report = analyze_range(args.repo, args.from_sha, args.to_sha)
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
