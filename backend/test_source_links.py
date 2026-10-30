"""Source links: the old link of source [1] (app.cpcbccr.com, which on 26 Oct 2026 served an HTML page with third-party ads instead of the CPCB report)
must not appear in anything the website serves or in any source list; [1] must point to the official CPCB copy.

Runs the FastAPI app IN-PROCESS (fastapi TestClient: no network port, never port 8000), temporary users.db, fake e-mail; nothing is sent.
usage (project root, aqi env):  python backend\\test_source_links.py
"""
import json
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TMP = Path(tempfile.mkdtemp(prefix="aqi_links_"))
os.environ.update(AQI_EMAIL_FAKE="1", AQI_USERS_DB=str(TMP / "users.db"), AQI_SECRET_KEY="links-test-" + "k" * 40,
                  AQI_PROFILE_FILE=str(TMP / "profile.json"), AQI_RATE_FILE=str(TMP / "rate.json"))
sys.path.insert(0, str(ROOT / "backend"))
from fastapi.testclient import TestClient  # noqa: E402
import advice as adv  # noqa: E402
import app as appmod  # noqa: E402
import weekly as W  # noqa: E402

OLD = "app.cpcbccr.com"
OFFICIAL = "https://airquality.cpcb.gov.in/ccr_docs/FINAL-REPORT_AQI_.pdf"
failures = []


def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  {extra}" if extra else ""))
    if not cond:
        failures.append(name)


# 1. every file the website can serve (frontend/), read from disk
hits = [str(p.relative_to(ROOT)) for p in (ROOT / "frontend").rglob("*") if p.is_file() and p.suffix in (".html", ".js", ".css", ".json", ".txt", ".md")
        and OLD in p.read_text(encoding="utf-8", errors="replace")]
check("S1 no file in frontend/ contains the old [1] link 'app.cpcbccr.com'", not hits, str(hits))

# 2. the same pages as the running app serves them (guest cookie passes the login gate)
c = TestClient(appmod.app)
c.cookies.set("aqi_guest", "1")
pages = sorted({p.name for p in (ROOT / "frontend").glob("*.html") if not p.name.startswith("_")} | {"ui.js", "app.js", "live.js", "account.js", "style.css"})
served, bad = 0, []
for name in pages:
    r = c.get("/" + name)
    if r.status_code == 200:
        served += 1
        if OLD in r.text:
            bad.append(name)
r = c.get("/")
check("S2 served pages and scripts (/, every .html, ui.js, app.js, live.js, account.js, style.css) do not contain the old link",
      r.status_code == 200 and OLD not in r.text and served >= 8 and not bad, f"served={served} bad={bad}")

# 3. the source lists the site sends
meta = c.get("/api/meta").json()
wk_replay = c.get("/api/weekly", params={"station": "silkboard", "mode": "replay", "t": "2026-04-24 02:00:00", "groups": "lung"}).json()
wk_live = c.get("/api/weekly", params={"station": "silkboard", "mode": "live"})
blobs = {"/api/meta": json.dumps(meta), "/api/weekly replay": json.dumps(wk_replay),
         "/api/weekly live": wk_live.text if wk_live.status_code == 200 else "", "advice.REFERENCES (e-mail 'Sources' line)": json.dumps(adv.REFERENCES),
         "weekly_advice_rules.json": (ROOT / "backend" / "weekly_advice_rules.json").read_text(encoding="utf-8")}
bad = [k for k, v in blobs.items() if OLD in v]
check("S3 no source list contains the old link: /api/meta, /api/weekly (replay and live), the e-mail sources, the weekly rule table", not bad, str(bad))
check("S4 source [1] links to the official CPCB copy on the weekly card (rule table and /api/weekly)",
      W.RULES["urls"]["1"] == OFFICIAL and wk_replay["references"]["1"]["url"] == OFFICIAL, W.RULES["urls"]["1"])

# 4. documents: every reference list points [1] to the official copy; the old domain may appear only in the notes that say it is not used
docs = {p: (ROOT / p).read_text(encoding="utf-8") for p in ("docs/health_advisory_reference.md", "docs/weekly_advice_review.md", "README.md", "CLAUDE.md")
        if (ROOT / p).exists()}
ref1 = [l for p in ("docs/health_advisory_reference.md", "docs/weekly_advice_review.md") for l in docs[p].split("\n")
        if re.match(r"1\. Central Pollution Control Board", l)]
links = [l for l in (ln for t in docs.values() for ln in t.split("\n")) if re.search(r"https?://" + re.escape(OLD), l)]
check("S5 both reference lists give [1] the official link; no document contains the old link as a URL (only as a 'not used' note)",
      len(ref1) == 2 and all(OFFICIAL in l for l in ref1) and not links, str(links[:2]))

print()
print("ALL PASSED" if not failures else f"{len(failures)} FAILED: {failures}")
sys.exit(1 if failures else 0)
