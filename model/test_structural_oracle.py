"""Oracle test: give the structural reconstruction the TRUE future window means (UNK_*). It must return the
true AQI(t+h) wherever the true AQI is valid. Tests K>0 (h<24) and K<=0 (h>=24; h>=8 for O3/CO).
usage: python test_structural_oracle.py <clean_hourly.csv> [h1,h2,...]"""
import sys
import numpy as np, pandas as pd
from aq_model import build_dataset, structural_aqi, POLLUTANTS

H = pd.read_csv(sys.argv[1], parse_dates=["datetime"])
for h in [int(x) for x in sys.argv[2].split(",")]:
    D = build_dataset(H, h)
    unk = {p: D[f"UNK_{p}"].to_numpy(float) for p in POLLUTANTS}
    a, _, _ = structural_aqi(D, unk, h)
    y = D["y"].to_numpy(float)
    ok = np.isfinite(y) & np.isfinite(a)
    err = np.abs(a[ok] - y[ok])
    print(f"h={h:3d}: rows with true AQI {int(np.isfinite(y).sum())}, reconstructed {int(ok.sum())}, "
          f"MAE {err.mean():.3f}, max {err.max():.1f}, share |err|<=1: {(err <= 1).mean():.3f}")
