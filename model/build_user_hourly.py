"""Build the hourly pickle from the user's earlier processed (gap-filled) hourly files, exactly as
notebooks/CSH_AQI_on_your_hourly_data.ipynb (cell 3) does. Output: data/processed_user/hourly_user.pkl
usage (project root): python model/build_user_hourly.py"""
import glob, os
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "processed_user"
STATIONS = ["chikkaballapura", "chikkamagaluru", "hebbal", "jayanagar", "madikeri", "mysuru", "ramanagara", "silkboard"]
AVG_COL = {"pm25": "pm25_avg_24h", "pm10": "pm10_avg_24h", "no2": "no2_avg_24h", "so2": "so2_avg_24h", "o3": "o3_avg_8h", "co": "co_avg_8h"}

frames = []
for st in STATIONS:
    hits = sorted(h for ext in ("csv", "xls", "xlsx") for h in glob.glob(str(DATA_DIR / f"*{st}_Final_hourly_AQI.{ext}")))
    d = pd.read_csv(hits[0])
    out = pd.DataFrame({"datetime": pd.to_datetime(d["datetimeLocal"].astype(str).str[:19]), "station": st})
    for c in ["pm25", "pm10", "no2", "so2", "o3", "co", "no", "nox", "temperature", "relativehumidity", "AQI"]:
        out[c] = pd.to_numeric(d[c], errors="coerce")
    for p, col in AVG_COL.items():
        out[p + "_avg"] = pd.to_numeric(d[col], errors="coerce")
        out[p + "_si"] = pd.to_numeric(d[p + "_subindex"], errors="coerce")
    frames.append(out)
H = pd.concat(frames, ignore_index=True).sort_values(["station", "datetime"]).reset_index(drop=True)
H.to_pickle(DATA_DIR / "hourly_user.pkl")
print("wrote", DATA_DIR / "hourly_user.pkl", len(H), "rows;", H.datetime.min(), "->", H.datetime.max())
