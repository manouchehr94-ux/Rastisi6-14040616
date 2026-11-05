"""Data-safe removal of COD (and the store-only card-transfer code) from PLATFORM billing configuration.

Cash-on-delivery is meaningless for SaaS invoices and was never an eligible platform gateway. If any older platform
configuration still references it (``PlatformConfiguration.enabled_payment_providers`` / ``default_payment_provider`` or a
stray ``PlatformGatewayConfig`` row), it is neutralised WITHOUT deleting history: lists are filtered, a default of ``cod``
falls back to ``manual``, stray gateway rows are disabled (kept), and every change is recorded in the platform audit log.
Store COD (``apps.orders``) is not touched. Idempotent; reverse is a no-op (history stays in the audit log)."""

from django.db import migrations

REMOVED = ("cod", "card_to_card")


def neutralise(apps, schema_editor):
    Config = apps.get_model("portal", "PlatformConfiguration")
    Gateway = apps.get_model("portal", "PlatformGatewayConfig")
    Audit = apps.get_model("portal", "PlatformAuditLogEntry")

    for config in Config.objects.all():
        before_list = list(config.enabled_payment_providers or [])
        after_list = [code for code in before_list if code not in REMOVED]
        before_default = config.default_payment_provider
        after_default = "manual" if before_default in REMOVED else before_default
        if after_list != before_list or after_default != before_default:
            config.enabled_payment_providers = after_list
            config.default_payment_provider = after_default
            config.save(update_fields=["enabled_payment_providers", "default_payment_provider"])
            Audit.objects.create(
                action_code="platform_gateway.cod_removed", object_type="PlatformConfiguration", object_id=str(config.pk),
                before_summary=f"enabled={before_list} default={before_default}",
                after_summary=f"enabled={after_list} default={after_default}",
                metadata={"reason": "COD / store card-transfer are not platform billing methods"},
            )

    for row in Gateway.objects.filter(gateway_code__in=REMOVED, is_enabled=True):      # already-disabled rows: nothing to do (idempotent)
        was_enabled = row.is_enabled
        row.is_enabled = False
        row.save(update_fields=["is_enabled"])
        Audit.objects.create(
            action_code="platform_gateway.cod_removed", object_type="PlatformGatewayConfig", object_id=str(row.pk),
            object_label=row.gateway_code, before_summary=f"enabled={was_enabled}", after_summary="enabled=False (row kept)",
            metadata={"reason": "not a platform billing method"},
        )


class Migration(migrations.Migration):
    dependencies = [("portal", "0017_platform_gateway_gates")]
    operations = [migrations.RunPython(neutralise, migrations.RunPython.noop)]
