# Privacy policy accuracy review

The owner's Persian privacy text (dated 16 Aban 1405) is published verbatim at `/privacy/`. It was not edited. This note lists how each claim compares with the code, so the owner can decide on follow-ups. Only the claims below were checked.

| Policy section | Claim | Evidence in code | Status |
|---|---|---|---|
| 4 | Passwords stored hashed | Django `django.contrib.auth` is used. `shop_core/settings.py` does not override `PASSWORD_HASHERS`, so Django's default (PBKDF2) applies, and `AUTH_PASSWORD_VALIDATORS` is set. | Consistent |
| 4 | Admin areas are access-controlled | Dashboard views are login-required with store membership and role checks (see `CLAUDE.md` tenant rules). | Consistent, not exhaustively audited |
| 3 | Stores are prevented from reaching each other's data | Store scoping is a design rule. The public Terms already say this is design intent, not a guarantee, and a repo deployment doc lists Store-boundary hardening as open work. | Partially verified. Do not treat as an absolute guarantee. |
| 5 | Card data is entered at the bank gateway, not at RastiSi | Billing uses redirect-style providers (`apps/billing/providers`). However, a manual card-to-card payment flow exists (`manual_card_service`), where the payer sends money outside the gateway. | Consistent for gateway payments. The manual-card flow is not described in the policy. |
| 5 | SMS, email, security tools and payment gateways are used | `apps/sms`, `apps/notifications`, `apps/portal/services/captcha_service.py` (own math CAPTCHA; Cloudflare Turnstile was removed 2026-11-11) and `apps/billing/providers` exist. | Consistent |
| 5, 6 | Stores may use analytics/ads tools subject to consent | `apps/core/templatetags/consent_tags.py` and tracking tests in `apps/catalog` exist. | Consistent, not exhaustively audited |
| 6 | Essential cookies: session, login state, security | Django session and CSRF cookies. `SESSION_COOKIE_SECURE` and `CSRF_COOKIE_SECURE` default to on outside DEBUG. | Consistent |
| 7 | Account deletion on request via official channels, with retention exceptions | No self-service account-deletion flow was found (only product, campaign and similar deletes). Deletion is therefore a manual support process. | Consistent only if support handles requests. No documented retention schedule in code. |
| 7 | Retention follows "system retention policies" | No central retention policy or purge job was identified. | Unverified. The owner should define one. |
| 10 | "Contact us" page exists | `portal:contact` (`/contact/`) exists and is linked from the policy. | Consistent |

Not verified here: transport encryption in production, backups, and what the SMS/email/payment providers retain.

Related note: the Terms page keeps its section 18, titled as a draft needing legal review, and the "· پیش‌نویس" label in the page eyebrow. The owner asked only for the single disclaimer paragraph to be removed.
