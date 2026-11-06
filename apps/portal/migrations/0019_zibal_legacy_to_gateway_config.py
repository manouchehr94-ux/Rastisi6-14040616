"""One-time, non-destructive consolidation of the legacy platform Zibal configuration into ``PlatformGatewayConfig``.

Before: ``PlatformConfiguration.encrypted_zibal_credentials`` / ``zibal_sandbox_mode`` (+ ``default_payment_provider ==
"zibal"`` meaning "enabled") were a second credential store mirrored by the old ``/payments/zibal/`` page.
After: ``PlatformGatewayConfig(gateway_code="zibal")`` is the only place credentials/mode/enabled live; the legacy columns
are NO LONGER WRITTEN (kept as an untouched, read-only rollback copy — nothing is deleted or cleared).

* No row yet and legacy data exists  -> create the row from it (same Fernet ciphertext, so no decrypt/re-encrypt).
* A row already exists               -> the row wins (it already had priority at read time); nothing is overwritten.
* Idempotent; recorded in the platform audit log (no secrets). Reverse is a no-op."""

from django.db import migrations


def consolidate(apps, schema_editor):
    Config = apps.get_model("portal", "PlatformConfiguration")
    Gateway = apps.get_model("portal", "PlatformGatewayConfig")
    Audit = apps.get_model("portal", "PlatformAuditLogEntry")

    for config in Config.objects.all():
        has_creds = bool(config.encrypted_zibal_credentials)
        legacy_enabled = config.default_payment_provider == "zibal"
        if not (has_creds or config.zibal_sandbox_mode or legacy_enabled):
            continue
        existing = Gateway.objects.filter(gateway_code="zibal").first()
        if existing is not None:
            Audit.objects.create(
                action_code="platform_gateway.zibal_legacy_consolidated", object_type="PlatformGatewayConfig",
                object_id=str(existing.pk), object_label="zibal",
                before_summary="legacy columns present", after_summary="row kept as canonical (legacy not copied)",
                metadata={"outcome": "row_wins"},
            )
            continue
        row = Gateway.objects.create(
            gateway_code="zibal", is_enabled=bool(legacy_enabled and has_creds), sandbox_mode=bool(config.zibal_sandbox_mode),
            encrypted_credentials=config.encrypted_zibal_credentials,
        )
        Audit.objects.create(
            action_code="platform_gateway.zibal_legacy_consolidated", object_type="PlatformGatewayConfig",
            object_id=str(row.pk), object_label="zibal",
            before_summary=f"legacy credentials={'yes' if has_creds else 'no'} sandbox={config.zibal_sandbox_mode} default_is_zibal={legacy_enabled}",
            after_summary=f"row created enabled={row.is_enabled} sandbox={row.sandbox_mode}",
            metadata={"outcome": "row_created"},
        )


class Migration(migrations.Migration):
    dependencies = [("portal", "0018_platform_cod_removal")]
    operations = [migrations.RunPython(consolidate, migrations.RunPython.noop)]
