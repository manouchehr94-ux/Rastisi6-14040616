"""Rendering signature of a storefront page, used to prove that a converted +
imported store looks exactly like its source.

The signature captures what a visitor (and the design) depends on: visible text,
links, image URLs, stylesheet/script URLs, a hash of every inline ``<style>``
block (theme colours/fonts live there) and the multiset of element/class pairs
(layout structure). It deliberately ignores CSRF tokens and script bodies.

Integer ids that a renumbering legitimately shifted (``offset < n < offset+stride``)
are shifted back in attribute/URL contexts only - never in visible text, so a
price can never be mistaken for an id.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

_NUM = re.compile(r"(?<![\d.])(\d{1,10})(?!\d)")
_URL_IN_STYLE = re.compile(r"url\(([^)]+)\)")


def _deshift(value: str, offset: int, stride: int) -> str:
    if not offset:
        return value

    def repl(match):
        n = int(match.group(1))
        return str(n - offset) if offset < n < offset + stride else match.group(0)

    return _NUM.sub(repl, value)


def _norm_url(url: str, host: str, offset: int, stride: int, rename: dict[str, str]) -> str:
    url = (url or "").strip().strip("'\"")
    parts = urlsplit(url)
    if parts.netloc and parts.netloc.lower() == host.lower():
        url = url[len(parts.scheme) + 3 + len(parts.netloc):] or "/"
    for new, old in rename.items():
        if new in url:
            url = url.replace(new, old)
    return _deshift(url, offset, stride)


def _srcset(value: str | None) -> list[str]:
    return [chunk.strip().split(" ")[0] for chunk in (value or "").split(",") if chunk.strip()]


def page_signature(html: str, *, host: str, offset: int = 0, stride: int = 1, rename: dict[str, str] | None = None) -> dict:
    rename = rename or {}
    soup = BeautifulSoup(html, "html.parser")
    styles = []
    for tag in soup.find_all("style"):
        styles.append(" ".join(tag.get_text().split()))
    scripts = sorted(_norm_url(t["src"], host, offset, stride, rename) for t in soup.find_all("script", src=True))
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = " ".join(soup.get_text(" ").split())

    def nu(u):
        return _norm_url(u, host, offset, stride, rename)

    links = sorted({nu(a["href"]) for a in soup.find_all("a", href=True)})
    sheets = sorted({nu(link["href"]) for link in soup.find_all("link", href=True)})
    imgs = set()
    for img in soup.find_all(["img", "source"]):
        for attr in ("src", "data-src"):
            if img.get(attr):
                imgs.add(nu(img[attr]))
        for u in _srcset(img.get("srcset")) + _srcset(img.get("data-srcset")):
            imgs.add(nu(u))
    inline_urls = set()
    for tag in soup.find_all(style=True):
        for u in _URL_IN_STYLE.findall(tag["style"]):
            inline_urls.add(nu(u))
    structure = Counter()
    for tag in soup.find_all(True):
        classes = ".".join(sorted(_deshift(c, offset, stride) for c in (tag.get("class") or [])))
        ident = _deshift(tag.get("id") or "", offset, stride)
        data = ",".join(sorted(
            f"{k}={_deshift(str(v), offset, stride)}" for k, v in tag.attrs.items()
            if k.startswith("data-") and k not in ("data-src", "data-srcset") and not isinstance(v, list)
        ))
        structure[f"{tag.name}|{classes}|{ident}|{data}"] += 1
    style_attr_hash = hashlib.sha256(
        "\n".join(sorted(_deshift(t["style"], offset, stride) for t in soup.find_all(style=True))).encode()
    ).hexdigest()
    return {
        "title": " ".join((soup.title.get_text() if soup.title else "").split()),
        "text": text,
        "links": links,
        "images": sorted(imgs | inline_urls),
        "sheets": sheets,
        "scripts": scripts,
        "style_blocks": hashlib.sha256("\n".join(styles).encode()).hexdigest(),
        "style_attrs": style_attr_hash,
        "structure": dict(structure),
    }


def diff_signatures(a: dict, b: dict) -> list[str]:
    """Human-readable differences between two signatures (empty = identical)."""
    out = []
    for key in ("title", "text", "style_blocks", "style_attrs"):
        if a[key] != b[key]:
            if key == "text":
                x, y = a[key].split(), b[key].split()
                i = next((n for n, (p, q) in enumerate(zip(x, y)) if p != q), min(len(x), len(y)))
                out.append(f"text differs near word {i}: {' '.join(x[i:i + 6])!r} vs {' '.join(y[i:i + 6])!r}")
            else:
                out.append(f"{key} differs")
    for key in ("links", "images", "sheets", "scripts"):
        sa, sb = set(a[key]), set(b[key])
        if sa != sb:
            out.append(f"{key}: only-in-source={sorted(sa - sb)[:3]} only-in-import={sorted(sb - sa)[:3]}")
    if a["structure"] != b["structure"]:
        ca, cb = Counter(a["structure"]), Counter(b["structure"])
        out.append(f"structure: -{sum((ca - cb).values())} +{sum((cb - ca).values())} element(s), e.g. {list((ca - cb))[:2]} / {list((cb - ca))[:2]}")
    return out
