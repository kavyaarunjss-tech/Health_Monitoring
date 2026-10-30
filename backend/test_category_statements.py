"""The six CPCB category health statements must match CPCB report [1] Table 3.12 "Health Statements for AQI Categories" (printed p. 36) WORD FOR WORD,
everywhere the site shows them: advice card (/api/advice, /api/replay/state), the "full" advice of pop-ups / Health advice tab, e-mails, the reference document.
[1] is cited first; [2] (Arthapedia) only where its wording is identical.

Table 3.12 below was transcribed from the official PDF https://airquality.cpcb.gov.in/ccr_docs/FINAL-REPORT_AQI_.pdf (page image and text layer, 26 Oct 2026).
In-process app (fastapi TestClient: no network port, never port 8000), temporary users.db, fake e-mail; nothing is sent.
usage (project root, aqi env):  python backend\\test_category_statements.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TMP = Path(tempfile.mkdtemp(prefix="aqi_cat_"))
os.environ.update(AQI_EMAIL_FAKE="1", AQI_USERS_DB=str(TMP / "users.db"), AQI_SECRET_KEY="cat-test-" + "c" * 40,
                  AQI_PROFILE_FILE=str(TMP / "profile.json"), AQI_RATE_FILE=str(TMP / "rate.json"))
sys.path.insert(0, str(ROOT / "backend"))
from fastapi.testclient import TestClient  # noqa: E402
import advice as adv  # noqa: E402
import app as appmod  # noqa: E402
import notify_email as ne  # noqa: E402
import weekly as W  # noqa: E402

TABLE_3_12 = {   # CPCB [1] Table 3.12, p. 36, exactly as printed (no full stop at the end of a row)
    "Good": "Minimal Impact",
    "Satisfactory": "May cause minor breathing discomfort to sensitive people",
    "Moderate": "May cause breathing discomfort to the people with lung disease such as asthma and discomfort to people with heart disease, children and older adults",
    "Poor": "May cause breathing discomfort to people on prolonged exposure and discomfort to people with heart disease with short exposure",
    "Very Poor": "May cause respiratory illness to the people on prolonged exposure. Effect may be more pronounced in people with lung and heart diseases",
    "Severe": "May cause respiratory effects even on healthy people and serious health impacts on people with lung/heart diseases. The health impacts may be "
              "experienced even during light physical activity",
}
ARTHAPEDIA = {   # [2], page HTML 26 Oct 2026 (full stops removed): cited only where identical to [1]
    "Good": "Minimal Impact",
    "Satisfactory": "May cause minor breathing discomfort to sensitive people",
    "Moderate": "May cause breathing discomfort to people with lung disease such as asthma, and discomfort to people with heart disease, children and older adults",
    "Poor": "May cause breathing discomfort to people on prolonged exposure, and discomfort to people with heart disease",
    "Very Poor": "May cause respiratory illness to the people on prolonged exposure. Effect may be more pronounced in people with lung and heart diseases",
    "Severe": "May cause respiratory impact even on healthy people, and serious health impacts on people with lung/heart disease. The health impacts may be "
              "experienced even during light physical activity",
}
AQI = {"Good": 30, "Satisfactory": 75, "Moderate": 150, "Poor": 250, "Very Poor": 350, "Severe": 450}
failures = []


def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  {extra}" if extra else ""))
    if not cond:
        failures.append(name)


diff = {c: adv.IMPACT.get(c) for c in TABLE_3_12 if adv.IMPACT.get(c) != TABLE_3_12[c]}
check("T1 advice.IMPACT: all six category statements equal CPCB Table 3.12 (p. 36) word for word", not diff and set(adv.IMPACT) == set(TABLE_3_12), str(diff))
want_src = {c: "[1][2]" if ARTHAPEDIA[c] == TABLE_3_12[c] else "[1]" for c in TABLE_3_12}
check("T2 sources: [1] first on every category; [2] only where Arthapedia is identical (Good, Satisfactory, Very Poor)",
      adv.IMPACT_SRC == want_src and want_src["Poor"] == "[1]" and want_src["Very Poor"] == "[1][2]", str(adv.IMPACT_SRC))

bad = []
for cat, aqi in AQI.items():
    a = adv.advice(aqi, {"groups": ["lung"], "alert_from": 101})
    if a["category"] != cat or a["impact"] != TABLE_3_12[cat] or a["impact_source"] != want_src[cat]:
        bad.append(("advice", cat, a["impact"], a["impact_source"]))
    pa = adv.personal_advice(aqi, {"groups": ["lung"], "alert_from": 101}, None, aqi, "pm25", 0)
    if pa["headline"]["text"] != f"{cat} (AQI {aqi}): {TABLE_3_12[cat]}" or pa["headline"]["source"] != want_src[cat] or pa["headline"] not in pa["full"]:
        bad.append(("headline", cat, pa["headline"]))
check("T3 advice card and the full advice (Health advice tab / pop-up details): each category's statement exactly, with its sources", not bad, str(bad[:2]))

c = TestClient(appmod.app)
api_bad = []
for cat, aqi in AQI.items():
    r = c.post("/api/advice", params={"aqi": aqi}, json={"groups": [], "alert_from": 201}).json()
    if r["impact"] != TABLE_3_12[cat] or r["impact_source"] != want_src[cat]:
        api_bad.append((cat, r.get("impact")))
st = c.get("/api/replay/state", params={"period": "validation", "station": "silkboard", "t": "2026-04-24 02:00:00", "groups": "lung", "alert_from": 101})
sj = st.json() if st.status_code == 200 else {}
blob = json.dumps(sj, ensure_ascii=False)
replay_ok = st.status_code == 200 and any(TABLE_3_12[k] in blob for k in TABLE_3_12)
check("T4 served: POST /api/advice for all six categories, and /api/replay/state (Silk Board 24 Apr 02:00) carry the exact Table 3.12 sentence",
      not api_bad and replay_ok, f"{api_bad[:2]} replay={st.status_code}")

fc = {"aqi": 250, "category": "Poor", "dominant": "pm10", "range_low": 220, "range_high": 290, "category_low": "Poor", "category_high": "Poor",
      "tier": "high", "horizon": 6, "target_end": "2026-04-24 08:00"}
_, body = ne.compose_alert("replay", "Silk Board", "likely", fc, {"groups": ["lung"], "alert_from": 101}, "2026-04-24 02:00", now_aqi=250)
check("T5 e-mail body: the Poor statement word for word ('... heart disease with short exposure') with [1], and no old [2] wording",
      TABLE_3_12["Poor"] in body and TABLE_3_12["Poor"] + " [1]" in body and ARTHAPEDIA["Poor"] not in body, body[:300])

doc = (ROOT / "docs" / "health_advisory_reference.md").read_text(encoding="utf-8")
rows = [f"| {TABLE_3_12[c_]} | {want_src[c_]} |" for c_ in TABLE_3_12]
old_in_doc = [c_ for c_ in ("Moderate", "Poor", "Severe") if f"| {ARTHAPEDIA[c_]} |" in doc]
check("T6 reference document section 1: every row has the exact Table 3.12 sentence and its sources; the old [2] wording is not used as the CPCB column",
      all(r in doc for r in rows) and not old_in_doc and 'Table 3.12 "Health Statements for AQI' in doc, str(old_in_doc))

quotes = []
for k in ("clean", "short_term", "long_term", "actions"):
    for r in W.RULES[k]:
        b = r.get("basis", "")
        if b.startswith("[1][2] ") or "; [1][2] " in b or b.startswith("[1] "):
            for q in b.split("'")[1::2]:
                if b.startswith("[1]") or "[1][2]" in b:
                    quotes.append((r["id"], q))
cpcb_quotes = [(i, q) for i, q in quotes if any(q.lower() in TABLE_3_12[c_].lower() for c_ in TABLE_3_12)]
s2 = next(r for r in W.RULES["short_term"] if r["id"] == "S2")["basis"]
check("T7 weekly card: the S2 source note quotes [1] exactly ('breathing discomfort to the people with lung disease such as asthma'), and the [1][2] quotes "
      "of S3 / S8 are in Table 3.12", "[1] Moderate 'breathing discomfort to the people with lung disease such as asthma'" in s2
      and any(i == "S3" for i, _ in cpcb_quotes) and any(i == "S8" for i, _ in cpcb_quotes), str(quotes[:4]))

print()
print("ALL PASSED" if not failures else f"{len(failures)} FAILED: {failures}")
sys.exit(1 if failures else 0)
