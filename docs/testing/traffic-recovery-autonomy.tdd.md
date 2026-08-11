# Traffic recovery autonomy — TDD evidence

## Source and journeys

Journeys were derived from the operator request on 2026-08-11:

- As the Bloom operator, I want zero-traffic articles processed in a bounded
  queue so that work does not grow linearly with the alert count.
- As the Bloom operator, I want cooldowns and attempt history so that agents do
  not repeat actions before results can be measured.
- As the Bloom operator, I want unsafe content changes rejected so that greater
  autonomy remains reversible and auditable.

## RED and GREEN evidence

| Guarantee | Test | Evidence |
|---|---|---|
| Commercial candidates are prioritized and daily work is limited | `TrafficRecoveryPolicyTests.test_limits_daily_work_and_prioritizes_commercial_candidates` | RED: import failed because the policy did not exist. GREEN: test passes. |
| A completed attempt creates a seven-day cooldown | `TrafficRecoveryPolicyTests.test_waits_seven_days_after_a_completed_attempt` | GREEN in the 50-test API suite. |
| Two measured cycles without traffic become a human exception | `TrafficRecoveryPolicyTests.test_escalates_after_two_unsuccessful_cycles` | GREEN in the 50-test API suite. |
| Published-post rewrites cannot be submitted by the restricted tool | `TrafficRecoveryPolicyTests.test_rejects_unsafe_agent_action` | GREEN through Pydantic action allowlist validation. |
| Low-risk, evidenced actions are accepted | `TrafficRecoveryPolicyTests.test_accepts_auditable_low_risk_action` | GREEN in the 50-test API suite. |

RED command: `python -m unittest test_content_security.py` from `api/`.
The run failed on the intended missing `TrafficRecoveryAttemptCreate` import.

GREEN command: `python -m unittest discover -s api -p "test_*.py"`.
Result: `Ran 50 tests ... OK`.

Static validation: `python -m py_compile api/main.py hermes/bloom_content/__init__.py`
and `git diff --check`, both successful.

## Coverage and known gaps

The environment does not have the Python `coverage` package installed, so a
numeric coverage report could not be produced (`No module named coverage`).
The policy branches introduced in this change are exercised directly. Database
endpoint behavior still depends on the PostgreSQL migration and production
smoke test during rollout.

## Checkpoints

- RED checkpoint: `b17dc2c test: define traffic recovery autonomy policy`.
- GREEN checkpoint: recorded in the implementation commit that follows this
  report.
