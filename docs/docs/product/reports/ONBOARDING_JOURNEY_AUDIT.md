# Onboarding Journey Audit — store-create → wizard → store-created

Scope: the owner journey from "first store exists" to "store published", plus the shared industry-template
gate that feeds it. Not in scope: Merchant Admin redesign, registration/login pages (already on the public
shell), billing.

## Design approach

* **One shell.** `portal/onboarding/base_onboarding.html` extends the platform base but replaces the legacy
  dark header/footer with a focused authenticated header (brand · current store name · "ذخیره و بازگشت")
  and loads `public-site-v2.css` (the single `--rs-*` token source) plus `portal/css/onboarding.css`.
  No second palette; no colour literals (pinned by `test_onboarding_stylesheet_has_no_colour_literals_outside_tokens`);
  no inline styles and no legacy `p-*` / `industry-*` classes in any journey template (pinned by test).
* **One progress model.** `views._onboarding_shell_context` derives the 4-step indicator
  (معرفی · صنف · ظاهر · بازبینی) from `Store.onboarding_stage`: done steps are links, the furthest reached step is
  current/available, later steps are locked. Purely presentational — no authorization logic.
* **One action bar.** Previous · (Skip on optional steps) · Continue, identical on every stage; Skip is a separate
  POST form attached with the HTML `form=` attribute.
* **Real data only.** Industry cards/previews come from `catalog.services.template_summary_service`
  (batch queries, constant query count): category tree highlights, attribute labels, variant axes,
  schema-mapping counts, recommended options, default section labels (unknown keys dropped), and exactly what
  install creates. Default sections are shown as *suggested later via Storefront Builder* — install does not apply them.

## Per-stage changes

| Stage | Change |
|---|---|
| Store create | Same shell + selector + real previews; "بدونِ صنف" is an explicit choice; forged/non-offerable id → store is created without a template and a warning explains; `submission_token` double-submit protection kept. |
| 1 Identity | Required/optional tags, hints (`help_text`), **all** field errors + focused error summary, LTR-safe phone/email, values preserved on error, placeholders never saved. |
| 2 Industry | Search + sector chips (only sectors that have offerable templates), radio cards, live preview panel, "what install creates", irreversible-install confirmation (checkbox gates the CTA), skip explained, installed-state summary (Continue idempotent), no-template state with a working continue, friendly errors for empty/forged/non-offerable selection, race-safe second install. |
| 3 Branding | Current/new logo preview, `accept` + guidance matching the real backend check (Pillow `ImageField`; no app-level size cap — size is guidance only), real backend error shown, honest note that colours/layout live in Storefront Builder (no fake colour controls). |
| 4 Review | Identity/contact summary with empty-state labels, template + logo summary, edit links, trial hostname (LTR), **real** publication state (`publication_service`), what-publishing-does list that only claims visibility when the real state says so, idempotent publish (timestamp not overwritten). |
| Store created | Adaptive: unfinished → "continue setup" (no admin button); published → real hostname, admin entry (only for active stores), next steps. |

## Gap list

| # | Gap found | Status |
|---|---|---|
| 1 | Registration → first store → wizard redirect | OK already (`_finish_owner_login`); unchanged |
| 2 | Resume mid-wizard | OK (dispatcher + "ادامه‌ی راه‌اندازی"); now tested |
| 3 | Revisit earlier steps | **Fixed** — stepper links; never loses progress (tested) |
| 4 | Skip semantics unexplained | **Fixed** — explained on the industry step |
| 5 | One-time install not clearly irreversible | **Fixed** — confirmation checkbox + copy |
| 6 | Forged / unknown template id → 404 page or silent reload | **Fixed** — friendly error, nothing installed (tested for review_required, inactive, deprecated, draft, unknown) |
| 7 | Empty industry POST silently reloaded | **Fixed** — explicit message |
| 8 | Double-click / concurrent install showed "already installed" error | **Fixed** — treated as success and advances |
| 9 | Publish POST re-stamped `onboarding_completed_at` and re-flashed success | **Fixed** — idempotent |
| 10 | Review/created pages implied "public" without checking state | **Fixed** — driven by `publication_service` |
| 11 | Only the first (name) form error rendered; image upload errors invisible-ish | **Fixed** |
| 12 | Store-created page was a dead end for unfinished stores | **Fixed** |
| 13 | Legacy search input contrast bug class (dark theme) | **Removed at the root** (journey no longer uses the dark selector) |
| 14 | Mobile layout, long Persian names, LTR phone/email/hostname | **Fixed** — verified in browser at 390px |
| 15 | `portal/403.html` (permission denied on POST) is the legacy dark page | **Deferred** — shared portal-wide page, tests pin its template; restyle with the rest of the portal account area |
| 16 | "فروشگاه‌های من" (`my_stores.html`) is still legacy-styled; "ذخیره و بازگشت" lands there | **Deferred** — account-area redesign, outside this journey |
| 17 | GET of a stage by a member without `SETTINGS_MANAGE` shows editable forms (POST is denied with 403) | **Deferred** — read-only variant needs product decision; no security impact (POST gate unchanged) |
| 18 | 76 of 107 templates are skeletal and now held at `review_required` | **Content backlog** — see `INDUSTRY_TEMPLATE_COMPLETENESS_AUDIT.md` |
| 19 | No app-level logo size/format limit beyond "is an image" | **Deferred** — would be a backend behaviour change; guidance only |
