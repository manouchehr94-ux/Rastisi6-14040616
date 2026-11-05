"""QA-ONLY finance seed (scratch DB): purchases/attempts/claims/refunds so every PR #40 page has content. Synthetic; no secrets."""
import secrets
from datetime import timedelta
from decimal import Decimal
from django.utils import timezone
from apps.billing.models import PlatformManualPaymentClaim, SubscriptionInvoice, SubscriptionPaymentAttempt, SubscriptionRefund
from apps.sms.models import SmsPackage, SmsPackagePaymentAttempt, SmsPackagePurchase
from apps.stores.models import Store
from django.contrib.auth import get_user_model
U = get_user_model(); owner = U.objects.filter(is_superuser=True).first()
store = Store.objects.get(slug="qa-store-1"); inv = SubscriptionInvoice.objects.filter(store=store).first()
pkg = SmsPackage.objects.first()
if not SmsPackagePurchase.objects.exists():
    pend = SmsPackagePurchase.objects.create(store=store, package=pkg, credit_amount=pkg.credit_amount, price=pkg.price, status="pending")
    done = SmsPackagePurchase.objects.create(store=store, package=pkg, credit_amount=pkg.credit_amount, price=pkg.price, status="completed", completed_at=timezone.now())
    for i, (p, st) in enumerate([(pend, "pending"), (done, "succeeded")]):
        SmsPackagePaymentAttempt.objects.create(store=store, purchase=p, provider="zibal", status=st, amount=p.price, public_token=secrets.token_urlsafe(24), idempotency_key=f"qa-sms-{i}")
if not SubscriptionPaymentAttempt.objects.exists():
    for i, (st, code) in enumerate([("pending", ""), ("succeeded", ""), ("failed", "purchase_canceled"), ("requires_action", "amount_mismatch")]):
        SubscriptionPaymentAttempt.objects.create(store=store, invoice=inv, provider="zibal" if i % 2 == 0 else "zarinpal", status=st, amount=inv.grand_total,
            public_token=secrets.token_urlsafe(20)[:40], idempotency_key=f"qa-sub-{i}", failure_code=code, started_at=timezone.now() - timedelta(hours=3 * (i + 1)))
if not PlatformManualPaymentClaim.objects.exists():
    PlatformManualPaymentClaim.objects.create(store=store, invoice=inv, submitted_by=None, expected_amount=inv.grand_total, reference_raw="TRK-QA-556677", reference_key="trkqa556677",
        transferred_at=timezone.now() - timedelta(hours=2), payer_card_last4="4321", expires_at=timezone.now() + timedelta(days=2), flags=["amount_close"])
    PlatformManualPaymentClaim.objects.create(store=store, invoice=inv, expected_amount=inv.grand_total, reference_raw="TRK-QA-OLD", reference_key="trkqaold", transferred_at=timezone.now() - timedelta(days=1),
        expires_at=timezone.now() + timedelta(days=1), status="rejected", review_note="مبلغ نامطابق")
if not SubscriptionRefund.objects.exists():
    SubscriptionRefund.objects.create(store=store, invoice=inv, provider="zibal", status="requested", amount=Decimal(100000), reason="درخواستِ مشتری")
SubscriptionInvoice.objects.filter(pk=inv.pk).update(amount_paid=Decimal(500000), amount_due=inv.grand_total - Decimal(500000))
print("finance seeded", PlatformManualPaymentClaim.objects.count(), SmsPackagePurchase.objects.count())
