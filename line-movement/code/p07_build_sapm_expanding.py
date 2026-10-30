"""
For each fighter, compute the expanding mean of per-fight significant-strikes-absorbed-per-minute
(SAPM) over fights strictly before each bout date.

- Absorbed strikes for fighter A in a fight = sig_str_landed_b (what B landed on A)
- Fight duration = (round - 1)*5 + minutes_elapsed_in_last_round
- Expanding mean is based on all fights strictly before the current fight's date
- Debut fights (no prior fights) are dropped

Output: C:/Users/micha/merged/sapm_expanding.csv
"""

import pandas as pd
import numpy as np

# ── 1. Load ───────────────────────────────────────────────────────────────────
df = pd.read_csv("C:/Users/micha/merged/ufc_fights_clean.csv")
print(f"Loaded {len(df):,} fights")

# ── 2. Parse fight duration ───────────────────────────────────────────────────
def parse_duration(rnd, time_str):
    parts = str(time_str).strip().split(":")
    mins  = int(parts[0])
    secs  = int(parts[1]) if len(parts) > 1 else 0
    return (int(rnd) - 1) * 5 + mins + secs / 60

df["duration_min"] = df.apply(lambda r: parse_duration(r["round"], r["time"]), axis=1)

# ── 3. Parse date ─────────────────────────────────────────────────────────────
df["date"] = pd.to_datetime(df["date"], format="%B %d, %Y")

# ── 4. Reshape to long format (one row per fighter per fight) ─────────────────
keep = ["fight_url", "date", "duration_min"]

a = df[keep + ["fighter_a", "sig_str_landed_b"]].copy()
a.columns = ["fight_url", "date", "duration_min", "fighter", "sig_str_absorbed"]

b = df[keep + ["fighter_b", "sig_str_landed_a"]].copy()
b.columns = ["fight_url", "date", "duration_min", "fighter", "sig_str_absorbed"]

long = pd.concat([a, b], ignore_index=True)
long["duration_min"]     = pd.to_numeric(long["duration_min"],     errors="coerce")
long["sig_str_absorbed"] = pd.to_numeric(long["sig_str_absorbed"], errors="coerce")
long = long[long["duration_min"] > 0].dropna(subset=["sig_str_absorbed", "duration_min"]).copy()
print(f"Rows after cleaning: {len(long):,}")

# ── 5. Per-fight SAPM ─────────────────────────────────────────────────────────
long["sapm"] = long["sig_str_absorbed"] / long["duration_min"]

# ── 6. Expanding mean strictly before each fight date ────────────────────────
#
# Aggregate sapm to (fighter, date) level → cumsum/cumcount → shift by 1 date.
# This correctly handles same-day fights: both share the identical prior mean.

date_agg = (
    long
    .groupby(["fighter", "date"])["sapm"]
    .agg(sapm_sum="sum", sapm_count="count")
    .reset_index()
    .sort_values(["fighter", "date"])
)

# Cumulative sum/count up through each date-block
date_agg["cum_sum"]   = date_agg.groupby("fighter")["sapm_sum"].cumsum()
date_agg["cum_count"] = date_agg.groupby("fighter")["sapm_count"].cumsum()

# Shift by 1 date-block → "all fights before this date"
date_agg["prior_sum"]   = date_agg.groupby("fighter")["cum_sum"].shift(1)
date_agg["prior_count"] = date_agg.groupby("fighter")["cum_count"].shift(1)
date_agg["sapm_r"]      = date_agg["prior_sum"] / date_agg["prior_count"]

# ── 7. Merge back to fight-level ──────────────────────────────────────────────
long = long.merge(
    date_agg[["fighter", "date", "sapm_r"]],
    on=["fighter", "date"],
    how="left"
)

# ── 8. Drop debut fights (NaN prior) ─────────────────────────────────────────
long = long.dropna(subset=["sapm_r"]).reset_index(drop=True)
print(f"Rows after dropping debuts: {len(long):,}")

# ── 9. Save ───────────────────────────────────────────────────────────────────
out_cols = ["fight_url", "date", "fighter", "sig_str_absorbed", "duration_min", "sapm", "sapm_r"]
long[out_cols].to_csv("C:/Users/micha/merged/sapm_expanding.csv", index=False)
print("Saved: C:/Users/micha/merged/sapm_expanding.csv")

# ── 10. Sanity checks ─────────────────────────────────────────────────────────
print("\n── Distribution of sapm_r ──────────────────────────────────────────")
print(long["sapm_r"].describe().round(3).to_string())

# Trace most-frequent fighter
top = long["fighter"].value_counts().idxmax()
sample = (
    long[long["fighter"] == top]
    [["date", "sapm", "sapm_r"]]
    .sort_values("date")
    .head(6)
)
print(f"\nFirst 6 non-debut fights for most-frequent fighter ({top}):")
print(sample.to_string(index=False))

print("\nDone.")
