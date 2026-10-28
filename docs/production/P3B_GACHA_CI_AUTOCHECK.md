# P3b gacha contract auto-check (GitHub Actions)

Commit changes to the PR branch, then use the GitHub **Checks** tab. The
"P3b Gacha Protocol — source audit" workflow runs automatically and publishes
a Markdown summary plus a downloadable JSON report.

**Expected current result: BLOCKED.** In the current Go session handler,
colon-delimited RPCs including drawCard are logged and silently returned,
with no proven server-compatible S2C. The original client Lua S2C contract
and a dedicated packet-level test are not present in committed source.

This static test checks prerequisites only. It does not access private APKs,
modify PostgreSQL, run Android, alter Harness state, or certify physical
summon/formation. A green source gate would still mean Android NOT_RUN.
The prior mType=nil Lua log predates the cited tap; causality is unconfirmed.

To clear the source gate legitimately: independently trace original client
S2C, document it in P3B_GACHA_S2C_CONTRACT.md, implement actual Go RPC
dispatch, and add gacha_wire_test.go. Only then run physical Android E2E.
