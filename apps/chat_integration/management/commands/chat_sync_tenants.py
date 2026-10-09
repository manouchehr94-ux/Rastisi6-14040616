from django.core.management.base import BaseCommand

from apps.stores.models import StoreIntegrationConnection

from apps.chat_integration import client, conf
from apps.chat_integration.services import enablement, tenant_service


class Command(BaseCommand):
    help = ("Re-send name / verified domains / status of every chat-enabled store to RastiChat (idempotent reconcile for "
            "renames, domain changes and missed lifecycle hooks). Never enables a store and never changes a flag.")

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        if not conf.globally_enabled():
            self.stdout.write("RASTICHAT_INTEGRATION_ENABLED is off — nothing to do.")
            return
        ok = failed = 0
        for connection in StoreIntegrationConnection.objects.filter(provider_code=enablement.PROVIDER_CODE, is_active=True).select_related("store"):
            if opts["dry_run"]:
                self.stdout.write(f"would sync {connection.store.slug}")
                continue
            try:
                tenant_service.ensure_remote_tenant(connection.store)
                ok += 1
            except client.RastiChatError as exc:
                failed += 1
                self.stderr.write(f"{connection.store.slug}: {exc}")
        self.stdout.write(f"synced={ok} failed={failed}")
