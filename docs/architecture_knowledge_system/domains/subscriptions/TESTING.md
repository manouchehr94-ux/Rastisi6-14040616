# subscriptions — Testing

```
domain_id: D7
code_baseline: 5883a140
source: apps/subscriptions/tests/
```

| Behavior | Test file |
|---|---|
| State machine (transitions, legality, idempotency, terminal) | `test_state_machine.py` |
| Plan change | `test_plan_change.py` |
| Manual trial controls | `test_manual_trial_controls.py` |
| Management commands + tenant isolation | `test_management_and_isolation.py` |

## Coverage posture
The canonical state machine is directly tested (transition legality + idempotency). Cross-domain
activation via billing is tested in `apps/billing/tests/test_confirmation_activation.py`.
See canonical [`../../canonical/TESTING_MAP.md`](../../canonical/TESTING_MAP.md).
