"""Settings for the opt-in real-browser tests (``SFB_BROWSER_TESTS=1``) that CLICK through the Studio.

The default SQLite test database lives in memory and is shared with the live server's threads, which cannot survive a real mutation
workflow (``no such savepoint`` / table locks). A file-based test database gives every thread its own connection:

    SFB_BROWSER_TESTS=1 DJANGO_SETTINGS_MODULE=shop_core.settings_browser_tests python manage.py test <browser test module>

Test-only: it never touches the development or production database (Django creates and drops its own ``test_*`` file)."""

import tempfile
from pathlib import Path

from .settings import *  # noqa: F401,F403
from .settings import DATABASES

_TEST_DB = Path(tempfile.gettempdir()) / "rastisi_browser_tests.sqlite3"
DATABASES["default"].setdefault("TEST", {})["NAME"] = str(_TEST_DB)
DATABASES["default"].setdefault("OPTIONS", {})["timeout"] = 30
