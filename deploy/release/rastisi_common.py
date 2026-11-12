"""Shared helpers for the RastiSi release tooling (standard library only, Python 3.8+).

Installed root-owned in /usr/local/lib/rastisi/ together with the other tools. A release can never replace the tooling that deploys it.
Nothing in here prints secret values: configuration is read by name, text is passed through ``redact`` before it is logged.
"""

import configparser
import hashlib
import json
import os
import re
import shlex
import sys
import tarfile
import time
from pathlib import Path

CONF_ENV = "RASTISI_DEPLOY_CONF"
DEFAULT_CONF = "/etc/rastisi/deploy.conf"

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
RELEASE_ID_RE = re.compile(r"^(?:\d{8}T\d{6}Z-[0-9a-f]{12}|legacy-[0-9a-f]{12})$")
RUN_ID_RE = re.compile(r"^\d{8}T\d{6}Z-[0-9a-f]{8}$")

# exit codes (stable: the workflow and the runbooks refer to them)
EXIT_OK = 0
EXIT_FAILED_SAFE = 1          # failed before anything changed, or failed and was rolled back; the previous release is serving
EXIT_NEEDS_HUMAN = 2          # state is uncertain / rollback unsafe; INCIDENT file written
EXIT_MIGRATION_FAILED = 3     # migration failed; release not activated; previous release is serving
EXIT_POLICY = 4               # refused by policy (migration class, stale plan, bad input)
EXIT_BUSY = 75                # another deployment holds the lock


class ConfigError(Exception):
    pass


# ----------------------------------------------------------------------------------------------------------------- redaction
_URL_PW = re.compile(r"(?i)\b([a-z][a-z0-9+.\-]*://[^/\s:@]*):([^@\s/]+)@")
_KV_SECRET = re.compile(
    r"(?i)\b((?:[A-Z0-9_]*(?:SECRET|PASSWORD|PASSWD|TOKEN|API_?KEY|PRIVATE_?KEY|CREDENTIAL)[A-Z0-9_]*)\s*[=:]\s*)(\S+)"
)
_BEARER = re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._~+/=\-]{8,}")
_PEM = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S)


def redact(text, extra_values=()):
    """Mask credentials in free text. ``extra_values`` are exact secret strings known to the caller (never logged themselves)."""
    text = str(text)
    for value in sorted({v for v in extra_values if v and len(v) >= 4}, key=len, reverse=True):
        text = text.replace(value, "***")
    text = _PEM.sub("***PRIVATE KEY***", text)
    text = _URL_PW.sub(r"\1:***@", text)
    text = _BEARER.sub(r"\1***", text)
    text = _KV_SECRET.sub(r"\1***", text)
    return text


SENSITIVE_NAME = re.compile(r"(?i)(SECRET|PASSWORD|PASSWD|TOKEN|API_?KEY|PRIVATE_?KEY|CREDENTIAL|_KEY$|^DATABASE_URL$|_URL$)")


def parse_env_file(path):
    """Parse a KEY=VALUE environment file (the same dialect systemd's EnvironmentFile and the app's wrapper accept: no expansion)."""
    values = {}
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", key):
            values[key] = value
    return values


def secret_values(env):
    """Values of the sensitive-looking variables, used only to mask them in captured output."""
    out = set()
    for key, value in env.items():
        if SENSITIVE_NAME.search(key) and value:
            out.add(value)
            for part in _URL_PW.findall(value):
                out.add(part[1])
    return out


# ------------------------------------------------------------------------------------------------------------------- config
class Config:
    """Non-secret deployment settings from /etc/rastisi/deploy.conf (path overridable with RASTISI_DEPLOY_CONF, used by the tests)."""

    REQUIRED = ("base_dir", "app_user", "service", "env_file", "port")

    def __init__(self, path=None):
        path = path or os.environ.get(CONF_ENV) or DEFAULT_CONF
        parser = configparser.ConfigParser(interpolation=None)
        if not Path(path).is_file():
            raise ConfigError("deployment config not found: %s" % path)
        parser.read(path, encoding="utf-8")
        if not parser.has_section("rastisi"):
            raise ConfigError("deployment config has no [rastisi] section")
        self._v = dict(parser.items("rastisi"))
        missing = [k for k in self.REQUIRED if not self._v.get(k)]
        if missing:
            raise ConfigError("deployment config is missing: " + ", ".join(missing))
        self.path = path

    def get(self, key, default=None):
        value = self._v.get(key)
        return default if value in (None, "") else value

    def int(self, key, default):
        try:
            return int(self.get(key, default))
        except ValueError:
            raise ConfigError("%s must be an integer" % key)

    @property
    def base(self):
        return Path(self._v["base_dir"])

    @property
    def releases(self):
        return self.base / "releases"

    @property
    def venvs(self):
        return self.base / "venvs"

    @property
    def state(self):
        return self.base / "state"

    @property
    def staging(self):
        return self.base / "staging"

    @property
    def current_link(self):
        return self.base / "current"

    @property
    def previous_link(self):
        return self.base / "previous"

    def command(self, key, default):
        """A configurable command prefix (shell-split, never run through a shell)."""
        return shlex.split(self.get(key, default))


# --------------------------------------------------------------------------------------------------------------- filesystem
def sha256_file(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def utc_stamp():
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())


def fsync_directory(path):
    fd = os.open(str(path), os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_write_text(path, text, mode=0o640):
    path = Path(path)
    tmp = path.with_name(".%s.tmp-%d" % (path.name, os.getpid()))
    with tmp.open('w', encoding='utf-8') as fh:
        os.fchmod(fh.fileno(), mode)
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(str(tmp), str(path))
    fsync_directory(path.parent)


def atomic_write_json(path, data, mode=0o640):
    # The migration fence must be durable before any SQL is started, not just
    # visible to another process. fsync both the file and the renamed directory.
    atomic_write_text(path, json.dumps(data, indent=2, sort_keys=True) + "\n", mode)


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def atomic_symlink(target, link):
    """Point ``link`` at ``target`` in one atomic step (rename over a temporary symlink)."""
    link = Path(link)
    tmp = link.with_name(".%s.new-%d" % (link.name, os.getpid()))
    if tmp.is_symlink() or tmp.exists():
        tmp.unlink()
    os.symlink(str(target), str(tmp))
    os.replace(str(tmp), str(link))
    fsync_directory(link.parent)


def safe_extract_tar(archive, dest, max_bytes=2 * 1024 ** 3):
    """Extract a .tar.gz refusing absolute paths, ``..``, links that escape, devices, and oversize archives (zip-slip / tar bombs)."""
    dest = Path(dest).resolve()
    total = 0
    with tarfile.open(str(archive), "r:gz") as tar:
        members = tar.getmembers()
        for m in members:
            name = m.name
            if name.startswith("/") or ".." in Path(name).parts:
                raise ValueError("unsafe path in archive: %r" % name)
            if m.isdev() or m.isfifo():
                raise ValueError("device/fifo in archive: %r" % name)
            if m.issym() or m.islnk():
                link_target = (dest / Path(name).parent / m.linkname) if not m.linkname.startswith("/") else Path(m.linkname)
                if m.islnk():
                    link_target = dest / m.linkname
                if not str(Path(os.path.normpath(str(link_target)))).startswith(str(dest) + os.sep):
                    raise ValueError("link escapes the release: %r -> %r" % (name, m.linkname))
            total += max(m.size, 0)
            if total > max_bytes:
                raise ValueError("archive too large")
        for m in members:
            m.uid = m.gid = 0
            m.uname = m.gname = ""
        tar.extractall(str(dest), members=members)


def log(msg, stream=None):
    stream = stream or sys.stdout
    stream.write("%s %s\n" % (time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), redact(msg)))
    stream.flush()
