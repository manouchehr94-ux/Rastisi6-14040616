# UI evidence — notifications admin (store + platform)

Screenshots of the real rendered pages. The desktop set was captured earlier; the `*_mobile.png` set (390 px viewport) was
captured in the finalization pass from the **running QA server** at commit `eb7834ad` (fake provider, seeded QA data), rendered
headless at a phone width. These are reference images for the **manual RTL review** in scenario M — not a substitute for looking at
the live pages on your own machine.

## Desktop
| file | page |
|---|---|
| `store_sender_1_inactive_no_domain.png` | Store sender — INACTIVE, no custom domain (reason, remedy, responsible party) |
| `store_sender_2_pending_dns_records.png` | Store sender — PENDING, the 3 DKIM CNAME records |
| `store_sender_3_error.png` | Store sender — provider error state |
| `store_sender_4_active.png` | Store sender — ACTIVE (`info@…` on the store's own domain) |
| `store_channels.png` | Store channel toggles (SMS / e-mail independent) |
| `store_history.png` | Store notification history |
| `store_template_editor_override_html.png` | Store template editor — HTML e-mail override |
| `store_template_editor_sms_override_order_created.png` | Store template editor — SMS override |
| `store_preview_partial.png` | Template preview partial |
| `platform_catalog.png` | Platform — event catalog |
| `platform_senders.png` | Platform — all stores' sender identities |
| `platform_delivery.png` | Platform — delivery / failures |
| `platform_template_editor.png` | Platform — default template editor |
| `platform_403_no_permission.png` | Platform — 403 for a member without the permission |

## Mobile (390 px viewport)
| file | page |
|---|---|
| `store_sender_active_mobile.png` | Store sender — ACTIVE, RTL at phone width |
| `store_sender_2_pending_dns_records_mobile.png` | Store sender — PENDING, DNS records (earlier capture) |
| `store_channels_mobile.png` | Store channel toggles |
| `store_history_mobile.png` | Store notification history |
| `store_template_editor_mobile.png` | Store template editor (`order.created`) |
| `platform_senders_mobile.png` | Platform — all stores' sender identities |
| `platform_catalog_mobile.png` | Platform — event catalog |

**Expected at mobile width:** right-to-left layout, no horizontal page scroll (the DNS-records table scrolls inside its own box),
every button reachable, the sender status badge and the "two separate verifications" and SPF/DMARC advisory cards legible.
