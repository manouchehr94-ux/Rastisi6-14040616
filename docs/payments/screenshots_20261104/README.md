Chromium QA (Playwright) of the unified payment catalog — 76 checks at 1440 / 768 / 390 / 320 px (all passed):
`finance_<w>.png` = `/admin-portal/settings/?section=payment-config` (12 accordions: 10 online providers + COD + card transfer; honest statuses: active / documentation-blocked / needs credentials; blocked provider switch is aria-disabled and explains why),
`checkout_<w>.png` = storefront checkout (offered: Zibal, Zarinpal, card transfer, SnappPay (sandbox), COD; never offered: Pasargad (incomplete), Mellat/Saman (documentation-blocked)). No horizontal overflow, no page errors.
Seeded disposable database; no real provider was called.
