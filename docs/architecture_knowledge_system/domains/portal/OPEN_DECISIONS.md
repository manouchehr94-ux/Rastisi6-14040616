# portal — Open Decisions

```
domain_id: D2
code_baseline: 5883a140
```

Full detail: [`../../canonical/ARCHITECTURAL_DECISION_REGISTER.md`](../../canonical/ARCHITECTURAL_DECISION_REGISTER.md).

| DR | Title | Why it affects portal | Blocks |
|---|---|---|---|
| **DR-4** | Ownership-transfer duplication | portal's `ownership_transfer_service` (OTP flow) is one of the two live transfer paths; it calls `owner_auth_service.get_or_create_owner_by_phone` | unifying/choosing the transfer path |

## Related findings (not DRs)
- **M15** — `is_staff` overloaded (platform admin requires it; dashboard ignores it).

No option is selected.
