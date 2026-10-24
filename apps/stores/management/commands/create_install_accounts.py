"""Create the two install-time accounts: ``platform_owner`` and ``shops_admin``.

Interactive by default (``getpass``, typed twice, never echoed or logged).
For a secret manager, name an ENVIRONMENT VARIABLE that holds the password:

    python manage.py create_install_accounts \
        --platform-owner-password-env PLATFORM_OWNER_PASSWORD \
        --shops-admin-password-env SHOPS_ADMIN_PASSWORD

The password itself is never accepted as a command-line argument (it would land
in shell history and ``ps``). Existing users keep their password unless
``--reset-password`` is given.
"""

import getpass
import os
import sys

from django.core.management.base import BaseCommand, CommandError

from apps.stores.services.demo_bundle import accounts
from apps.stores.services.demo_bundle.targets import load_targets


class Command(BaseCommand):
    help = "Create platform_owner (superuser) and shops_admin (active OWNER of both demo stores)."

    def add_arguments(self, parser):
        parser.add_argument("--targets", default=None)
        parser.add_argument("--platform-owner-password-env", metavar="VAR")
        parser.add_argument("--shops-admin-password-env", metavar="VAR")
        parser.add_argument("--platform-owner-email", default="")
        parser.add_argument("--shops-admin-email", default="")
        parser.add_argument("--reset-password", action="store_true")

    def _password(self, username, env_name, needed):
        if env_name:
            value = os.environ.get(env_name)
            if not value:
                raise CommandError(f"environment variable {env_name} is empty or unset")
            return value
        if not needed:
            return None
        if not sys.stdin.isatty():
            raise CommandError(f"no TTY: provide --{username.replace('_', '-')}-password-env VAR")
        first = getpass.getpass(f"Password for {username}: ")
        if first != getpass.getpass(f"Repeat password for {username}: "):
            raise CommandError("passwords do not match")
        return first

    def handle(self, *args, **opts):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        reset = opts["reset_password"]
        need_owner = reset or not User.objects.filter(username=accounts.PLATFORM_OWNER).exists()
        need_admin = reset or not User.objects.filter(username=accounts.SHOPS_ADMIN).exists()
        slugs = [t.slug for t in load_targets(opts["targets"]).values()]
        try:
            summary = accounts.ensure_accounts(
                platform_owner_password=self._password(accounts.PLATFORM_OWNER, opts["platform_owner_password_env"], need_owner),
                shops_admin_password=self._password(accounts.SHOPS_ADMIN, opts["shops_admin_password_env"], need_admin),
                store_slugs=slugs,
                reset_password=reset,
                platform_owner_email=opts["platform_owner_email"],
                shops_admin_email=opts["shops_admin_email"],
            )
        except accounts.AccountError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(
            f"created={summary['created']} password_set={summary['password_set']} owner_of={summary['memberships']}"
        ))
