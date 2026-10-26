# P0 live acceptance — autonomous controller + REAL Antigravity subagent

**Purpose:** Before letting RE Dragon operate on a large ReturnSaiyan workload,
validate the actual Antigravity CLI LLM behavior, not only simulated SQLite
actors. The live pilot is isolated, bounded, offline and should not modify
production codec files, game binaries or the main research project.

## Preconditions

- Git pull current main and restart Antigravity CLI to reload Harness MCP.
- Open Antigravity CLI in the re_dragon repo, where AGENTS.md is available.
- RE Dragon Harness MCP tools are discoverable.
- Check /agents for re-dragon-reviewer in Available Agents.
- Permission policy must allow the Agent to create an **isolated temp copy** of
  the fixture, invoke a subagent, and write only under a local scratch
  directory. No external game-server/network calls.
- Do not run full REA/Ghidra auto-analysis. This test is about orchestration.

## One live pilot prompt for Antigravity CLI

> Execute ONLY the RE Dragon v0.5 autonomy pilot described in
> docs/LIVE_PILOT.md. Do not begin the production ReturnSaiyan tasks.
>
> Call harness_auto_projects. Create ONE isolated project with goal
> "PILOT: validate 3-task continuous autonomous loop and real independent
> subagent review"; acceptance requires (1) reviewer rejects a known buggy
> synthetic decoder based on a separate primary-spec inspection, (2) executor
> repairs a disposable copy and reviewer accepts the revised copy, (3) an
> automatically scheduled dependent task completes without a new user prompt,
> and (4) durable events and distinct session IDs can be inspected.
>
> Plan two dependent tasks:
> - inspect-and-repair-fixture (IMPLEMENT): work on a temp copy of
>   pilot/buggy_decoder.py, inspect pilot/SPEC.md; submit the original
>   defective candidate first with the current failed test result to test
>   rejection. Do not falsely claim success; after REJECT, repair the
>   disposable copy, run pilot/test_fixture_oracle.py against the copy and
>   resubmit as REWORK.
> - continuation (DOCUMENT): depends on the reviewed fixture task; record
>   tests and a pilot handoff under the local ignored scratch directory.
>
> The main Agent MUST call harness_auto_tick after every submit and review
> without asking me for P1/P2 prompt. The reviewer must be a REAL spawned
> subagent (invoke_subagent using re-dragon-reviewer, isolated context).
> Show its actual ID under /agents and inspect its tool calls. Do not fake a
> reviewer by changing a string. The subagent itself should claim/review via
> MCP if available; otherwise report REVIEW_BLOCKED without impersonation.
>
> Call harness_pilot_evaluate after the run. Record the returned checks, the
> actual subagent ID and link to the inspectable /agents transcript. Export
> harness_auto_report and summarize GO/NO-GO; NEVER promote to GO solely
> because controller SQL checks passed.

## Required independent-review failure injection

The fixture at pilot/buggy_decoder.py deliberately disagrees with pilot/SPEC.md
in endianness and surplus-byte handling. **First review must REJECT** with a
concrete counterexample, even if the executor reports a plausible success.

After REJECT the executor may fix its isolated copy, rerun oracle, resubmit,
and request another genuine subagent review. The second review should APPROVE
only after independently inspecting the fixed copy.

## GO criteria (all required)

1. A real, visible subagent ID exists in Antigravity /agents; its own
   conversation/tool logs show the inspection and verdict.
2. The main Agent performed >1 work task, including follow-up work initiated
   by harness_auto_tick without a second user prompt.
3. REVIEW_REJECT preceded REVIEW_APPROVE for the same task; actual evidence is
   recorded with exact local paths and failed/passing oracle output.
4. The dependent continuation task unlocked only after review approval.
5. A fresh Antigravity session can discover the project via
   harness_auto_projects and read the handoff without a user-supplied ID.
6. No source APK/SO mutated, no network calls to game endpoints, and no
   production Git push from the pilot.

## Decision boundaries

- harness_pilot_evaluate verifies the **SQLite event trace only**. It
  intentionally reports the live subagent identity as UNATTESTED. Inspect
  /agents transcript to establish actual execution.
- Missing distinct reviewer subagent, same-session reviewer spoof,
  repeated manual prompts, missing REJECT or a blocked continuation = NO-GO.
- A reviewer that returns BLOCKED due to MCP access is a valid finding;
  integration must be fixed before a bulk production run.
- Do not mark the pilot complete if human/operator has not confirmed the
  separate subagent run via /agents.
