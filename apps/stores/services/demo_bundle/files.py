"""Filesystem helpers shared by exporter, validator and importer."""

from __future__ import annotations

import hashlib
import os
import posixpath
import shutil
import tempfile
from pathlib import Path

from django.apps import apps
from django.db import models


def long_path(path: Path) -> Path:
    """On Windows, lift the 260-character MAX_PATH limit (Persian file names get long) with the ``\\\\?\\`` prefix."""
    if os.name != "nt":
        return Path(path)
    resolved = str(Path(path).resolve())
    if resolved.startswith("\\\\?\\"):
        return Path(resolved)
    return Path("\\\\?\\" + resolved)


class UnsafeMediaPath(ValueError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(long_path(path), "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_relative_media_path(name: str) -> str:
    """Return the normalized MEDIA_ROOT-relative POSIX path or raise.

    Rejects absolute paths, drive letters, backslashes, NUL and any ``..``
    segment so a hostile bundle can never write outside MEDIA_ROOT.
    """
    if not isinstance(name, str) or not name or "\x00" in name or "\\" in name:
        raise UnsafeMediaPath(f"invalid media path {name!r}")
    normalized = posixpath.normpath(name)
    if normalized.startswith("/") or normalized.startswith("..") or ":" in normalized.split("/")[0]:
        raise UnsafeMediaPath(f"unsafe media path {name!r}")
    if any(part in ("", ".", "..") for part in normalized.split("/")):
        raise UnsafeMediaPath(f"unsafe media path {name!r}")
    return normalized


def file_fields(model) -> list[models.FileField]:
    return [f for f in model._meta.concrete_fields if isinstance(f, models.FileField)]


def model_for(label: str):
    return apps.get_model(label)


def copy_atomic(src: Path, dst: Path) -> None:
    src, dst = long_path(src), long_path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(dst.parent), prefix=".bundle-")
    os.close(fd)
    try:
        shutil.copyfile(src, tmp)
        os.replace(tmp, dst)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
