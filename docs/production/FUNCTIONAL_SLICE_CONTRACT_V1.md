# Functional Slice Contract v1: code-enforced evidence budgets

**No time-based functional-slice deadline.** A task may continue while it has
work remaining, a valid claim and its required host/REA permissions. Do not
launch Agent analysis using shell 'timeout 600' or 'timeout 900'.

This opt-in, backward-compatible Harness change adds:
- \`harness_slice_define\`: freeze feature, objective, SHA-256, entrypoints,
  1–8 scope targets, questions, deliverables, acceptance and per-slice budgets.
- \`harness_slice_reserve\`: approve a call only within an allowed target,
  max REA calls 30, max XREF depth 2, at most one outstanding call.
- \`harness_slice_receipt\`: require result SHA-256, function ID, confidence and
  evidence reference instead of raw decompiler dumps. Reject reported output
  above 16,000 chars and more than 8 distinct functions.
- \`harness_auto_submit\`: registered analyses cannot be submitted without
  completed receipts, a matching VERIFIED evidence reference and the
  frozen list of artifacts. Normal independent review still required.
- \`harness_slice_checkpoint_split\`: preserve work and enter SPLIT_REQUIRED
  to use existing bounded child scope decomposition, no timer involved.

**Important limitation:** these restrictions are enforced at the Harness API
boundary, *not* on direct external REA MCP tool calls. To hard-limit every REA
read at the host level, route REA calls through a gateway that invokes reserve
and receipt, or disallow bypass tool access. Do not claim an external call was
prevented merely because the Harness could reject a receipt. SHA-256 and
evidence refs are still Agent-submitted until independently checked.

The existing 1,200-second claim lease (renewable) and the Watchdog's CLI turn
limits remain distinct failure/recovery mechanisms. This patch does not
change active V1/V2 checkpoints or OS-level supervision. Those independent
limits require host-side renewal/continuation and are not a slice timeout.

Use for a newly approved, narrow ANALYZE task, not for automatically
reopening the currently BLOCKED P3b. Python regression test:
\`python -m unittest discover -s tests -p test_functional_slices.py -v\`.
