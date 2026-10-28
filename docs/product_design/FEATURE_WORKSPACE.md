# ReturnSaiyan — Product Design Workspace

> [!IMPORTANT]
> **SOURCE OF TRUTH FOR USER-APPROVED PRODUCT RULES.**
> This workspace starts empty. The legacy 68-WP catalog is
> [NOT_APPROVED — DO NOT EXECUTE](../production/RETURNSAIYAN_FUNCTIONAL_SLICE_WP_REGISTRY_V1.md).
> Nothing in that catalog is automatically approved by creating this workspace.

## Design session protocol (owner-approved on 2026-10-28)

- **Starting with the next chat session**, the assistant presents **one interactive form for exactly one function or product rule**. Do not open a second feature form in the same chat.
- The owner chooses or describes the feature and fills the form. Partial answers are allowed; unfilled fields remain **UNKNOWN**, never inferred.
- Review the submission against the fields below. If a missing/contradictory decision would make approval ambiguous, ask a focused question **for that same feature** before finalizing. Explicitly distinguish original-client evidence from new desired game design.
- After the owner has provided a coherent decision, **create or update one corresponding feature specification** at `docs/product_design/features/<FEATURE_ID>.md`, and insert/update **one row** in this workspace table in the **same Git commit** on the working PR branch. Each saved spec records decision provenance and the owner's approval; report commit SHA to the owner.
- The completion of this **design** session does **not** grant implementation, protocol, REA or Android gameplay PASS. No DAG or executable Work Package may be generated from an unapproved item or the legacy catalog.
- Subsequent chats repeat the loop, one feature per chat, with progress read from this GitHub workspace.
- When the owner sends the exact text **`kết thúc`** (trimmed, case-insensitive), **stop offering forms and close the design loop**; keep existing approved decisions unchanged. Do not invent the remaining requirements.
- This is **human-in-the-loop**, not an unattended process. The assistant writes to GitHub during each owner-approved submission; GitHub does not automatically receive data merely because a form is filled.

### Required fields for each function specification

| Field | What the owner decides | Blank/unknown handling |
|---|---|---|
| Feature name, objective, scope | Name, what problem it solves, inclusions/exclusions | Ask only if the feature cannot be identified |
| Product intent | Reproduce original behavior, modify, or add a new behavior | UNKNOWN; do not assume original APK does it |
| Input / preconditions | Player/account/game-state requirements; currency/items/hero, if applicable | UNKNOWN |
| Action / state changes | Player gesture, rules/sequence and business logic | UNKNOWN |
| Output / UI behavior | What the player sees/receives; any response/state changes | UNKNOWN |
| Failure/error states | No resource, invalid state, offline, retry, disconnect, cancellation | UNKNOWN |
| Persistent data | Records saved/changed and persistence across reconnect/relogin | UNKNOWN |
| Acceptance tests | Observable success and negative test with expected result | UNKNOWN |
| Numerical rules / bounds | Cost, probabilities, levels, durations, limits; if applicable | UNKNOWN, never guessed |
| References / conflicts | APK screenshot, Lua, REA, captured packet; competing behavior | Tag SOURCE_VERIFIED, OWNER_SPECIFIED or UNKNOWN |
| Open decisions / dependencies | Questions for later, other accepted feature IDs | Do not manufacture dependencies |

A `USER_APPROVED` label means **product intent approved**, not that
the APK's observed behavior is proven or that implementation passes.
`SOURCE_VERIFIED` requires primary evidence separately. A function may be
fully designed while its client protocol remains `UNKNOWN`.

### Feature workspace table

| ID | Chức năng | Đầu vào | Hành động | Đầu ra | Trạng thái lỗi | Lưu trữ | Nghiệm thu | Quy tắc/giới hạn | Trạng thái | Đặc tả |
|---|---|---|---|---|---|---|---|---|---|---|

*No feature has yet been approved in this workflow. Do not add speculative rows.*

### State and amendment policy

- `DRAFT`: information is being collected and has not been approved.
- `NEEDS_DECISION`: important contradictions or missing design rules remain.
- `USER_APPROVED`: product specification explicitly confirmed by owner; not runtime-proven.
- `SUPERSEDED`: revised by a later user-approved version (link old/new).
- `CLOSED`: design loop ended by owner's `kết thúc`; this is a workflow state, not a feature.

Keep both the original and amended decision trace. Do not silently change
existing approved rows when refining another feature. Distinguish
`SOURCE_VERIFIED`, `OWNER_SPECIFIED`, `INFERRED`, `UNKNOWN` in each
specification, and cite evidence exactly where it exists.

**Repository scope:** `khanhpn308/re_dragon`, current working branch
`fix/p3b-gacha-formation-recovery` (PR #10). Do not modify `main` or
touch accepted V1/V2 production gates to perform design bookkeeping.
