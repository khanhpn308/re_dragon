# DISPUTED ACCEPTANCE FINDING: Historical Project 6181397b27b247e9

**Date:** 2026-10-28  
**Scope:** Combat and Hero Roster Verification Claims in Project `6181397b27b247e9`  
**Supervising Project:** `e2ff7b42242746d4` (`RS-UH-V2-REAL-DUNGEON-COMBAT-E2E`)  
**Status:** DISPUTED_ACCEPTANCE (Preserved Historical Baseline, Explicit Non-Regression Gate)

---

## 1. Discrepancy Identification

In historical project `6181397b27b247e9`, task `p4-e2e-gameplay-action-verification` and project-level gate `p6-final-playability-audit` were accepted based on automated scripts (`tools/e2e_runner/orchestrator_gameplay_e2e.py` and `tools/e2e_runner/test_p4_actions.py`).

Independent secondary inspection of the primary evidence artifacts revealed that:
1. **03_world_entry.png** is the **Main Lobby** scene post-login, not an in-world combat or exploration stage.
2. **04c_combat_skill.png** and **04d_hero_roster.png** captured a flying-cloud / "Connecting Server..." / Adventure mode backdrop rather than a rendered combat stage, enemy sprites, damage indicators, or actual hero roster UI.
3. Blind touch inputs at hardcoded coordinates (e.g. `(2150, 920)`, `(1950, 950)`, `(1380, 1000)`) were executed without validating the active scene or waiting for scene transitions.
4. Raw packet reception (Opcode 0x25) and non-zero RMS RGB deltas were erroneously treated as proof of verified combat gameplay.
5. In-stage enemy engagement, combat mechanics, stage victory/defeat, reward settlement, and persistent stage progression were never independently demonstrated on the physical device.

---

## 2. Evidence References

- Primary artifacts in dispute:
  - `evidence/s6_e2e/03_world_entry.png` (Main Lobby)
  - `evidence/s6_e2e/04c_combat_skill.png` (Scene misclassified as combat skill)
  - `evidence/s6_e2e/04d_hero_roster.png` (Scene misclassified as hero roster)
  - `docs/production/P4_E2E_GAMEPLAY_ACTION_VERIFICATION_REPORT.md`
  - `docs/production/P6_FINAL_PLAYABILITY_AUDIT_REPORT.md`
  - `docs/production/RS_REAL_DUNGEON_COMBAT_E2E_HANDOFF.md`

---

## 3. Preservation & Non-Regression Policy

In compliance with the RS-UH-PROD-V2 charter and `AGENTS.md`:
- Historical project `6181397b27b247e9` records, timestamps, and files in `evidence/s6_e2e/` remain **strictly immutable** and are not deleted or overwritten.
- All new validation for real dungeon combat runs in dedicated, clean-room evidence paths (`evidence/real_dungeon_combat/<UTC_run_id>/`).
- Project `e2ff7b42242746d4` formally records this dispute to establish the requirement for genuine, observable state-aware scene navigation and verified in-stage combat before any subsequent release gate.
