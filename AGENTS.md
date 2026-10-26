# AGENTS.md — RE Dragon

Canonical source repository: https://github.com/khanhpn308/re_dragon

## Mission

Analyze local ReturnSaiyan Android native binaries with REA and Ghidra. Preserve evidence and avoid unsupported protocol claims.

## Execution

- Use WSL2 Ubuntu with local ELF and REA installed.
- Plan: python3 -m re_harness plan --binary ./libaos_jogo.so
- Work: python3 -m re_harness worker --run-id ID --max-steps 1 --capacity 1
- Resume: python3 -m re_harness resume --run-id ID
- Graph: python3 -m re_harness graph-start --run-id ID --root EXACT_SYMBOL_OR_ADDRESS
- Candidates: python3 -m re_harness evidence --run-id ID
- Recover: python3 -m re_harness recover --run-id ID
- Validate/report: python3 -m re_harness validate --run-id ID and report --run-id ID
- MCP: python3 -m re_harness.mcp

## Multi-Agent rules

1. Share one SQLite state directory and use identical engine capacity (default 1).
2. Claim tasks through the harness, not parallel unmanaged REA runs.
3. Do not reclaim leases from still-running native processes.
4. Review raw REA Evidence including coverage and limitations before scientific claims.
5. Static call edges and symbol candidates are hypotheses, not runtime truth.
6. Mark VERIFIED, INFERRED and UNKNOWN distinctly; G4 requires semantic review.
7. Do not contact game servers or capture credentials without explicit scope.
8. Commit code, workflow JSON and safe curated reports only. Never commit APK/SO, secrets, packet captures or raw evidence.
9. Prioritize delivered code as requested; do not claim unrun tests passed.

Reference: docs/STABLE.md.
