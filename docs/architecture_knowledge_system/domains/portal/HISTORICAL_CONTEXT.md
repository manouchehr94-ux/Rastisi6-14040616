# portal — Historical Context

```
domain_id: D2
code_baseline: 5883a140
```

Evidence/history only — not modified/moved/archived here.

| Document | Level | Relationship to code | Label |
|---|---|---|---|
| `SAAS_DOMAIN_DECISIONS.md` ADR-97 | L3 ADR | MATCHES_CODE — owner portal + platform-admin host partitioning (PlatformHostRoutingMiddleware) | AUTHORITATIVE-INTENT |
| ADR-98 | L3 ADR | MATCHES_CODE — admin handoff / support login | AUTHORITATIVE-INTENT |
| ADR-101 | L3 ADR | MATCHES_CODE — platform-admin host, retired-domain safe response | AUTHORITATIVE-INTENT |
| **ADR-93 (superseded by ADR-102)** | L3 ADR | ADR-93 (email/password owner identity) SUPERSEDED by ADR-102 (mobile OTP, shared phone identity); code follows ADR-102 | SUPERSEDED→ADR-102 |
| ADR-102 | L3 ADR | MATCHES_CODE — PlatformConfiguration singleton + owner mobile OTP shared with customer phone identity | AUTHORITATIVE-INTENT |
| `00_PROJECT_MASTER_REFERENCE.md` | L3 | platform vs store framing | CONTEXT |

## Key point
The host partitioning (ADR-97) and the owner-identity evolution (ADR-93 → ADR-102, mobile OTP +
shared phone identity) are implemented as documented. When reading ADR-93, note it is **superseded**
by ADR-102 — the code follows ADR-102.
