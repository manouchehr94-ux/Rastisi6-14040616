"""A tiny structured report shared by validator, importer and integrity checker.

Each finding is PASS / WARN / FAIL / BLOCKED. ``BLOCKED`` means "could not be
evaluated because a required input is missing" - it is never folded into PASS.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

PASS, WARN, FAIL, BLOCKED = "PASS", "WARN", "FAIL", "BLOCKED"


@dataclass
class Finding:
    level: str
    code: str
    message: str
    store: str = ""


@dataclass
class Report:
    title: str
    findings: list[Finding] = field(default_factory=list)

    def add(self, level: str, code: str, message: str, store: str = "") -> None:
        self.findings.append(Finding(level, code, message, store))

    def ok(self, code, message, store=""):
        self.add(PASS, code, message, store)

    def warn(self, code, message, store=""):
        self.add(WARN, code, message, store)

    def fail(self, code, message, store=""):
        self.add(FAIL, code, message, store)

    def blocked(self, code, message, store=""):
        self.add(BLOCKED, code, message, store)

    def extend(self, other: "Report") -> None:
        self.findings.extend(other.findings)

    def of(self, level: str) -> list[Finding]:
        return [f for f in self.findings if f.level == level]

    @property
    def failed(self) -> bool:
        return bool(self.of(FAIL))

    @property
    def blocked_any(self) -> bool:
        return bool(self.of(BLOCKED))

    @property
    def status(self) -> str:
        if self.failed:
            return FAIL
        if self.blocked_any:
            return BLOCKED
        return PASS

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "status": self.status,
            "findings": [f.__dict__ for f in self.findings],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    def to_text(self, *, show_pass: bool = True) -> str:
        lines = [f"== {self.title} -> {self.status}"]
        for f in self.findings:
            if f.level == PASS and not show_pass:
                continue
            where = f" [{f.store}]" if f.store else ""
            lines.append(f"  {f.level:7s} {f.code}{where}: {f.message}")
        return "\n".join(lines)
