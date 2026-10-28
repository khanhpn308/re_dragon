# P3b controlled recovery (not gameplay acceptance)

This patch introduces additive owned-hero and formation tables, a test-only
backend persistence foundation, and a **review-gated** blocked-task recovery.

## Known unresolved client requirement
Real Android logs show `drawCard:open:1` and Lua `mType == nil`.
`game-server/internal/session/handler.go` currently logs any colon-delimited
0x25 RPC and returns without processing it. No faithful S2C drawCard wire
format, currency semantics, or formation picker protocol is established from
the pushed source tree. Do **not** guess 0x20 as a gacha opcode (currently
movement). Do not report real Android summon as PASS based on this patch.

## Safe sequence
1. Inspect and reproduce on physical RMX3461, trace client callback and server
   RPC; add a source-backed decode/encode contract and tests.
2. Approve explicit eligible hero pool and currency cost; for a free tutorial
   summon, show evidence it is actually free. Connect the backend repository
   only after the client-compatible S2C contract is proven.
3. Review SQL migration 000003 and backup live database. It has NOT been
   applied by this PR. Rollback is destructive.
4. Run tests (Go/Python); have a genuinely separate reviewer inspect the
   code and source evidence. Then explicitly run:

```bash
python3 scripts/blocked_rework.py prepare --state-dir .re_harness_mvp \
 --project-id e2ff7b42242746d4 --task-key P3b-hero-onboarding-preflight \
 --reason "Implemented and independently tested genuine summon protocol" \
 --evidence docs/production/P3B_HERO_ONBOARDING_PREFLIGHT_BLOCKED_REPORT.md --confirm
```

That creates an audit task but **keeps P3b BLOCKED**. After this new audit
is VERIFIED by an independent reviewer, use the returned audit key:

```bash
python3 scripts/blocked_rework.py apply --state-dir .re_harness_mvp \
 --project-id e2ff7b42242746d4 --task-key P3b-hero-onboarding-preflight \
 --audit-key audit-blocked-XXXXXXXXXX \
 --reason "Reviewed source, tests, protocol and Android evidence" --confirm
```

The apply call transitions P3b to REWORK, never VERIFIED. Preserve archived
evidence. Before either command ensure the existing Watchdog/Agent has no
in-flight competing turn; the controller lease does not prove process absence.

## Non-negotiable Android gate
All screenshots must be opened and *semantically* checked by an independent
reviewer; SHA-256 only proves file identity. Require Earth x1 summon result,
owned hero picker, active right-side lineup, re-login persistence, real Phó bản
stage battle, result and reward. Connecting Server / Adventure screens fail.
