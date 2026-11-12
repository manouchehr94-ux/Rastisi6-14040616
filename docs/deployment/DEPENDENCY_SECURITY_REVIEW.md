# Dependency exception assessment — 2026-11-12

Scope: the production wheelhouse resolved for this remediation, including
Gunicorn. Audit reported 41 advisories: 40 for Pillow 12.3.0 and one for
cryptography 49.0.0. The existing application version ranges forbid the stated
fixed major versions. No version ranges or payment/encryption logic were changed.

## cryptography — PYSEC-2026-3552

OSV: https://api.osv.dev/v1/vulns/PYSEC-2026-3552

The advisory concerns PKCS#7 EnvelopedData decryption (`pkcs7_decrypt_der`,
`pkcs7_decrypt_pem`, `pkcs7_decrypt_smime`) exposing an adaptive RSA error/timing
oracle. Fixed in 50.0.0. The advisory's described precondition is a service
accepting attacker-supplied encrypted PKCS#7/S/MIME messages.

Source search found no PKCS#7/EnvelopedData decrypt caller in apps/ or shop_core/.
Current usages include Fernet credentials, EC Web Push/VAPID and RSA/x509 SNS
signature verification. These are different APIs. This reduces the demonstrated
application reachability; it does not prove all transitive uses or deployment
extensions safe. The exception has NOT been automatically approved. A reviewed
upgrade and regression validation, or explicit owner/security acceptance backed
by the full deployment inventory, is still required. The gate blocks it.

## Pillow — 40 original exception IDs

OSV sample: https://api.osv.dev/v1/vulns/CVE-2026-112390

This confirmed sample concerns infinite MIC/TIFF frame traversal when processing
crafted input (with olefile and frame-count/multi-frame processing preconditions),
fixed in 13.0.0. One sample is not evidence that the other 39 IDs are harmless.
Merchant image upload/validation is an untrusted-image boundary. The 40-advisory
blanket exception cannot be accepted from package version/expiry alone.

Keep the existing registry for traceability, with no security approval record.
The hardened audit rejects it. Required follow-up: evaluate every advisory against
the actual enabled codecs/call sites and limits, or upgrade Pillow in a separate
validated dependency change and run image/upload/catalog regression tests. Do not
mark every exception approved to obtain green CI.

## Separate financial blocker

`payment.refund_failed` is still planned while code can assign final FAILED refund
states. The existing notification test reproduces this mismatch. It is explicitly
a release blocker in the test registry. No refund, payment, order or subscription
logic was modified; a separate financial/product assignment must resolve it.
