"""QA-only settings: the real project settings with a DISPOSABLE sqlite copy (never the project's db.sqlite3)."""
from shop_core.settings import *   # noqa: F401,F403
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": "/tmp/claude-0/-home-user-Rastisi6-14040616/9464551a-7c83-50df-b657-f00f736fb713/scratchpad/qa/qa_notif.sqlite3"}}
