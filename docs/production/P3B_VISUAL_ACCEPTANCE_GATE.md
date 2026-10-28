# Physical Android visual acceptance policy (P3b–P8)

Run `python3 -m tools.e2e_runner.evidence_review --root PATH_TO_RUN_DIR
--manifest PATH_TO_RUN_MANIFEST` to produce `visual_review.html`.
Only files inside the immutable run directory are allowed. The tool checks
PNG headers, byte counts, hashes and duplication, then outputs
`visual_review=REQUIRED` and `acceptance=NOT_VERIFIED`. It **never** certifies
visual semantics.

An independent reviewer must inspect the original images alongside server
logs, logcat, device identity, SQL records and phase timestamps for:
1. Earth Dragon x1 return of *one hero*;
2. persistent account-owned hero and picker;
3. populated active formation after relogin;
4. real Phó bản or Chiến đấu stage (not Adventure / flying cloud);
5. actual battle actions, enemy response, results and reward persistence.

Do not mark a task VERIFIED when only a click occurred, only an animation is
visible, or a screenshot depicts Connecting Server. Keep all old run artifacts.
Document independent reviewer decision with per-image assertions separately.
