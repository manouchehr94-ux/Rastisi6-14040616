"""Gunicorn settings for RastiSi only (see systemd/rastisi-gunicorn.service).

Listens on its own unix socket, so it cannot collide with any other site that
runs on the same VPS (for example rastiservice.ir). Everything is overridable
through environment variables set in the unit file.
"""

import multiprocessing
import os

bind = os.environ.get("RASTISI_GUNICORN_BIND", "unix:/run/rastisi/gunicorn.sock")
workers = int(os.environ.get("RASTISI_GUNICORN_WORKERS", max(2, min(4, multiprocessing.cpu_count()))))
threads = int(os.environ.get("RASTISI_GUNICORN_THREADS", 2))
timeout = int(os.environ.get("RASTISI_GUNICORN_TIMEOUT", 60))
graceful_timeout = 30
keepalive = 5
max_requests = 2000
max_requests_jitter = 200
accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("RASTISI_GUNICORN_LOGLEVEL", "info")
proc_name = "rastisi-gunicorn"
umask = 0o007  # socket readable by the nginx group only
