"""رندرِ سخت‌گیرانه‌ی قالبِ پیامکِ قدیمی (جایگزینِ ``str.format``).

``str.format`` روی متنِ قابلِ‌ویرایشِ مدیر خطرناک است: ``{customer_name.__class__}``
یا ``{x[0]}`` به ویژگی/ایندکسِ اشیاء دسترسی می‌دهد و ``{amount:>999999}`` می‌تواند
خروجیِ عظیم بسازد. این‌جا فقط این ساختارها مجازند:

* ``{name}`` — ``name`` یک شناسه‌ی ساده (``[A-Za-z_][A-Za-z0-9_]*``) و عضوِ فهرستِ مجاز؛
* ``{{`` و ``}}`` — آکولادِ تحت‌اللفظی (سازگار با رفتارِ قدیمیِ ``str.format``).

هر چیزِ دیگر (نقطه، کروشه، ``!``/``:``، آکولادِ تنها، جای‌گیرِ خالی یا عددی) رد
می‌شود. هیچ expression‌ای ارزیابی نمی‌شود و مقدارها فقط با ``str()`` درج می‌شوند."""

from __future__ import annotations

import re

_TOKEN_RE = re.compile(r"\{\{|\}\}|\{[^{}]*\}|[{}]")
_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


class StrictTemplateError(ValueError):
    """قالب ساختارِ غیرمجاز دارد (``kind="syntax"``) یا متغیرِ ناشناخته (``kind="unknown"``)."""

    def __init__(self, message: str, *, kind: str = "syntax", names: tuple = ()):
        super().__init__(message)
        self.kind = kind
        self.names = names


def _shown(token: str) -> str:
    return token if len(token) <= 40 else token[:37] + "..."


def tokenize(body: str) -> list[tuple[str, str]]:
    """→ فهرستِ ``("text"|"var", مقدار)``. ساختارِ غیرمجاز → ``StrictTemplateError(kind="syntax")``."""
    out: list[tuple[str, str]] = []
    pos = 0
    body = body or ""
    for m in _TOKEN_RE.finditer(body):
        if m.start() > pos:
            out.append(("text", body[pos:m.start()]))
        token = m.group(0)
        pos = m.end()
        if token == "{{":
            out.append(("text", "{"))
        elif token == "}}":
            out.append(("text", "}"))
        elif token in ("{", "}"):
            raise StrictTemplateError(f"آکولادِ نامعتبر در قالب: «{token}» (برایِ آکولادِ ساده از {{{{ و }}}} استفاده کنید)")
        else:
            name = token[1:-1]
            if not _NAME_RE.fullmatch(name):
                raise StrictTemplateError(
                    f"ساختارِ غیرمجاز در قالب: «{_shown(token)}»؛ فقط متغیرِ ساده مثل {{customer_name}} مجاز است "
                    "(دسترسی به ویژگی، ایندکس، قالب‌بندی و عبارت پذیرفته نمی‌شود)."
                )
            out.append(("var", name))
    if pos < len(body):
        out.append(("text", body[pos:]))
    return out


def placeholders(body: str) -> list[str]:
    return [value for kind, value in tokenize(body) if kind == "var"]


def validate(body: str, allowed) -> None:
    allowed = set(allowed)
    unknown = sorted({name for name in placeholders(body) if name not in allowed})
    if unknown:
        raise StrictTemplateError("متغیر ناشناخته در قالب: " + "، ".join(unknown), kind="unknown", names=tuple(unknown))


def render(body: str, values: dict, allowed) -> str:
    """رندرِ امن؛ متغیرِ مجازِ غایب/``None`` رشته‌ی خالی می‌شود (مثلِ رفتارِ قدیمی)."""
    validate(body, allowed)
    parts = []
    for kind, value in tokenize(body):
        if kind == "text":
            parts.append(value)
        else:
            raw = values.get(value)
            parts.append("" if raw is None else str(raw))
    return "".join(parts)


def rename_placeholders(body: str, mapping: dict) -> str:
    """نامِ متغیرها را طبقِ ``mapping`` تغییر می‌دهد (متنِ ثابت و آکولادهایِ تحت‌اللفظی دست‌نخورده)."""
    parts = []
    for kind, value in tokenize(body):
        if kind == "var":
            parts.append("{" + mapping.get(value, value) + "}")
        else:
            parts.append(value.replace("{", "{{").replace("}", "}}"))
    return "".join(parts)
