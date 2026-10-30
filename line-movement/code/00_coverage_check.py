"""
Phase 00 — BFO coverage check
==============================
Implements: Phase 0 of the line-efficiency analysis.
Reads:      data/raw/bfo_odds_raw.csv
Writes:     nothing (printed output only; numbers transcribed to results/phase00_coverage.txt)
Result:     10,581 / 12,097 unique fights (87.5%) have real open + close_hi for both corners.
            All opening implied-prob sums > 1 (vig present; Shin devig applicable).
"""

import pandas as pd
import numpy as np

bfo = pd.read_csv("../data/raw/bfo_odds_raw.csv")

bfo['fight_key'] = bfo.apply(
    lambda r: '_'.join(sorted([str(int(r['fighter_bfo_id'])) if pd.notna(r['fighter_bfo_id']) else 'NA',
                                str(int(r['opponent_bfo_id'])) if pd.notna(r['opponent_bfo_id']) else 'NA']))
              + '_' + str(r['event_bfo_id']),
    axis=1
)

fights = bfo.drop_duplicates(subset='fight_key').copy()
N = len(fights)

both_open  = fights['fighter_open'].notna() & fights['opponent_open'].notna()
both_close = fights['fighter_close_hi'].notna() & fights['opponent_close_hi'].notna()
usable     = both_open & both_close

print(f"Unique fights (deduped): {N}")
print(f"(1) Both corners non-null fighter_open:  {both_open.sum()} / {N}  ({100*both_open.mean():.1f}%)")
print(f"(2) Both corners non-null close_hi:      {both_close.sum()} / {N}  ({100*both_close.mean():.1f}%)")
print(f"(3) Usable (both open + both close_hi):  {usable.sum()} / {N}  ({100*usable.mean():.1f}%)")

sample = fights[usable][['fighter_name','fighter_open','fighter_close_hi',
                          'opponent_name','opponent_open','opponent_close_hi',
                          'event_name']].head(5)
print("\n(4) Five example fights:")
print(sample.to_string(index=False))

def american_to_implied(odds):
    odds = pd.to_numeric(odds, errors='coerce')
    result = pd.Series(np.nan, index=odds.index)
    result[odds > 0] = 100 / (odds[odds > 0] + 100)
    result[odds < 0] = -odds[odds < 0] / (-odds[odds < 0] + 100)
    return result

s5 = fights[usable].head(5).copy()
s5['a_impl']   = american_to_implied(s5['fighter_open'])
s5['b_impl']   = american_to_implied(s5['opponent_open'])
s5['open_sum'] = s5['a_impl'] + s5['b_impl']
print("\n(5) Opening implied prob sums:")
print(s5[['fighter_name','opponent_name','a_impl','b_impl','open_sum']].to_string(index=False))
print(f"All 5 sums > 1? {(s5['open_sum'] > 1).all()}")
