"""Resolve once for ordinary CI. Releases instead test their existing artifact."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'deploy/release'))
from build_release import build_wheelhouse

if __name__ == '__main__':
    dest = Path('.ci-deps')
    dest.mkdir(exist_ok=True)
    version = '%d.%d' % sys.version_info[:2]
    lock = build_wheelhouse([Path('requirements.txt'), Path('deploy/release/requirements-server.txt')], dest/'wheelhouse', version)
    (dest/'requirements.lock').write_text(lock)
