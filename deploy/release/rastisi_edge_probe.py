"""Verify local Nginx/TLS and one actual static asset. No public network target.

curl --resolve pins the TLS connection to loopback while retaining the real
hostname for SNI, certificate verification and the HTTP Host header.
"""
import argparse
import json
import re
import subprocess
from urllib.parse import urlsplit


def fetch(host, port, path):
    proc = subprocess.run(['curl', '--silent', '--show-error', '--fail', '--max-time', '15',
                           '--noproxy', host, '--resolve', '%s:%d:127.0.0.1' % (host, port),
                           'https://%s:%d%s' % (host, port, path)], capture_output=True, text=True, timeout=20)
    if proc.returncode:
        raise ValueError('local Nginx/TLS request failed for %s' % path.split('?')[0])
    return proc.stdout


def check(host, port):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]*', host) or not 1 <= port <= 65535:
        raise ValueError('invalid configured edge host or port')
    html = fetch(host, port, '/')
    if '<html' not in html.lower():
        raise ValueError('edge home page is not HTML')
    fetch(host, port, '/login/')
    fetch(host, port, '/robots.txt')
    assets = re.findall(r'(?:src|href)=["\'](/static/[^"\'<>\s]+)["\']', html)
    if not assets:
        raise ValueError('no static asset found in edge HTML')
    path = assets[0]
    if urlsplit(path).netloc or not path.startswith('/static/'):
        raise ValueError('invalid static asset path')
    fetch(host, port, path)
    return {'ok': True, 'passed': ['local Nginx TLS, public pages and static asset'], 'failures': []}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', required=True)
    parser.add_argument('--port', type=int, default=443)
    args = parser.parse_args()
    try:
        result = check(args.host, args.port)
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        # No command output or environment values are exposed.
        result = {'ok': False, 'failures': [str(exc) if isinstance(exc, ValueError) else type(exc).__name__]}
    print(json.dumps(result))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
