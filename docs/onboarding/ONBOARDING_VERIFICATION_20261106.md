# Registration and store onboarding — verification — 2026-11-06

Branch `ux/platform-merchant-remediation-20261106`. **No code was changed for this item**: the brief asks to prove status through tests and not to rebuild existing work.
Evidence run: 11 modules, **285 tests, OK (exit 0)** on PostgreSQL 16.15:
`test_mandatory_industry`, `test_onboarding`, `test_onboarding_authorization`, `test_onboarding_density`, `test_onboarding_industry_ux`, `test_onboarding_journey`, `test_onboarding_ready_template`,
`test_onboarding_template_fidelity`, `test_owner_signup_credentials`, `test_supported_industries_page`, `test_platform_admin_industries`.

## ONBOARDING-01 — mandatory industry selection
| Requirement | Status | Evidence |
|---|---|---|
| Selection cannot be bypassed (backend) | ALREADY_FIXED (verified) | `test_publication_is_refused_without_an_industry`; `test_skip_is_refused_and_installs_nothing`; `onboarding_publish_service` requires an installed industry (`NO_INDUSTRY_MESSAGE`) |
| Only a valid, offerable industry can be installed | ALREADY_FIXED (verified) | `test_a_forged_unknown_or_non_offerable_id_cannot_install`; `test_only_the_exact_confirmation_value_installs` |
| Industry data loads correctly; registry readiness is checked | ALREADY_FIXED (verified) | `industry_registry_readiness` (107-template registry loads via `ensure_industry_registry --apply`); `test_search_and_sector_filters_remain_and_every_offerable_industry_is_discoverable` |
| `سایر (صنف آزاد)` exists | ALREADY_FIXED (verified) | catalog entry `slug="other"` (`approved_catalog.py`); readiness check fails if it is not offerable; `test_the_free_form_choice_is_a_valid_complete_industry_for_the_checklist`; `test_a_second_store_choosing_other_gets_its_own_rows` |
| **A custom industry name can be typed when appropriate** | **NEEDS_OWNER_DECISION — not implemented** | "سایر" is a generic catalog entry (no attributes); there is **no free-text industry-name field** in any model or template. Adding one needs a schema change (e.g. a name on the installation) plus validation and UX — a product decision, not done here |
| Selection persists across onboarding steps; resume works | ALREADY_FIXED (verified) | `test_dispatcher_resumes_at_the_saved_stage`; `test_order_progress_and_resume`; `test_industry_stage_already_installed_never_installs_twice`; `test_a_shop_that_is_already_published_is_not_sent_back_to_the_industry_step` |
| Industry choice is separate from installing a visual template | ALREADY_FIXED (verified) | `test_industry_template_stays_independent_of_the_ready_template`; `test_review_shows_the_chosen_visual_template_separately_from_the_industry_template` |
| Template can be changed later; industry does not restrict design | ALREADY_FIXED (verified) | `test_choosing_another_template_uses_the_preservation_first_switch`; `test_explicitly_choosing_the_latest_card_performs_the_upgrade` |

## ONBOARDING-02 — journey: public site → registration → verification → industry → details → template → setup → create → dashboard → preview → publish
| Aspect | Status | Evidence |
|---|---|---|
| Validation, values kept on error | ALREADY_FIXED (verified) | `test_every_field_error_is_rendered_and_values_are_preserved`; `test_a_rejected_submit_keeps_the_selection_checked` |
| Back navigation | ALREADY_FIXED (verified) | `test_previous_links_chain_through_the_template_step` |
| Duplicate-store prevention / replay / double submit | ALREADY_FIXED (verified) | `test_replaying_the_successful_post_never_creates_a_second_store`; `test_double_submit_refresh_and_replayed_post_never_duplicate_anything`; `test_if_the_owner_appears_meanwhile_completion_logs_in_without_a_second_store`; `test_double_submit_does_not_republish_or_rewrite_the_first_timestamp` |
| Tenant ownership / authorization | ALREADY_FIXED (verified) | `test_cross_store_request_cannot_mutate_another_store`; `test_a_member_without_settings_manage_cannot_apply_or_advance`; `test_a_member_without_settings_manage_cannot_publish` |
| Redirect correctness, unfinished store routed back into the wizard | ALREADY_FIXED (verified) | `test_unfinished_store_is_pointed_back_into_the_wizard`; `test_an_old_unpublished_store_at_branding_or_review_without_a_template_is_routed_through_the_step` |
| A new store stays private until final Publish | ALREADY_FIXED (verified) | `test_without_a_subscription_the_anonymous_storefront_is_private_until_the_final_publish`; `test_a_failed_publish_keeps_the_no_subscription_store_private` (this branch's QA store behaved exactly so: 403 until `onboarding_completed_at` was set) |
| Provider failures / controlled errors | ALREADY_FIXED (verified) | `test_expected_domain_publication_failures_become_controlled_persian_errors`; `test_a_database_error_during_publish_is_controlled_and_rolls_back` |
| Mobile layout | ALREADY_FIXED (static) | `test_onboarding_density` (mobile step summary, no viewport-height layouts) — **not exercised in a real browser** |
| Real-browser end-to-end walk of the whole journey | **NEEDS_MANUAL_VALIDATION** | registration and verification are OTP-gated; no real SMS/email was sent and the OTP steps were not driven through a browser in this QA |

## Residual risks
1. The free-text industry name (above) — owner decision.
2. The 3 `InFlightDeliveryConcurrencyTests` in `test_owner_registration_hardening` fail on the unmodified Checkout baseline too (pre-existing; they appear as setUpClass errors when run after other test classes). They concern OTP-resend delivery concurrency, not the onboarding flow above.
