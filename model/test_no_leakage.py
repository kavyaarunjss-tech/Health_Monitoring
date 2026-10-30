"""Leakage test: features of a row at time t must not change when all data after t is removed.
usage: python test_no_leakage.py <clean_hourly.csv> [h1,h2,...]
(The targets y / UNK_* / KNOWN_* legitimately look ahead and are not tested.)"""
import sys
import numpy as np, pandas as pd
from aq_model import build_dataset, feature_columns

H = pd.read_csv(sys.argv[1], parse_dates=["datetime"])
hs = [int(x) for x in sys.argv[2].split(",")] if len(sys.argv) > 2 else [1, 6, 12, 24, 36, 48, 72]
T = pd.Timestamp("2026-03-01 00:00")
bad_any = False
for h in hs:
    full = build_dataset(H, h)
    cut = build_dataset(H[H["datetime"] <= T], h)
    cols = [c for c in feature_columns(full) if c != "station_code"]
    A = full[full["datetime"] <= T].sort_values(["station", "datetime"]).reset_index(drop=True)
    B = cut[cut["datetime"] <= T].sort_values(["station", "datetime"]).reset_index(drop=True)
    assert len(A) == len(B), "row mismatch"
    bad = []
    for c in cols:
        a, b = A[c].to_numpy(float), B[c].to_numpy(float)
        if not np.allclose(a, b, equal_nan=True, atol=1e-6):
            bad.append(c)
    print(f"h={h:3d}: {len(cols)} features tested, LEAKING: {bad if bad else 'none'}")
    bad_any |= bool(bad)
sys.exit(1 if bad_any else 0)
