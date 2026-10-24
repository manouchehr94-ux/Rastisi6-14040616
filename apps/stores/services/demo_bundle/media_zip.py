"""Safe, tolerant reader for a store's media archive (``*_media.zip``).

The archive is the old ``MEDIA_ROOT`` zipped on some machine, so it may or may
not carry a wrapping folder (``media/``, ``demo_v5_media/media/`` ...), may use
Windows ``\\`` separators or non-UTF-8 file-name encodings, and may contain OS
junk. This module finds the real root by matching the paths the database
actually references, and refuses anything unsafe (zip-slip, symlinks,
encrypted members, absurd sizes). Nothing is extracted to disk except by the
explicit streaming ``copy_to``.
"""

from __future__ import annotations

import hashlib
import posixpath
import unicodedata
import zipfile
from collections import Counter
from pathlib import Path

from .files import long_path

JUNK_BASENAMES = {"thumbs.db", ".ds_store", "desktop.ini"}
MAX_FILES = 400_000
MAX_TOTAL_BYTES = 16 * 2**30
MAX_RATIO = 1000


class MediaZipError(Exception):
    pass


def _norm(name: str) -> str:
    return unicodedata.normalize("NFC", name.replace("\\", "/"))


def _is_unsafe(name: str) -> bool:
    if not name or "\x00" in name or name.startswith("/") or (len(name) > 1 and name[1] == ":"):
        return True
    return any(part == ".." for part in name.split("/"))


def _is_junk(name: str) -> bool:
    parts = name.split("/")
    return parts[0] == "__MACOSX" or parts[-1].lower() in JUNK_BASENAMES


class MediaZip:
    def __init__(self, path: Path):
        self.path = Path(path)
        if not self.path.is_file():
            raise MediaZipError(f"media archive not found: {self.path}")
        try:
            self.zf = zipfile.ZipFile(self.path)
        except zipfile.BadZipFile as exc:
            raise MediaZipError(f"{self.path} is not a valid ZIP archive: {exc}") from exc
        bad = self.zf.testzip()
        if bad is not None:
            raise MediaZipError(f"{self.path}: corrupt member {bad!r}")
        self.entries: dict[str, zipfile.ZipInfo] = {}
        self.junk = 0
        infos = [i for i in self.zf.infolist() if not i.is_dir()]
        if len(infos) > MAX_FILES:
            raise MediaZipError(f"{self.path}: {len(infos)} members exceeds the safety limit {MAX_FILES}")
        total = 0
        for info in infos:
            for name in self._names(info):
                if _is_unsafe(name):
                    raise MediaZipError(f"{self.path}: unsafe member name {info.filename!r} (path traversal)")
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise MediaZipError(f"{self.path}: member {info.filename!r} is a symlink")
            if info.flag_bits & 0x1:
                raise MediaZipError(f"{self.path}: member {info.filename!r} is encrypted")
            total += info.file_size
            if info.compress_size and info.file_size / info.compress_size > MAX_RATIO and info.file_size > 50 * 2**20:
                raise MediaZipError(f"{self.path}: member {info.filename!r} has a suspicious compression ratio")
            primary = self._names(info)[0]
            if _is_junk(primary):
                self.junk += 1
                continue
            for name in self._names(info):
                self.entries.setdefault(name, info)
        if total > MAX_TOTAL_BYTES:
            raise MediaZipError(f"{self.path}: uncompressed size {total} exceeds the safety limit")
        self.prefix = ""

    @staticmethod
    def _names(info: zipfile.ZipInfo) -> list[str]:
        """Primary decoded name plus a re-decoded variant for archives that lack the UTF-8 flag."""
        names = [_norm(info.filename)]
        if not info.flag_bits & 0x800:
            try:
                alt = _norm(info.filename.encode("cp437").decode("utf-8"))
                if alt != names[0]:
                    names.append(alt)
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass
        return names

    def sha256(self) -> str:
        digest = hashlib.sha256()
        with open(self.path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def detect_prefix(self, referenced: set[str], override: str | None = None) -> str:
        """Folder inside the archive that corresponds to ``MEDIA_ROOT``."""
        if override is not None:
            self.prefix = _norm(override).strip("/")
            self.prefix = self.prefix + "/" if self.prefix else ""
            return self.prefix
        by_base: dict[str, list[str]] = {}
        for name in self.entries:
            by_base.setdefault(posixpath.basename(name), []).append(name)
        votes: Counter[str] = Counter()
        for rel in referenced:
            rel_n = _norm(rel)
            for name in by_base.get(posixpath.basename(rel_n), ()):
                if name == rel_n:
                    votes[""] += 1
                elif name.endswith("/" + rel_n):
                    votes[name[: -len(rel_n)]] += 1
        if not votes:
            self.prefix = ""
            return ""
        best = max(votes.items(), key=lambda kv: (kv[1], -len(kv[0])))
        self.prefix = best[0]
        return self.prefix

    def info_for(self, rel: str) -> zipfile.ZipInfo | None:
        return self.entries.get(self.prefix + _norm(rel))

    def rooted_files(self) -> dict[str, zipfile.ZipInfo]:
        """All archive files under the detected root, keyed by MEDIA_ROOT-relative path."""
        out = {}
        for name, info in self.entries.items():
            if name.startswith(self.prefix):
                rel = name[len(self.prefix):]
                if rel:
                    out[rel] = info
        return out

    def copy_to(self, info: zipfile.ZipInfo, destination: Path) -> tuple[str, int]:
        """Stream one member to ``destination``; returns ``(sha256, size)``."""
        destination = long_path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        digest, size = hashlib.sha256(), 0
        with self.zf.open(info) as src, open(destination, "wb") as dst:
            for chunk in iter(lambda: src.read(1 << 20), b""):
                digest.update(chunk)
                dst.write(chunk)
                size += len(chunk)
        return digest.hexdigest(), size

    def close(self) -> None:
        self.zf.close()
