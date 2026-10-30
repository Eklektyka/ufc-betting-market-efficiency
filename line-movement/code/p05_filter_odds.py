"""
filter_odds.py
--------------
Flags corrupted odds rows and writes a clean copy of ufc_fights_shin.csv.

Filter rules (applied independently per line type):
  close_lo / open : drop if vig < 0pp or vig > 20pp
  close_hi        : drop if vig < -15pp or vig > 20pp
                    (negative vig on close_hi is expected from cross-book
                     line-shopping; only extreme negatives are corruptions)

A row is flagged bad if ANY of its three line types fails.
Flagged rows keep their odds columns but get odds_clean = False so the
user can filter in analysis. The Shin p_ columns for bad lines are zeroed.
"""

import csv, sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

IN_CSV  = Path("merged/ufc_fights_shin.csv")
OUT_CSV = Path("merged/ufc_fights_clean.csv")

def to_prob(v):
    try: v = float(v)
    except: return None
    if v == 0: return None
    return abs(v) / (abs(v) + 100) if v < 0 else 100 / (v + 100)

with IN_CSV.open(encoding="utf-8") as f:
    rows = list(csv.DictReader(f))
    in_fields = list(rows[0].keys())

LINE_CHECKS = [
    # (a_col, b_col, vig_min, vig_max, pa_col, pb_col, z_col)
    ("odds_open",     "odds_opp_open",
     0.00, 0.20,
     "p_open_a",     "p_open_b",     "shin_z_open"),
    ("odds_close_lo", "odds_opp_close_lo",
     0.00, 0.20,
     "p_close_lo_a", "p_close_lo_b", "shin_z_close_lo"),
    ("odds_close_hi", "odds_opp_close_hi",
     -0.15, 0.20,
     "p_close_hi_a", "p_close_hi_b", "shin_z_close_hi"),
]

flagged = 0
line_flags = {lc[0]: 0 for lc in LINE_CHECKS}

for r in rows:
    r["odds_clean"] = "True"
    for a_col, b_col, vmin, vmax, pa, pb, pz in LINE_CHECKS:
        qa = to_prob(r.get(a_col, ""))
        qb = to_prob(r.get(b_col, ""))
        if qa is None or qb is None:
            continue
        vig = qa + qb - 1
        if vig < vmin or vig > vmax:
            # Zero out the Shin probabilities for this line
            r[pa] = r[pb] = r[pz] = ""
            r["odds_clean"] = "False"
            line_flags[a_col] += 1

for r in rows:
    if r["odds_clean"] == "False":
        flagged += 1

out_fields = in_fields + ["odds_clean"]
with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=out_fields)
    w.writeheader()
    w.writerows(rows)

total = len(rows)
print(f"Total fights:   {total}")
print(f"Flagged bad:    {flagged} ({flagged/total*100:.2f}%)")
print(f"Clean fights:   {total-flagged} ({(total-flagged)/total*100:.2f}%)")
print()
print("Flags by line type (vig out of bounds):")
for a_col, *_ in LINE_CHECKS:
    label = a_col.replace("odds_", "")
    print(f"  {label:<12}: {line_flags[a_col]}")
print(f"\nOutput: {OUT_CSV}")
