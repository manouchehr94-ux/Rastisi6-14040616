"""Recover media that a source ZIP does not contain - with recorded provenance.

A source media ZIP can lack files the database still references (thumbnails that
were never copied, category images that lived outside the exported folder, ...).
The validator rightly refuses such a bundle (``media.missing_at_export``).  This
module is the *only* way those references are made whole, and it never guesses:

``ORIGINAL``              the file came out of the operator's own inputs (the media ZIP,
                          the same file under another path in that ZIP, or the optional
                          ``--extra-media-dir`` supplied by the operator).
``RECOVERED_FROM_REPO``   byte-identical copy of a committed asset under
                          ``apps/stores/demo_assets/rasti_mode_demo/curated/`` whose
                          checksum matches ``SHA256SUMS.txt`` and whose *database file name*
                          is exactly the name ``refresh_rasti_mode_demo_visuals`` gives it.
``REGENERATED_DERIVATIVE``a deterministic derivative produced by the real application code
                          (thumbnail: ``product_image_service``; V5 category cover: the seed
                          command's ``_composite_visual_bytes`` over the committed product
                          photos) - never a stand-in image.
``UNRECOVERABLE``         nothing above applies.  The reference stays missing, the validator
                          keeps reporting ``BLOCKED`` and the bundle is not built.

Rules that keep this honest:

* A file is only recovered when its database path *proves* what it is (file-name pattern
  written by the original command + the owning row's name/slug).  A hand-uploaded
  ``categories/images/kafsh.jpg`` matches nothing and is therefore ``UNRECOVERABLE``.
* The database value (path + extension) is never changed.  If the bytes of a repo asset
  are another format than the extension, they are transcoded and the file is classed
  ``REGENERATED_DERIVATIVE`` (``transcode_repo_asset``) - not ``RECOVERED_FROM_REPO``.
* Nothing is written here: the caller receives bytes and places them in its temp dir.
"""

from __future__ import annotations

import importlib
import json
import posixpath
import re
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Callable

from .files import UnsafeMediaPath, safe_relative_media_path, sha256_bytes

ORIGINAL = "ORIGINAL"
RECOVERED_FROM_REPO = "RECOVERED_FROM_REPO"
REGENERATED_DERIVATIVE = "REGENERATED_DERIVATIVE"
UNRECOVERABLE = "UNRECOVERABLE"
CLASSES = (ORIGINAL, RECOVERED_FROM_REPO, REGENERATED_DERIVATIVE, UNRECOVERABLE)

CURATED_REL = Path("demo_assets") / "rasti_mode_demo" / "curated"
_FORMAT_BY_EXT = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG", ".webp": "WEBP"}
#: ``FileSystemStorage`` appends ``_`` + 7 random characters when a name is already taken
_DJANGO_SUFFIX = r"(?:_[A-Za-z0-9]{7})?"


def default_curated_dir() -> Path:
    import apps.stores

    return Path(apps.stores.__file__).resolve().parent / CURATED_REL


@dataclass
class Provenance:
    """What is known about ONE referenced file (``path`` is the database value)."""

    path: str
    classification: str
    method: str
    models: list[dict] = field(default_factory=list)  # [{"model","pk","field"}]
    sha256: str = ""
    size: int = 0
    sources: list[dict] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    note: str = ""

    def as_dict(self) -> dict:
        return {
            "path": self.path, "classification": self.classification, "method": self.method,
            "models": self.models, "sha256": self.sha256, "size": self.size,
            "sources": self.sources, "evidence": self.evidence, "note": self.note,
        }


@dataclass
class Recovered:
    data: bytes
    classification: str
    method: str
    sources: list[dict] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    note: str = ""


class NotRecoverable(Exception):
    """Raised by a strategy that recognised the file but cannot rebuild it."""


@dataclass
class RecoveryEnv:
    """Everything a strategy may look at (all read-only)."""

    read_zip: Callable[[str], bytes | None]  # exact MEDIA_ROOT-relative path -> bytes
    find_in_zip_elsewhere: Callable[[str], list[tuple[str, Callable[[], bytes]]]]
    #: records of the SOURCE store (original pks): {"model","pk","fields"}
    records: list[dict]
    curated_dir: Path
    extra_media_dir: Path | None = None
    _index: dict = field(default_factory=dict, repr=False)
    _curated: dict | None = field(default=None, repr=False)
    _sums: dict | None = field(default=None, repr=False)

    # -- record helpers -------------------------------------------------
    def row(self, label: str, pk: int) -> dict | None:
        if not self._index:
            for rec in self.records:
                self._index[(rec["model"].lower(), rec["pk"])] = rec
        return self._index.get((label.lower(), pk))

    # -- curated pack ----------------------------------------------------
    def curated_manifest(self) -> dict:
        if self._curated is None:
            path = self.curated_dir / "manifest.json"
            self._curated = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        return self._curated

    def curated_sums(self) -> dict[str, str]:
        if self._sums is None:
            self._sums = {}
            path = self.curated_dir / "SHA256SUMS.txt"
            if path.is_file():
                for line in path.read_text(encoding="utf-8").splitlines():
                    parts = line.strip().split(None, 1)
                    if len(parts) == 2:
                        self._sums[parts[1].lstrip("*").replace("\\", "/")] = parts[0].lower()
        return self._sums

    def curated_bytes(self, rel: str) -> tuple[bytes, dict]:
        """Bytes of one curated asset - refused unless it matches ``SHA256SUMS.txt``."""
        path = self.curated_dir / rel
        if not path.is_file():
            raise NotRecoverable(f"curated asset {rel} is not present in this checkout")
        data = path.read_bytes()
        digest = sha256_bytes(data)
        expected = self.curated_sums().get(rel)
        if expected is None:
            raise NotRecoverable(f"curated asset {rel} has no entry in SHA256SUMS.txt")
        if expected != digest:
            raise NotRecoverable(f"curated asset {rel} does not match SHA256SUMS.txt (altered checkout)")
        return data, {"kind": "repo", "path": f"{CURATED_REL.as_posix()}/{rel}", "sha256": digest}


# ---------------------------------------------------------------- helpers

def _stem(rel: str) -> str:
    return posixpath.splitext(posixpath.basename(rel))[0]


def _ext(rel: str) -> str:
    return posixpath.splitext(rel)[1].lower()


def _name_is(rel: str, expected_stem: str) -> bool:
    """True when the stored name is ``expected_stem`` (+ Django's collision suffix)."""
    return re.fullmatch(re.escape(expected_stem) + _DJANGO_SUFFIX, _stem(rel)) is not None


def _image_format(data: bytes) -> str:
    from PIL import Image

    with Image.open(BytesIO(data)) as img:
        return (img.format or "").upper()


def _encode_for_extension(data: bytes, rel: str) -> tuple[bytes, bool]:
    """``data`` re-encoded to the format ``rel``'s extension promises; ``(bytes, transcoded)``."""
    target = _FORMAT_BY_EXT.get(_ext(rel))
    if target is None or _image_format(data) == target:
        return data, False
    from PIL import Image

    from apps.catalog.services.product_image_service import _encode

    with Image.open(BytesIO(data)) as img:
        img.load()
        image = img.convert("RGB") if target == "JPEG" else (img if img.mode in ("RGB", "RGBA") else img.convert("RGBA"))
        return _encode(image, target), True


# ---------------------------------------------------------------- strategies

def _from_curated(env: RecoveryEnv, db_rel: str, curated_rel: str, evidence: list[str]) -> Recovered:
    data, source = env.curated_bytes(curated_rel)
    data2, transcoded = _encode_for_extension(data, db_rel)
    if not transcoded:
        return Recovered(data, RECOVERED_FROM_REPO, "copy_repo_asset", [source], evidence)
    return Recovered(
        data2, REGENERATED_DERIVATIVE, "transcode_repo_asset", [source], evidence,
        f"repo asset is {_image_format(data)}, the database path promises {_ext(db_rel)}: transcoded, DB path kept",
    )


def _thumbnail(env: RecoveryEnv, db_rel: str, label: str, pk: int) -> Recovered:
    """Rebuild ``ProductImage.thumbnail`` with the application's own routine
    (``add_product_image``: normalise -> ``_shrink_to_fit(THUMBNAIL_DIMENSION)`` -> ``_encode``)."""
    from PIL import Image

    from apps.catalog.services import product_image_service as svc

    row = env.row(label, pk)
    main = (row or {}).get("fields", {}).get("image") or ""
    if not main:
        raise NotRecoverable("the ProductImage row has no original image to derive a thumbnail from")
    candidates = [
        (f"{svc.ORIGINALS_DIR}/{posixpath.basename(main)}", "the uploaded original kept by product_image_service"),
        (main, "the stored display image"),
    ]
    data = None
    for rel, why in candidates:
        data = env.read_zip(rel)
        if data is not None:
            src_rel, src_why = rel, why
            break
    if data is None:
        raise NotRecoverable(f"neither {candidates[0][0]} nor {main} is in the media ZIP")
    try:
        image, fmt = svc._load_normalized_image(BytesIO(data))
    except svc.ProductImageError as exc:
        raise NotRecoverable(f"source image {src_rel} is not decodable: {exc}") from exc
    target = _FORMAT_BY_EXT.get(_ext(db_rel), fmt)
    note = f"derived from {src_why}"
    if target != fmt:
        image = image.convert("RGB") if target == "JPEG" else (
            image if image.mode in ("RGB", "RGBA") else image.convert("RGBA"))
        note += f"; source is {fmt} but the database path promises {_ext(db_rel)}, encoded as {target}"
    thumb = svc._shrink_to_fit(image, svc.THUMBNAIL_DIMENSION)
    out = svc._encode(thumb, target)
    with Image.open(BytesIO(out)) as check:
        check.verify()
    return Recovered(
        out, REGENERATED_DERIVATIVE, "product_image_service.thumbnail",
        [{"kind": "input", "path": src_rel, "sha256": sha256_bytes(data)}],
        [f"{label} pk={pk} field thumbnail", f"THUMBNAIL_DIMENSION={svc.THUMBNAIL_DIMENSION}"], note,
    )


def _category(env: RecoveryEnv, db_rel: str, label: str, pk: int) -> Recovered:
    row = env.row(label, pk)
    if row is None:
        raise NotRecoverable("owning Category row not found")
    name, slug = row["fields"].get("name", ""), row["fields"].get("slug", "")
    manifest = env.curated_manifest()
    curated = manifest.get("categories", {}).get(name)
    if curated and _name_is(db_rel, f"rasti-{slug}"):
        return _from_curated(env, db_rel, curated, [
            f"category {name!r} is in curated/manifest.json",
            f"stored name matches refresh_rasti_mode_demo_visuals (rasti-{slug}.webp)",
        ])
    if _name_is(db_rel, f"category-{slug}") and _ext(db_rel) in _FORMAT_BY_EXT:
        return _seed_category_cover(env, db_rel, row, name, slug)
    raise NotRecoverable(
        f"{posixpath.basename(db_rel)!r} is not a name produced by refresh_rasti_mode_demo_visuals "
        f"(rasti-{slug}.*) or seed_ready_template_fashion_demo (category-{slug}.*); the original is not in Git"
    )


def _seed_category_cover(env: RecoveryEnv, db_rel: str, row: dict, name: str, slug: str) -> Recovered:
    """V5 category photos: ``seed_ready_template_fashion_demo._seed_category_images``."""
    seed = importlib.import_module("apps.stores.management.commands.seed_ready_template_fashion_demo")
    first = next((r for r in seed.PRODUCT_MATRIX if r[1] == name), None)
    if first is None:
        raise NotRecoverable(f"category {name!r} is not one of the seed command's categories")
    sku, colors = first[0], first[6]
    colors = colors if isinstance(colors, tuple) else (colors,)
    product = next((r for r in env.records if r["model"].lower() == "catalog.product"
                    and r["fields"].get("sku") == sku and r["fields"].get("category") == row["pk"]), None)
    if product is None:
        raise NotRecoverable(f"product {sku} (the seed's cover of {name!r}) is not in this category of the database")
    source = Path(seed.PRODUCT_MEDIA_DIR) / sku / "01.webp"
    if not source.is_file():
        raise NotRecoverable(f"committed product photo {source.name} of {sku} is missing")
    data = seed._composite_visual_bytes(
        width=800, height=600, product_paths=[source],
        bg_hex=seed.COLOR_HEX.get(colors[0], seed._FALLBACK_COLOR_HEX),
    )
    out, transcoded = _encode_for_extension(data, db_rel)
    return Recovered(
        out, REGENERATED_DERIVATIVE, "seed_composite" + ("+transcode" if transcoded else ""),
        [{"kind": "repo", "path": f"apps/stores/demo_assets/rasti_mode_demo/products/{sku}/01.webp",
          "sha256": sha256_bytes(source.read_bytes())}],
        [f"stored name matches seed_ready_template_fashion_demo (category-{slug}.jpg)",
         f"cover product {sku} exists in category {name!r}", "800x600 composite, background of the first colour"],
        "recreated with the seed command's own _composite_visual_bytes; JPEG bytes are not bit-comparable to the "
        "lost original (no hash of it exists) - the picture content is the same",
    )


def _brand(env: RecoveryEnv, db_rel: str, label: str, pk: int) -> Recovered:
    row = env.row(label, pk)
    fields = row["fields"] if row else {}
    name, slug = fields.get("name", ""), fields.get("slug", "")
    curated = env.curated_manifest().get("brands", {}).get(name)
    if curated and _name_is(db_rel, f"rasti-{slug}"):
        return _from_curated(env, db_rel, curated, [
            f"brand {name!r} is in curated/manifest.json", f"stored name matches rasti-{slug}.webp"])
    raise NotRecoverable(f"{posixpath.basename(db_rel)!r} is not a curated brand logo (brand {name!r})")


_NUMBERED = re.compile(r"^rasti-curated-(hero|banner|story)-(\d+)(-mobile)?" + _DJANGO_SUFFIX + "$")


def _numbered(env: RecoveryEnv, db_rel: str, label: str, pk: int, fname: str) -> Recovered:
    match = _NUMBERED.match(_stem(db_rel))
    if not match:
        raise NotRecoverable(f"{posixpath.basename(db_rel)!r} is not a rasti-curated-* name")
    kind, number, mobile = match.group(1), int(match.group(2)), bool(match.group(3))
    if mobile != fname.startswith("mobile"):
        raise NotRecoverable("desktop/mobile suffix of the name contradicts the field")
    manifest = env.curated_manifest()
    order = number - 1
    evidence = [f"stored name matches refresh_rasti_mode_demo_visuals (rasti-curated-{kind}-{number})"]
    if kind == "story":
        categories = list(manifest.get("categories", {}).items())
        if not 0 <= order < len(categories):
            raise NotRecoverable(f"no curated category #{number} for a story item")
        cat_name, curated = categories[order]
        row = env.row(label, pk)
        title = (row or {}).get("fields", {}).get("title", "")
        if title != cat_name[:60]:
            raise NotRecoverable(f"story title {title!r} is not the curated category {cat_name!r} #{number}")
        evidence.append(f"story #{number} shows category {cat_name!r} (title matches)")
        return _from_curated(env, db_rel, curated, evidence)
    entries = {"hero": manifest.get("heroes", []), "banner": manifest.get("banners", [])}[kind]
    entry = next((e for e in entries if e["order"] == order), None)
    if entry is None:
        raise NotRecoverable(f"no curated {kind} with order {order}")
    row = env.row(label, pk)
    if row is not None and row["fields"].get("display_order") != order:
        evidence.append(f"note: row display_order={row['fields'].get('display_order')} (curated order {order})")
    else:
        evidence.append(f"display_order {order} matches curated/manifest.json")
    return _from_curated(env, db_rel, entry["mobile" if mobile else "desktop"], evidence)


def _branding(env: RecoveryEnv, db_rel: str, fname: str) -> Recovered:
    manifest = env.curated_manifest().get("branding", {})
    expected = {"logo": "rasti-mode-demo-logo", "favicon": "rasti-mode-demo-favicon"}.get(fname)
    if expected and fname in manifest and _name_is(db_rel, expected):
        return _from_curated(env, db_rel, manifest[fname], [
            f"stored name matches refresh_rasti_mode_demo_visuals ({expected}.png)"])
    raise NotRecoverable(f"{posixpath.basename(db_rel)!r} is not the curated {fname}")


def _repo_strategy(env: RecoveryEnv, db_rel: str, label: str, pk: int, fname: str) -> Recovered:
    label_l = label.lower()
    if label_l == "catalog.productimage" and fname == "thumbnail":
        return _thumbnail(env, db_rel, label, pk)
    if label_l == "catalog.category" and fname == "image":
        return _category(env, db_rel, label, pk)
    if label_l == "catalog.brand" and fname == "logo":
        return _brand(env, db_rel, label, pk)
    if label_l in ("content.heroslide", "content.promotionalbanner") and fname in ("desktop_image", "mobile_image"):
        return _numbered(env, db_rel, label, pk, fname)
    if label_l == "content.storyrailitem" and fname == "image":
        return _numbered(env, db_rel, label, pk, fname)
    if label_l == "core.shopsettings" and fname in ("logo", "favicon"):
        return _branding(env, db_rel, fname)
    raise NotRecoverable(f"no recovery rule for {label}.{fname} (no original of this file exists in Git)")


# ---------------------------------------------------------------- entry point

def recover_one(env: RecoveryEnv, rel: str, label: str, pk: int, fname: str) -> Recovered | str:
    """A ``Recovered`` file, or the reason it is ``UNRECOVERABLE``."""
    # 1. the operator's own copy: --extra-media-dir
    if env.extra_media_dir is not None:
        try:
            candidate = env.extra_media_dir / safe_relative_media_path(rel)
        except UnsafeMediaPath:
            candidate = None
        if candidate is not None and candidate.is_file():
            data = candidate.read_bytes()
            return Recovered(data, ORIGINAL, "operator_supplied", [
                {"kind": "extra_media_dir", "path": rel, "sha256": sha256_bytes(data)}],
                ["supplied explicitly through --extra-media-dir"])
    # 2. the same file name, exactly once, under another folder of the same ZIP
    elsewhere = env.find_in_zip_elsewhere(rel)
    if len(elsewhere) == 1:
        name, reader = elsewhere[0]
        data = reader()
        return Recovered(data, ORIGINAL, "zip_other_path", [
            {"kind": "input_zip", "path": name, "sha256": sha256_bytes(data)}],
            [f"unique file with the same name {posixpath.basename(rel)!r} found at {name!r} in the same ZIP"])
    # 3. repo assets / application code
    try:
        return _repo_strategy(env, rel, label, pk, fname)
    except NotRecoverable as exc:
        extra = f" ({len(elsewhere)} same-named files in the ZIP, ambiguous)" if len(elsewhere) > 1 else ""
        return f"{exc}{extra}"
    except Exception as exc:  # noqa: BLE001 - a bug in a strategy must not silently produce an image
        return f"{type(exc).__name__}: {exc}"
