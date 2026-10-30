"""Readability redesign (26 Oct 2026): donut charts, "All stations now" card (two versions), summary-first advice with the top 3 actions and bold key
phrases, Gmail-safe HTML e-mail. PRESENTATION ONLY: the wording of every verified statement must be unchanged.

Checks: wording unchanged (emphasis markers stripped == the plain text, for the weekly rules and every advice part), top-3 selection per profile,
weekly donut counts == day counts, station gauges == /api/stations/now, stale handling (live data > 24 h, replay gaps), the toggle and its memory,
colour never alone, WCAG AA contrast, phone width 390 px, no JavaScript errors, e-mail HTML (no <script>/<svg>/<style>/class, inline CSS, < 100 KB,
plain-text part kept). Screenshots in screenshots_preview/redesign/.
Own server on port 8045 (DevTools 9345), temporary users.db, fake e-mail (AQI_EMAIL_FAKE=1); never port 8000; nothing is sent.
usage (project root, aqi env):  python backend\\test_readability.py
"""
import base64
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TMP = Path(tempfile.mkdtemp(prefix="aqi_read_"))
os.environ.update(AQI_EMAIL_FAKE="1", AQI_USERS_DB=str(TMP / "users_inproc.db"), AQI_SECRET_KEY="read-test-" + "r" * 40,
                  AQI_PROFILE_FILE=str(TMP / "profile.json"), AQI_RATE_FILE=str(TMP / "rate.json"))
sys.path.insert(0, str(ROOT / "backend"))
import advice as adv  # noqa: E402
import notify_email as ne  # noqa: E402
import weekly as W  # noqa: E402

OUT = ROOT / "screenshots_preview" / "redesign"
OUT.mkdir(parents=True, exist_ok=True)
failures = []
MARK = re.compile(r"\*\*")


def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  {extra}" if extra else ""))
    if not cond:
        failures.append(name)


# ---- 1. wording unchanged -----------------------------------------------------------------------------------------------------------------
raw = json.loads((ROOT / "backend" / "weekly_advice_rules.json").read_text(encoding="utf-8"))
items = [r for k in ("clean", "short_term", "long_term", "actions") for r in W.RULES[k]]
raw_items = [r for k in ("clean", "short_term", "long_term", "actions") for r in raw[k]]
review = (ROOT / "docs" / "weekly_advice_review.md").read_text(encoding="utf-8")
doc = (ROOT / "docs" / "health_advisory_reference.md").read_text(encoding="utf-8")
check("W1 weekly rules: every text with the **bold** markers removed equals the reviewed wording (docs/weekly_advice_review.md and the reference doc)",
      all(MARK.sub("", r["text"]) == i["text"] and f"| {i['id']} | {i['text']} |" in review and i["text"] in doc for r, i in zip(raw_items, items))
      and sum(r["text"].count("**") for r in raw_items) >= 2 * len(raw_items), f"{len(items)} rules")
check("W2 bold markers are well formed: pairs, never empty, never nested, each rule has at least one",
      all(r["text"].count("**") % 2 == 0 and "****" not in r["text"] and re.search(r"\*\*[^*]+\*\*", r["text"]) for r in raw_items))
bad, n = [], 0
for aqi in (30, 75, 150, 250, 350, 450):
    for g in ([], ["lung"], ["heart"], ["child"], ["older"], ["pregnant"], ["outdoor_worker"], ["athlete"], ["lung", "heart", "older"], ["child", "athlete"]):
        pa = adv.personal_advice(aqi, {"groups": g, "alert_from": 101 if g else 201}, None, aqi, "pm25", aqi,
                                 {"status": "ok", "best": {"label": "1-4 pm"}, "worst": {"label": "7-10 pm"}, "drop": 0.3})
        for p in pa["full"] + pa["short"] + pa["top3"]:
            n += 1
            if MARK.sub("", p["marked"]) != p["text"]:
                bad.append(p["text"][:60])
check("W3 advice parts (6 categories x 10 profiles): 'marked' with the markers removed == the unchanged text, everywhere (full, pop-up, top 3)",
      not bad and n > 500, f"{n} parts, bad={bad[:2]}")
check("W4 the CPCB category statements and the tips are untouched (still word for word; the markers live only in 'marked')",
      adv.IMPACT["Poor"].endswith("with short exposure") and "**" not in "".join(adv.IMPACT.values()) and all("**" not in t[3] for t in adv.TIPS))

# ---- 2. top-3 selection per profile ------------------------------------------------------------------------------------------------------
PAT = {"status": "ok", "best": {"label": "1-4 pm"}, "worst": {"label": "7-10 pm"}, "drop": 0.3}
top = lambda aqi, g: adv.personal_advice(aqi, {"groups": g, "alert_from": 101 if g else 201}, None, aqi, "pm10", 3, PAT)["top3"]   # noqa: E731
t1, t2, t3, t4, t5 = top(250, ["lung"]), top(250, []), top(320, ["lung", "heart", "older"]), top(40, []), top(150, ["outdoor_worker"])
check("T1 lung disease at Poor: [own group line, best time, doctor] with icons [walking, clock, doctor]",
      [p["kind"] for p in t1] == ["group", "best_time", "doctor"] and t1[0]["text"].startswith("Lung disease") and [p["icon"] for p in t1] == ["walking", "clock", "doctor"],
      str([(p["kind"], p["icon"]) for p in t1]))
check("T2 healthy adult at Poor: [what to do, best time, doctor]", [p["kind"] for p in t2] == ["what_to_do", "best_time", "doctor"], str([p["kind"] for p in t2]))
check("T3 lung + heart + older adult at Very Poor: lung and heart share one action -> ONE merged line, then older adult, then the best time",
      [p["kind"] for p in t3] == ["group", "group", "best_time"] and t3[0]["text"].startswith("Lung disease, heart disease: remain indoors")
      and t3[1]["text"].startswith("Older adult: ") and t3[2]["text"] == "Limit outdoor activity at all times", str([p["text"][:40] for p in t3]))
t7 = top(150, ["child", "older"])
full7 = adv.personal_advice(150, {"groups": ["child", "older"], "alert_from": 101}, None, 150, "pm10", 3, PAT)
act = lambda t: t.split(": ", 1)[1]   # noqa: E731
check("T7 identical group actions merged into one line ('Child, older adult: ...'); the action sentence is word for word the single lines' text;"
      " the freed slots go to best time and doctor",
      t7[0]["text"] == "Child, older adult: " + act(full7["groups"][0]["text"]) and act(full7["groups"][0]["text"]) == act(full7["groups"][1]["text"])
      and t7[0]["covers"] == [g["text"] for g in full7["groups"]] and [p["kind"] for p in t7] == ["group", "best_time", "doctor"]
      and MARK.sub("", t7[0]["marked"]) == t7[0]["text"], str([p["text"][:50] for p in t7]))
check("T4 Good air: one item, 'No special precautions ...'", len(t4) == 1 and t4[0]["text"].startswith("No special precautions"), str(t4))
check("T5 outdoor worker at Moderate: own line first, every top item is an unchanged part of the full advice",
      t5[0]["text"].startswith("Outdoor work") and all(any(p["text"] == q["text"] for q in adv.personal_advice(150, {"groups": ["outdoor_worker"], "alert_from": 101},
                                                                                                       None, 150, "pm10", 3, PAT)["full"]) for p in t5))
wk = W.replay_weekly("silkboard", "2026-04-24 02:00:00", ["lung", "child"])
check("T6 weekly top 3 = the profile's own actions first (A2, A3, A7 for lung + child), all of them existing actions of that week",
      wk["top3"] == ["A2", "A3", "A7"] and set(wk["top3"]) <= {i["id"] for i in wk["health"]["actions"]}, str(wk["top3"]))

# ---- 3. e-mail (Gmail-safe HTML + plain text) --------------------------------------------------------------------------------------------
fc = {"aqi": 250, "category": "Poor", "dominant": "pm10", "range_low": 220, "range_high": 290, "category_low": "Poor", "category_high": "Poor",
      "tier": "high", "horizon": 6, "target_end": "2026-04-24 08:00"}
subj, body = ne.compose_alert("replay", "Silk Board, Bengaluru", "likely", fc, {"groups": ["lung"], "alert_from": 101}, "2026-04-24 02:00 (simulated)",
                              now_aqi=249, seq=5, pattern=PAT)
html = body.html
msg = ne.build_message(subj, body, "someone@example.com", "sender@example.com")
parts = {p.get_content_type(): p.get_content() for p in msg.iter_parts()}
check("E1 e-mail HTML: no <script>, <svg>, <style>, class= or external CSS/images; inline styles and table layout only",
      not re.search(r"<script|<svg|<style|class=|<link|<img|https?://[^\s\"]+\.css", html, re.I) and html.count("<table") >= 3 and 'style="' in html)
check("E2 the message has a text/plain part (the unchanged text) and a text/html part; whole message < 100 KB",
      list(parts) == ["text/plain", "text/html"] and parts["text/plain"].strip() == str(body).strip() and len(msg.as_bytes()) < 100_000,
      f"{len(msg.as_bytes())} bytes")
plain_text = lambda h: re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", re.sub(r"</?strong>", "", h)).replace("&amp;", "&").replace("&middot;", "·").replace("&quot;", '"'))   # noqa: E731
pa_mail = adv.personal_advice(250, {"groups": ["lung"], "alert_from": 101}, None, 249, "pm10", 5, PAT)
ht = plain_text(html)
check("E3 header: coloured category badge 'Poor' + forecast AQI 250; 'What to do now' lists the 3 top actions with bold key phrases, then details, sources",
      "Forecast AQI 250" in re.sub(r"\s+", " ", plain_text(html)) and "background:#ef7d0f" in html and "What to do now" in ht and "<strong>" in html
      and ht.index("What to do now") < ht.index("Details") < ht.index("Sources:")
      and all(re.sub(r"\s+", " ", p["text"]) in ht for p in pa_mail["top3"]), subj)
check("E4 every advice line of the text part is also in the HTML, word for word (presentation only)",
      all(re.sub(r"\s+", " ", p["text"]) in ht for p in pa_mail["full"]))
prev = OUT / "email_alert_preview.html"                    # written below from the REAL replay alert (not from the sample above)

# ---- 4. pages (headless Chrome) ----------------------------------------------------------------------------------------------------------
import test_pages_logged_in as P  # noqa: E402
P.PORT, P.DEVTOOLS = 8045, 9345
P.BASE = f"http://127.0.0.1:{P.PORT}"
P.TMP = TMP / "ui"; P.TMP.mkdir()
with sqlite3.connect(ROOT / "data" / "aqi.db") as c:
    newest = c.execute("SELECT MAX(datetime) FROM hourly WHERE pm25 IS NOT NULL OR pm10 IS NOT NULL").fetchone()[0]
os.environ["AQI_LIVE_NOW"] = (datetime.strptime(newest, "%Y-%m-%d %H:%M:%S") + timedelta(hours=41)).strftime("%Y-%m-%d %H:%M")   # live data >= 40 h old
proc = P.start_server()
chrome = subprocess.Popen([P.CHROME, "--headless=new", "--disable-gpu", "--no-sandbox", f"--remote-debugging-port={P.DEVTOOLS}",
                           f"--user-data-dir={P.TMP / 'chrome'}", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
WORD_JS = r"""(() => { const bad = [];
  document.querySelectorAll('#stationsCard .st-name').forEach((el) => {
    if (el.scrollWidth > el.clientWidth + 1) bad.push(el.textContent + ' overflows');
    const tn = el.firstChild, t = tn.textContent; let i = 0;
    t.split(' ').forEach((w) => { const r = document.createRange(); r.setStart(tn, i); r.setEnd(tn, i + w.length); i += w.length + 1;
      const lines = new Set(Array.from(r.getClientRects()).map((x) => Math.round(x.top))); if (lines.size > 1) bad.push(w + ' broken'); });
    const tile = el.closest('.st-ring'); if (tile.scrollWidth > tile.clientWidth + 1) bad.push(el.textContent + ' tile overflow'); });
  return bad; })()"""
CONTRAST_JS = r"""(sel) => {
  const lum = (c) => { const m = c.match(/[\d.]+/g).map(Number); const f = (v) => { v /= 255; return v <= .03928 ? v / 12.92 : Math.pow((v + .055) / 1.055, 2.4); };
    return .2126 * f(m[0]) + .7152 * f(m[1]) + .0722 * f(m[2]); };
  const bgOf = (el) => { for (let e = el; e; e = e.parentElement) { const b = getComputedStyle(e).backgroundColor; const a = b.match(/[\d.]+/g);
    if (a && (a.length < 4 || +a[3] > .5)) return b; } return 'rgb(255,255,255)'; };
  const out = [];
  document.querySelectorAll(sel).forEach((el) => { if (!el.textContent.trim() || !el.getClientRects().length) return;
    const fg = getComputedStyle(el).color, bg = bgOf(el), L1 = lum(fg), L2 = lum(bg), r = (Math.max(L1, L2) + .05) / (Math.min(L1, L2) + .05);
    const size = parseFloat(getComputedStyle(el).fontSize), bold = +getComputedStyle(el).fontWeight >= 700, need = (size >= 24 || (bold && size >= 18.66)) ? 3 : 4.5;
    out.push({ t: el.textContent.trim().slice(0, 30), r: Math.round(r * 100) / 100, need, fg, bg }); });
  return out; }"""
try:
    for _ in range(60):
        try:
            page = next(t for t in json.loads(urllib.request.urlopen(f"http://127.0.0.1:{P.DEVTOOLS}/json", timeout=2).read()) if t["type"] == "page")
            break
        except Exception:
            time.sleep(0.5)
    tab = P.Tab(page["webSocketDebuggerUrl"])
    sess = P.api_session(first=True)
    req = urllib.request.Request(P.BASE + "/api/me", headers={"Cookie": "aqi_session=" + sess})
    me = json.loads(urllib.request.urlopen(req, timeout=30).read())
    acct_profile = {"groups": me["groups"], "alert_from": me["alert_effective"], "email": me["email"]}
    # the REAL replay alert e-mail for Silk Board, simulated hour label 2026-04-24 01:00 (issued 02:00, hour ending), this account's profile
    err, info = ne.replay_compose("silkboard", "2026-04-24 01:00:00", "validation", acct_profile)
    prev.write_text(info["body"].html, encoding="utf-8")

    def size(w, h, mobile=False):
        tab.cmd("Emulation.setDeviceMetricsOverride", width=w, height=h, deviceScaleFactor=2 if mobile else 1, mobile=mobile)

    def shot(name, sel=None, offset=96):
        if sel:
            tab.js(f"document.querySelector({json.dumps(sel)}).scrollIntoView({{block: 'start'}}); window.scrollBy(0, -{offset})")
            tab.pump(0.4)
        data = base64.b64decode(tab.cmd("Page.captureScreenshot", format="png")["data"])
        for attempt in range(5):                  # Windows: an editor previewing the old file can block the write for a moment
            try:
                (OUT / (name + ".tmp")).write_bytes(data)
                os.replace(OUT / (name + ".tmp"), OUT / name)
                break
            except OSError:
                time.sleep(0.5)

    def replay_at(hour, station="silkboard", period="validation", extra="&pauseonalert=0"):
        tab.set_session(sess)
        tab.goto(P.BASE + f"/?station={station}&period={period}{extra}")
        tab.wait("S.hours.length > 0", 25)
        tab.wait("!!document.getElementById('weeklyCard').dataset.clock && !!document.getElementById('stationsCard').dataset.clock", 25)
        tab.pump(1.0)
        for _ in range(4):
            clock = tab.js("(async () => { stop(); clearAlert('x'); S.idx = S.hours.findIndex(h => h >= %s); await show(); return S.hours[S.idx]; })()" % json.dumps(hour))
            tab.wait("document.getElementById('weeklyCard').dataset.clock === %s && document.getElementById('stationsCard').dataset.clock === %s"
                     % (json.dumps(clock), json.dumps(clock)), 15)
            tab.pump(0.8)
            if tab.js("document.getElementById('stationsCard').dataset.clock") == clock:
                break
        tab.js("clearAlert('x')")
        tab.pump(0.2)
        return clock

    def set_view(v):
        tab.js("document.querySelector('#stationsCard .seg button[data-view=%s]').click()" % json.dumps(v))
        tab.pump(0.3)

    TR = "2026-04-24 02:00:00"
    size(1366, 900)
    tab.set_session(sess)
    tab.goto(P.BASE + "/?pauseonalert=0")
    tab.js("try { localStorage.removeItem('aqiStationsView') } catch (e) {}")
    clock = replay_at(TR)
    api = json.loads(urllib.request.urlopen(P.BASE + "/api/stations/now?mode=replay&t=" + urllib.parse.quote(clock), timeout=30).read())
    rings = tab.js("""(() => Array.from(document.querySelectorAll('#stationsCard .st-ring')).map(b => ({ id: b.dataset.station, num: b.querySelector('.st-num').textContent,
        cat: (b.querySelector('.catpill') || {}).textContent, label: b.getAttribute('aria-label'), dash: (b.querySelectorAll('circle')[1] || {getAttribute: () => null}).getAttribute('stroke-dasharray') })))()""")
    pressed = tab.js("(() => Array.from(document.querySelectorAll('#stationsCard .seg button')).map(b => b.dataset.view + ':' + b.getAttribute('aria-pressed')))()")
    check("S1 'All stations now' defaults to (a) 'Each station': 8 ring gauges", len(rings) == 8 and pressed == ["each:true", "bycat:false"], str(pressed))
    want = {s["id"]: s for s in api["stations"]}
    mism = [r["id"] for r in rings if (str(want[r["id"]]["aqi"]) if want[r["id"]]["aqi"] is not None else "–") != r["num"]
            or (want[r["id"]]["category"] or "no data") != r["cat"]
            or (want[r["id"]]["aqi"] is not None and abs(float(r["dash"].split()[0]) - min(want[r["id"]]["aqi"], 500) / 500 * 2 * 3.14159265 * 30) > 0.05)]
    check("S2 every ring = /api/stations/now at the replay clock: AQI number, category label, ring filled to AQI/500; missing station = 'no data'",
          not mism and any(r["cat"] == "no data" for r in rings), str(mism))
    shot("stations_each_replay_desktop.png", "#stationsCard")
    times = tab.js("""(() => ({ banner: document.getElementById('simTime').textContent, stations: document.querySelector('#stationsCard .st-head p').textContent,
        weekly: document.querySelector('#weeklyCard .wk-head p').textContent }))()""")
    end = (datetime.strptime(clock, "%Y-%m-%d %H:%M:%S") + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M")
    check("Y1 replay: banner, 'All stations now' and the weekly card all show the same HOUR-ENDING time (2026-04-24 03:00), never the hour-start label",
          times["banner"].startswith(end) and f"hour ending {end} IST" in times["stations"] and f"{end} IST" in times["weekly"]
          and clock[:16] not in times["stations"] + times["weekly"], str(times))
    wb = tab.js(WORD_JS)
    check("Z1 station tiles (desktop 1366 px): every name fits its tile, no word broken across lines (incl. Chikkamagaluru)", not wb, str(wb))
    set_view("bycat")
    leg = tab.js("(() => Array.from(document.querySelectorAll('#stationsCard .st-legend button')).map(b => b.textContent.trim()))()")
    cnt = {}
    for s in api["stations"]:
        k = s["category"] or "No data"
        cnt[k] = cnt.get(k, 0) + 1
    exp_leg = [f"{k} {cnt[k]}" for k in ["Good", "Satisfactory", "Moderate", "Poor", "Very Poor", "Severe", "No data"] if k in cnt]
    tab.js("document.querySelectorAll('#stationsCard .st-legend button')[0].click()")
    tab.pump(0.2)
    listed = tab.js("document.querySelector('#stationsCard .st-list').textContent")
    centre = tab.js("Array.from(document.querySelectorAll('#stationsCard .donut text')).map(t => t.textContent).join(' ')")
    first_names = [P2 for P2 in [s["id"] for s in api["stations"] if (s["category"] or "No data") == exp_leg[0].rsplit(" ", 1)[0]]]
    check("S3 (b) 'By category': legend counts per CPCB category == /api, centre '8 stations', tapping a category lists its station names",
          leg == exp_leg and centre.startswith("8 stations") and all(n in listed for n in [{"madikeri": "Madikeri", "mysuru": "Mysuru", "silkboard": "Silk Board",
          "hebbal": "Hebbal", "jayanagar": "Jayanagar", "chikkaballapura": "Chikkaballapur", "chikkamagaluru": "Chikkamagaluru", "ramanagara": "Ramanagara"}[i] for i in first_names]),
          f"{leg} / {exp_leg} | {listed}")
    shot("stations_bycat_replay_desktop.png", "#stationsCard")
    tab.goto(P.BASE + "/?pauseonalert=0&station=silkboard")
    tab.wait("!!document.getElementById('stationsCard').dataset.clock", 25)
    tab.pump(0.6)
    remembered = tab.js("(() => [localStorage.getItem('aqiStationsView'), document.querySelector('#stationsCard .seg button[aria-pressed=true]').dataset.view])()")
    check("S4 the choice is remembered (localStorage aqiStationsView) after a reload", remembered == ["bycat", "bycat"], str(remembered))
    set_view("each")
    clock = replay_at(TR)
    tab.js("document.querySelector('#stationsCard .st-ring[data-station=hebbal]').click()")
    tab.wait("S.station === 'hebbal' && S.last && S.last.station === 'hebbal'", 20)
    tab.pump(0.6)
    after = tab.js("[S.station, S.hours[S.idx], document.getElementById('stationTitle').textContent]")
    check("S5 clicking a ring opens that station at the SAME replay hour", after[0] == "hebbal" and after[1] == clock and "Hebbal" in after[2], str(after))

    # weekly donut and dots
    clock = replay_at(TR)
    wkapi = json.loads(urllib.request.urlopen(P.BASE + "/api/weekly?station=silkboard&mode=replay&groups=lung,heart&t=" + urllib.parse.quote(clock), timeout=30).read())
    wk = tab.js("""(() => { const c = document.getElementById('weeklyCard'); return { counts: JSON.parse(c.querySelector('.wk-donut').dataset.counts),
        legend: Array.from(c.querySelectorAll('.wk-donut .dn-legend li')).map(l => l.textContent.trim()), centre: Array.from(c.querySelectorAll('.donut text')).map(t => t.textContent).join(' '),
        dots: Array.from(c.querySelectorAll('.wk-dots .wk-day')).map(d => d.querySelector('.wk-num').textContent),
        segs: c.querySelectorAll('.donut .dn-seg').length, top: Array.from(c.querySelectorAll('ul.top-acts > li')).map(l => l.textContent),
        poll: c.querySelector('details.wk-poll') ? c.querySelector('details.wk-poll').open : null, table: !!c.querySelector('details.wk-poll table.wk-table') }; })()""")
    exp = {}
    for d in wkapi["days"]:
        k = d["category"] if d["aqi"] is not None else "No data"
        exp[k] = exp.get(k, 0) + 1
    check("D1 weekly donut counts == the day counts of /api/weekly (per CPCB category), legend shows them, centre 'N of 7 days Moderate or worse'",
          wk["counts"] == exp and sum(exp.values()) == 7 and wk["centre"].startswith(f"{wkapi['days_moderate_or_worse']} of 7") and wk["segs"] == len(exp)
          and all(any(l.startswith(k) and l.endswith(str(v)) for l in wk["legend"]) for k, v in exp.items()), f"{wk['counts']} vs {exp}")
    check("D2 day strip: 7 dots oldest -> newest with their AQI numbers (same order as the API days)",
          wk["dots"] == [str(d["aqi"]) if d["aqi"] is not None else "–" for d in wkapi["days"]], str(wk["dots"]))
    check("D3 pollutant table kept but collapsed ('Show pollutant details'); top 3 actions shown with their sources",
          wk["poll"] is False and wk["table"] and len(wk["top"]) == 3 and all(re.search(r"\[\d\]", t) for t in wk["top"]), str(wk["top"]))
    shot("weekly_donut_replay_desktop.png", "#weeklyCard")
    # advice card + Health advice tab + pop-up
    adv_card = tab.js("""(() => { const n = document.getElementById('nowAdvice'); return { badge: (n.querySelector('.catpill') || {}).textContent,
        status: (n.querySelector('.adv-status') || {}).textContent, top: n.querySelectorAll('ul.top-acts > li').length, strong: n.querySelectorAll('ul.top-acts strong').length,
        icons: Array.from(n.querySelectorAll('ul.top-acts > li')).map(l => getComputedStyle(l, '::before').maskImage || getComputedStyle(l, '::before').webkitMaskImage),
        more: !!n.querySelector('details.adv-more') }; })()""")
    check("A1 personal advice card: category badge + status line, then 3 actions with icons and bold key phrases, then 'Show all advice'",
          adv_card["badge"] in ("Poor", "Moderate", "Very Poor") and "AQI" in adv_card["status"] and adv_card["top"] == 3 and adv_card["strong"] >= 2
          and all("svg" in (i or "") for i in adv_card["icons"]) and adv_card["more"], str(adv_card))
    shot("advice_card_summary_desktop.png", ".dash")
    tab.js("document.querySelector('[data-tab=advice], #tabAdvice, button[aria-controls=tab-advice]') && document.querySelector('[data-tab=advice], #tabAdvice, button[aria-controls=tab-advice]').click()")
    tab.js("document.querySelectorAll('#adviceBox details.adv-more').forEach(d => d.open = true)")
    tab.pump(0.4)
    secs = tab.js("(() => Array.from(document.querySelectorAll('#adviceBox .asec')).map(s => [s.className, s.querySelector('.sec-h').textContent]))()")
    check("A2 Health advice tab: summary, then amber 'May affect you' and green 'What you can do' sections, each colour with its text heading",
          [x[1] for x in secs] == ["May affect you", "What you can do"] and "sec-affect" in secs[0][0] and "sec-do" in secs[1][0], str(secs))
    shot("advice_tab_expanded_desktop.png", "#adviceBox", 140)
    # pop-up (pause on alert: modal)
    replay_at("2026-04-24 01:00:00", extra="&pauseonalert=1")
    tab.js("(async () => { stop(); S.lastIssued = {}; clearAlert('profile'); S.idx = S.hours.indexOf('2026-04-24 01:00:00'); await show(); })()")
    tab.wait("!!document.querySelector('#toasts .toast')", 10)
    tab.pump(0.5)
    pop = tab.js("""(() => { const t = document.querySelector('#toasts .toast'); return { badge: (t.querySelector('.toast-badge .catpill') || {}).textContent,
        top: t.querySelectorAll('ul.top-acts > li').length, more: !!t.querySelector('details.toast-more'),
        all: t.querySelectorAll('.toast-lines li').length }; })()""")
    check("A3 pop-up: category badge + forecast AQI, the top 3 actions with icons, the rest behind 'Show all advice'",
          bool(pop["badge"]) and pop["top"] == 3 and pop["more"] and pop["all"] >= 4, str(pop))
    shot("popup_desktop.png")
    toast = tab.js("(() => Object.assign({}, document.querySelector('#toasts .toast').dataset))()")
    card = tab.js("(h) => Object.assign({}, Array.from(document.querySelectorAll('#strip .fc-card')).find(c => c.dataset.horizon === h).dataset)"
                  .replace("(h) =>", "((h) =>") + ")(%s)" % json.dumps(toast["horizon"]))
    txt = str(info["body"])
    m1 = re.search(r"Forecast AQI: (\d+) \(([A-Za-z ]+?)(?:, mainly (\S+))?\)", txt)
    m2 = re.search(r"Likely range: (\d+) to (\d+)", txt)
    m3 = re.search(r"For the hour ending: (\S+ \S+) \(\+(\d+) h", txt)
    mail = {"aqi": m1.group(1), "category": m1.group(2), "dominant": m1.group(3) or "", "range": m2.group(1) + "-" + m2.group(2),
            "target": m3.group(1), "horizon": m3.group(2)}
    pop = {k: toast[k] for k in mail}
    pop["dominant"] = adv.pname(pop["dominant"]) if pop["dominant"] else ""
    crd = {k: card[k] for k in mail}
    crd["dominant"] = adv.pname(crd["dominant"]) if crd["dominant"] else ""
    hh = info["body"].html
    html_ok = (f'Forecast AQI <span style="font-size:28px;font-weight:700;">{mail["aqi"]}</span>' in hh and f"Likely range: {m2.group(1)} to {m2.group(2)}" in hh
               and f'>{mail["category"]}</td>' in hh and f'hour ending {mail["target"]} (+{mail["horizon"]} h)' in hh
               and (not mail["dominant"] or f'mainly {mail["dominant"]}' in hh))
    check("X1 one alert (Silk Board, issued 24 Apr 02:00): e-mail (text + HTML), pop-up and forecast card show the SAME AQI, likely range, category, main "
          "pollutant and target hour", mail == pop == crd and html_ok, f"mail={mail} pop={pop} card={crd} html={html_ok}")
    tab.js("clearAlert('x')")

    # contrast (WCAG AA) on all new text elements, desktop
    tab.js("document.querySelectorAll('details').forEach(d => d.open = true)")
    tab.pump(0.3)
    SEL = ("#stationsCard .st-name, #stationsCard .catpill, #stationsCard .st-age, #stationsCard p, #weeklyCard .catpill, #weeklyCard .adv-status, #weeklyCard .adv-h, "
           "#weeklyCard .dn-legend li, #weeklyCard .wk-cat, #weeklyCard .wk-lab, #weeklyCard .asec h3, #weeklyCard .asec li, #weeklyCard .src, #weeklyCard ul.top-acts > li, "
           "#nowAdvice .catpill, #nowAdvice .adv-h, #nowAdvice li, #nowAdvice .src, #adviceBox .sec-h, #adviceBox li, #adviceBox .src")
    con = tab.js("(" + CONTRAST_JS + ")(%s)" % json.dumps(SEL))
    low = [c for c in con if c["r"] < c["need"]]
    check("C1 WCAG AA contrast for every new text element (desktop, light theme): >= 4.5:1 (>= 3:1 for large text)", con and not low,
          f"{len(con)} elements, lowest {min(c['r'] for c in con) if con else '-'}; failing {low[:3]}")
    colour_only = tab.js("""(() => { const bad = [];
        document.querySelectorAll('#stationsCard .st-ring').forEach(b => { if (!b.querySelector('.catpill') || !b.querySelector('.catpill').textContent.trim()) bad.push('ring ' + b.dataset.station); });
        document.querySelectorAll('.dn-legend li').forEach(l => { if (!l.textContent.trim()) bad.push('legend'); });
        document.querySelectorAll('.asec').forEach(s => { if (!s.querySelector('h3, .sec-h, summary')) bad.push('section ' + s.className); });
        document.querySelectorAll('.wk-dots .wk-day').forEach(d => { if (!d.querySelector('.wk-cat').textContent.trim()) bad.push('dot'); });
        return bad; })()""")
    check("C2 colour is never the only cue: every ring has its category text, every donut legend entry and day dot a label, every coloured section a heading",
          not colour_only, str(colour_only))
    check("C3 no JavaScript errors on the replay page", not tab.errors, str(tab.errors))

    # live: stale handling
    tab.goto(P.BASE + "/live.html")
    tab.wait("!!document.getElementById('stationsCard').dataset.clock && !!document.getElementById('weeklyCard').dataset.clock", 30)
    tab.pump(1.0)
    lapi = json.loads(urllib.request.urlopen(P.BASE + "/api/stations/now?mode=live", timeout=30).read())
    lv = tab.js("""(() => { const c = document.getElementById('stationsCard'); return { banner: (c.querySelector('.wk-stale') || {}).textContent || '',
        ages: Array.from(c.querySelectorAll('.st-ring')).map(b => [b.dataset.station, (b.querySelector('.st-age') || {}).textContent || '', b.classList.contains('st-old')]),
        wtitle: document.querySelector('#weeklyCard h2').textContent }; })()""")
    stale_ids = {s["id"] for s in lapi["stations"] if s["status"] == "stale"}
    check("L1 live, data >= 40 h old: red 'DATA IS OLD' line, every stale ring marked 'STALE · N h old' and greyed; stations without data 'no data'",
          lv["banner"].startswith("DATA IS OLD") and stale_ids and all((i in stale_ids) == (old and a.startswith("STALE")) for i, a, old in lv["ages"]),
          f"{lv['banner'][:80]} | {lv['ages'][:3]}")
    check("L2 live weekly card is the past-tense 'Last available week' version (stale data)", lv["wtitle"].startswith("Last available week"), lv["wtitle"])
    lt = tab.js("[document.getElementById('bannerText').textContent, document.querySelector('#weeklyCard .wk-head p').textContent]")
    mb = re.search(r"hour ending (\d{4}-\d\d-\d\d \d\d:\d\d)", lt[0])
    check("Y2 live: the weekly card names the newest data by its HOUR-ENDING time, the same as the banner", bool(mb) and f"hour ending {mb.group(1)} IST" in lt[1], str(lt))
    shot("stations_each_live_stale_desktop.png", "#stationsCard")
    shot("weekly_donut_live_stale_desktop.png", "#weeklyCard")
    check("L3 no JavaScript errors on the live page", not tab.errors, str(tab.errors))

    # phone 390 px
    size(390, 844, True)
    clock = replay_at(TR)
    wide = tab.js("[document.documentElement.scrollWidth, document.documentElement.clientWidth]")
    check("M1 phone 390 px (replay): no horizontal scrolling", wide[0] <= wide[1], str(wide))
    con_m = tab.js("(" + CONTRAST_JS + ")(%s)" % json.dumps("#stationsCard .st-name, #stationsCard .catpill, #weeklyCard .dn-legend li, #nowAdvice li"))
    check("M2 phone: the same contrast rule holds", con_m and not [c for c in con_m if c["r"] < c["need"]])
    set_view("each")
    shot("stations_each_replay_phone.png", "#stationsCard", 70)
    wb = tab.js(WORD_JS)
    check("Z2 station tiles (phone 390 px): every name fits, no word broken across lines", not wb, str(wb))
    set_view("bycat")
    shot("stations_bycat_replay_phone.png", "#stationsCard", 70)
    set_view("each")
    shot("weekly_donut_replay_phone.png", "#weeklyCard", 70)
    shot("advice_card_summary_phone.png", ".foryou", 70)
    replay_at("2026-04-24 01:00:00", extra="&pauseonalert=1")
    tab.js("(async () => { stop(); S.lastIssued = {}; clearAlert('profile'); S.idx = S.hours.indexOf('2026-04-24 01:00:00'); await show(); })()")
    tab.wait("!!document.querySelector('#toasts .toast')", 10)
    tab.pump(0.5)
    shot("popup_phone.png")
    tab.js("clearAlert('x')")
    tab.goto(P.BASE + "/live.html")
    tab.wait("!!document.getElementById('stationsCard').dataset.clock", 30)
    tab.pump(0.8)
    wide = tab.js("[document.documentElement.scrollWidth, document.documentElement.clientWidth]")
    check("M3 phone 390 px (live): no horizontal scrolling", wide[0] <= wide[1], str(wide))
    shot("stations_each_live_phone.png", "#stationsCard", 70)
    # e-mail preview (the saved .html), desktop and phone
    size(1280, 1000)
    tab.goto(prev.as_uri())
    tab.pump(0.8)
    shot("email_preview_desktop.png")
    size(390, 844, True)
    tab.goto(prev.as_uri())
    tab.pump(0.8)
    ew = tab.js("[document.documentElement.scrollWidth, document.documentElement.clientWidth]")
    check("M4 e-mail preview at 390 px: fits the width (no horizontal scrolling)", ew[0] <= ew[1], str(ew))
    shot("email_preview_phone.png")
    check("M5 no JavaScript errors overall", not tab.errors, str(tab.errors))

    # ---- 5. every page in LIGHT and DARK mode (prefers-color-scheme), desktop and phone: WCAG AA for every visible text -----------------
    from contrast_scan import ALLTEXT_JS
    DARK = OUT / "dark"; DARK.mkdir(exist_ok=True)

    def scheme(mode):
        tab.cmd("Emulation.setEmulatedMedia", features=[{"name": "prefers-color-scheme", "value": mode}])

    def scan(steps=("",)):
        res = {"checked": 0, "fails": []}
        for step in steps:
            if step:
                tab.js(step); tab.pump(0.4)
            r = tab.js(ALLTEXT_JS)
            res["checked"] += r["checked"]
            res["fails"] += [f for f in r["fails"] if f not in res["fails"]]
        return res

    REPLAY_STEPS = ("", "document.querySelectorAll('details').forEach(d => d.open = true)", "document.getElementById('tabbtn-advice').click()",
                    "document.getElementById('tabbtn-pollutants').click()", "document.querySelector('#stationsCard .seg button[data-view=bycat]').click()",
                    "document.querySelector('#stationsCard .seg button[data-view=each]').click()")
    for mode in ("light", "dark"):
        scheme(mode)
        for w, h_, mob in ((1366, 900, False), (390, 844, True)):
            size(w, h_, mob)
            res = {}
            replay_at(TR)
            res["replay"] = scan(REPLAY_STEPS)
            replay_at("2026-04-24 01:00:00", extra="&pauseonalert=1")                  # the alert pop-up (modal) on screen
            tab.js("(async () => { stop(); S.lastIssued = {}; clearAlert('profile'); S.idx = S.hours.indexOf('2026-04-24 01:00:00'); await show(); })()")
            tab.wait("!!document.querySelector('#toasts .toast')", 10)
            tab.pump(0.5)
            res["pop-up"] = scan(("", "document.querySelectorAll('#toasts details').forEach(d => d.open = true)"))
            if mob and mode == "dark":
                shot("dark/popup_phone.png")
            tab.js("clearAlert('x')")
            tab.js("showInstallHelp()"); tab.pump(0.3)
            res["install help"] = scan()
            tab.js("document.getElementById('installHelp').hidden = true")
            tab.goto(P.BASE + "/live.html")
            tab.wait("!!document.getElementById('stationsCard').dataset.clock && !!document.getElementById('weeklyCard').dataset.clock", 30)
            tab.pump(1.0)
            res["live"] = scan(REPLAY_STEPS[:4])
            tab.goto(P.BASE + "/profile.html")
            tab.wait("!!document.getElementById('waNumber') && !!document.getElementById('weeklyCard').dataset.clock", 30)
            tab.pump(1.0)
            res["profile"] = scan(("", "document.querySelectorAll('details').forEach(d => d.open = true)"))
            wide = tab.js("[document.documentElement.scrollWidth, document.documentElement.clientWidth]")
            bad = {k: v["fails"][:3] for k, v in res.items() if v["fails"]}
            n = sum(v["checked"] for v in res.values())
            check(f"K {mode} {w} px: WCAG AA for every visible text on replay (all tabs, both station views, details), the alert pop-up, install help, "
                  f"live and profile", not bad and n > 2000, f"{n} texts checked; failing: {json.dumps(bad)[:400]}")
            check(f"K {mode} {w} px: no horizontal scrolling (profile)", wide[0] <= wide[1], str(wide))
            if mob and mode == "dark":
                replay_at(TR)
                shot("dark/stations_each_phone.png", "#stationsCard", 70)
                set_view("bycat"); tab.js("document.querySelectorAll('#stationsCard .st-legend button')[2].click()"); tab.pump(0.3)
                shot("dark/stations_bycat_phone.png", "#stationsCard", 70)
                set_view("each")
                shot("dark/weekly_phone.png", "#weeklyCard", 70)
                shot("dark/advice_card_phone.png", ".foryou", 70)
                tab.goto(P.BASE + "/profile.html"); tab.wait("!!document.getElementById('pushLive')", 20); tab.pump(0.8)
                tab.js("document.getElementById('pushLive').scrollIntoView({block: 'center'})"); tab.pump(0.3)
                shot("dark/profile_alerts_phone.png")
                tab.js("window.scrollTo(0, 0)"); tab.pump(0.3)
                shot("dark/header_install_phone.png")
        # signed-out pages
        tab.cmd("Network.clearBrowserCookies")
        res = {}
        for pg in ("/login.html", "/signup.html", "/forgot.html"):
            tab.goto(P.BASE + pg); tab.pump(1.0)
            res[pg] = scan()
        bad = {k: v["fails"][:3] for k, v in res.items() if v["fails"]}
        check(f"K {mode}: WCAG AA on the signed-out pages (login, sign-up, forgot password)", not bad, json.dumps(bad)[:300])
        tab.set_session(sess)
    scheme("light")
    check("K no JavaScript errors in light or dark mode", not tab.errors, str(tab.errors))
    tab.ws.close()
finally:
    chrome.kill(); proc.kill()

print()
print("ALL PASSED" if not failures else f"{len(failures)} FAILED: {failures}")
sys.exit(1 if failures else 0)
