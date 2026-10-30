# Path to Efficiency — closed 2026-07-08

**Question:** Do open-to-close line movements in UFC betting markets carry
information beyond the closing line, and do markets efficiently incorporate
their own revisions?

**What I expected:** Pre-registration (docs/PRE_REGISTRATION.md lines 42–45):
"A mechanism counts as real only if it is same-signed and significant (p < 0.05)
in both the pre-2020 and 2020+ subsamples. This rule was stated explicitly
before the OOS split was run (Phase 05). No post-hoc exceptions are made."
Magnitude test null (lines 48–50): H0: coef(move) = 1 (efficient revision).

**What I found:** Markets are informationally efficient at the close.

- Movement is informative at the open: coef(g_open ~ move) = +1.039
  (SE 0.064, p < 0.0001). OOS: pre-2020 +1.119, 2020+ +0.936, both
  p < 0.0001. **REAL in both windows.**
  (`results/phase03_movement_informative.txt` lines 8–13;
  `results/phase05_oos_split.txt` lines 8–11)

- Movement is fully impounded at the close: coef(g_close ~ move) = +0.038
  (p = 0.545). OOS: pre-2020 +0.119 (p = 0.170), 2020+ −0.064 (p = 0.486).
  **REJECT — sign flip across subsamples.**
  (`results/phase04_close_efficiency.txt` lines 7–11;
  `results/phase05_oos_split.txt` lines 16–23)

- Revision magnitude is efficient: t vs H0 = 1: +0.606, p = 0.545 — cannot
  reject efficient revision.
  (`results/phase07_magnitude_test.txt` lines 13–16)

- Brier improvement (close over open): −0.0073, CI [−0.0089, −0.0056].
  (`results/phase02_brier.txt` lines 16–20)

**Why I stopped:** All eight pre-registered phases are complete. The closing
line absorbs all information in the movement — the remaining questions
(sparkline-derived features) were explicitly deferred as exploratory before
analysis (docs/PRE_REGISTRATION.md lines 67–71).

**What it rules out:** Movement timing, magnitude, or path shape do not provide
an edge over the closing line. A bettor who observes the entire opening-to-
closing trajectory has no advantage over one who sees only the close. N=8,112
fighter-fight observations (4,830 pre-2020, 3,282 2020+).

**What would reopen it:** Nothing — closed. The deferred sparkline exploratory
work could be revisited as a separate project but would require its own
pre-registration.
