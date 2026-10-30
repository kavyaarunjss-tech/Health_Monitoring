"""Health advice engine. Every message below is quoted/derived from docs/health_advisory_reference.md.
Source numbers: [1] CPCB NAQI 2014, [2] Arthapedia NAQI, [3] NCDC ASHA handbook 2024, [4] NCDC Health Adaptation Plan 2021,
[5] WHO 2024 personal interventions Q&A. Do not add claims that are not in that document."""

import math
from datetime import datetime

CATEGORIES = [(50, "Good"), (100, "Satisfactory"), (200, "Moderate"), (300, "Poor"), (400, "Very Poor"), (10**9, "Severe")]
ORDER = [c for _, c in CATEGORIES]

# Section 3: default thresholds (users may lower, never raise)
DEFAULT_ALERT = {"vulnerable": 101, "healthy": 201}
EVERYONE_ALERT = 301
DEFAULT_ADVISORY = {"vulnerable": 51, "healthy": 101}

# Section 4 [3]
MESSAGES = {
    "Good": ("No special precautions", "No special precautions"),
    "Satisfactory": ("No need for special precautions",
                     "Use face masks/cloth/scarves to cover the nose while going out; avoid physical exertion for long periods"),
    "Moderate": ("Use mask or cloth to cover nose; avoid physical exertion for long periods",
                 "Use face masks/cloth/scarves to cover the nose while going out; avoid physical exertion for long periods; "
                 "take frequent water breaks between work"),
    "Poor": ("Avoid outdoor physical exertion, if possible; take frequent water breaks between work; use mask/cloth to cover nose while going out",
             "Use face masks/scarves to cover the nose while going out; avoid heavy exertion when outside and take lots of water breaks; "
             "in a closed space keep external doors and windows closed but ensure sufficient ventilation"),
    "Very Poor": ("Avoid outdoor physical activities; avoid additional pollution sources (burning, candles, smoking indoors); "
                  "use a close-fitted N95 or N99 mask while going out",
                  "Remain indoors as much as possible and keep activity levels low; use a close-fitted N95 or N99 mask while going out; "
                  "take a healthy diet and lots of water; avoid indoor pollution sources"),
    "Severe": ("Avoid outdoor physical activities; use a close-fitted N95 or N99 mask while going out; avoid indoor pollution sources; "
               "drink lots of water",
               "Remain indoors and keep activity levels low; avoid indoor pollution sources; always use a close-fitted N95 or N99 mask "
               "while stepping outside; step out only if urgent"),
}
SOURCE_OF_MESSAGES = "[3]"

# Category health statements: WORD FOR WORD from CPCB report [1] Table 3.12 "Health Statements for AQI Categories" (printed p. 36; official PDF
# https://airquality.cpcb.gov.in/ccr_docs/FINAL-REPORT_AQI_.pdf, checked 26 Oct 2026). [2] (Arthapedia) is cited only where its wording is identical.
IMPACT = {
    "Good": "Minimal Impact",
    "Satisfactory": "May cause minor breathing discomfort to sensitive people",
    "Moderate": "May cause breathing discomfort to the people with lung disease such as asthma and discomfort to people with heart "
                "disease, children and older adults",
    "Poor": "May cause breathing discomfort to people on prolonged exposure and discomfort to people with heart disease with short exposure",
    "Very Poor": "May cause respiratory illness to the people on prolonged exposure. Effect may be more pronounced in people "
                 "with lung and heart diseases",
    "Severe": "May cause respiratory effects even on healthy people and serious health impacts on people with lung/heart diseases. "
              "The health impacts may be experienced even during light physical activity",
}
IMPACT_SRC = {"Good": "[1][2]", "Satisfactory": "[1][2]", "Moderate": "[1]", "Poor": "[1]", "Very Poor": "[1][2]", "Severe": "[1]"}

WHO_MASK = ("WHO does not recommend respirators for the general public (no evidence of effectiveness in the general population; "
            "no one respirator can be guaranteed to fit all users); there are no commercial respirators designed for children (based on information "
            "available as of February 2019); "
            "people with lung or heart disease need special caution.")

DISCLAIMER = ("Health information disclaimer. AQI forecasts on this site are produced by a statistical model and can be wrong. "
              "The health messages are general guidance based on the Central Pollution Control Board's National Air Quality Index "
              "and the Ministry of Health and Family Welfare's air-pollution advisories, with cautions from the World Health "
              "Organization. They are not medical advice and do not replace advice from your doctor. If you have a health "
              "condition, follow the plan your doctor has given you. Seek medical help promptly if you experience breathlessness, "
              "chest pain, dizziness or other worsening symptoms. In an emergency, call 112.")

REFERENCES = {
    "1": "Central Pollution Control Board (2014). National Air Quality Index (CUPS/82/2014-15). MoEFCC, Government of India.",
    "2": "Indian Economic Service (n.d.). National Air Quality Index. Arthapedia.",
    "3": "National Centre for Disease Control (2024). Air pollution and its impact on health: Handbook for ASHA (NPCCHH). MoHFW.",
    "4": "National Centre for Disease Control (2021). Health adaptation plan for diseases due to air pollution (NPCCHH). MoHFW.",
    "5": "World Health Organization (2024, 4 Oct). Air pollution: Personal interventions and risk communication.",
    "6": "World Health Organization (n.d.). How air pollution is destroying our health [Spotlight]. Accessed 20 Oct 2026.",
    "7": "World Health Organization (2024, 24 Oct). Ambient (outdoor) air pollution [Fact sheet].",
    "8": "World Health Organization (2021). WHO global air quality guidelines: particulate matter (PM2.5 and PM10), ozone, nitrogen dioxide, sulfur dioxide and carbon monoxide. Executive summary.",
    "9": "Central Pollution Control Board (2009, 18 Nov). National Ambient Air Quality Standards, Notification No. B-29016/20/90/PCI-I. Gazette of India, Extraordinary, Part III Section 4.",
}

POLLUTANT_NAMES = {"pm25": "PM2.5", "pm10": "PM10", "no2": "NO\u2082", "so2": "SO\u2082", "o3": "O\u2083", "co": "CO"}


def pname(key):
    """Display name of a pollutant key ('pm25' -> 'PM2.5'). Never show the raw key to users."""
    return POLLUTANT_NAMES.get(str(key).lower(), str(key))


VULNERABLE_GROUPS = {"lung", "heart", "child", "older", "pregnant", "outdoor_worker", "athlete"}


def rint(x):
    """Round half up, the way the page displays the AQI (Python's round() would round 100.5 to 100)."""
    return int(math.floor(float(x) + 0.5))


def category_of(aqi):
    """CPCB category of the DISPLAYED (rounded integer) AQI: 51-100 is Satisfactory, so 100.4 -> 100 -> Satisfactory."""
    aqi = rint(aqi)
    for ub, name in CATEGORIES:
        if aqi <= ub:
            return name
    return "Severe"


def thresholds(profile):
    """Effective advisory/alert AQI for a profile. Users may lower, never raise above defaults."""
    vulnerable = bool(set(profile.get("groups", [])) & VULNERABLE_GROUPS)
    base = DEFAULT_ALERT["vulnerable" if vulnerable else "healthy"]
    alert = min(int(profile.get("alert_from", base)), base)
    alert = min(alert, EVERYONE_ALERT)
    advisory = min(DEFAULT_ADVISORY["vulnerable" if vulnerable else "healthy"], alert)
    return {"vulnerable": vulnerable, "advisory_from": advisory, "alert_from": alert}


def advice(aqi, profile):
    """Return the advice for a (forecast) AQI value and a profile. Each item carries its source."""
    aqi = rint(aqi)                       # everything below uses the displayed integer AQI
    cat = category_of(aqi)
    th = thresholds(profile)
    groups = set(profile.get("groups", []))
    level = "alert" if aqi >= th["alert_from"] or aqi >= EVERYONE_ALERT else ("advisory" if aqi >= th["advisory_from"] else "none")
    idx = ORDER.index(cat)
    items = []
    if level != "none":
        general, vuln = MESSAGES[cat]
        items.append({"text": vuln if th["vulnerable"] else general, "source": SOURCE_OF_MESSAGES})
        if idx >= ORDER.index("Poor"):
            items.append({"text": "On poor to severe days, avoid outdoor morning and late-evening walks, runs, jogging and exercise",
                          "source": "[4]"})
            items.append({"text": "Practise wet mopping instead of sweeping", "source": "[4]"})
            items.append({"text": "Paper masks, handkerchiefs, scarves and cloth are not effective in poor to severe pollution",
                          "source": "[3][4]"})
        if level == "alert":
            if groups & {"lung", "heart"}:
                items.append({"text": "Keep prescribed medicines readily available and follow your doctor's instructions; "
                                      "seek medical advice promptly if symptoms worsen", "source": "[4]"})
            items.append({"text": "Consult the nearest doctor for breathlessness, giddiness, cough, chest discomfort or pain",
                          "source": "[4]"})
        if idx >= ORDER.index("Very Poor"):
            items.append({"text": WHO_MASK, "source": "[5]", "kind": "caution"})
    return {"aqi": round(aqi), "category": cat, "impact": IMPACT[cat], "impact_source": IMPACT_SRC[cat], "level": level,
            "thresholds": th, "items": items}


# ============================================================================================================================================
# Personalised, varied advice (20 Oct 2026). Built from parts; every health statement carries its source number. Sources and page numbers are
# listed in docs/health_advisory_reference.md section 7. Trend and best-time lines are our own forecast output, labelled "(our forecast)".
# ============================================================================================================================================
FORECAST_SRC = "(our forecast)"
GROUP_NAME = {"lung": "Lung disease", "heart": "Heart disease", "child": "Child", "older": "Older adult", "pregnant": "Pregnancy",
              "outdoor_worker": "Outdoor work", "athlete": "Regular exercise"}
GROUP_ORDER = ["lung", "heart", "pregnant", "child", "older", "outdoor_worker", "athlete"]
SAT, MOD, POOR, VPOOR, SEV = 1, 2, 3, 4, 5                      # indices in ORDER

# NCDC advice for the vulnerable population by category [4] (advisory poster, HAP 2021 pp. 38 and 57)
_VULN_ACTION = {SAT: "reduce prolonged or strenuous outdoor physical exertion", MOD: "avoid prolonged or strenuous outdoor physical exertion",
                POOR: "avoid outdoor physical activities", VPOOR: "remain indoors and keep activity levels low",
                SEV: "remain indoors and keep activity levels low"}
_MEDS = "keep your prescribed medicines readily available and follow your doctor's instructions"


def _group_line(g, ci):
    """(text, source) for health group g at category index ci (1 = Satisfactory .. 5 = Severe), or None."""
    # advice only: the CPCB impact sentence of the category (which names lung/heart disease, children and older adults) is already the
    # headline line, so it is not repeated in the profile lines (user request 21 Oct 2026)
    if g in ("lung", "heart"):
        if ci >= VPOOR:
            return (f"{_VULN_ACTION[ci]}, keep a check on your symptoms and seek medical advice promptly if they get worse", "[4]")
        if ci == POOR:
            return (f"{_VULN_ACTION[ci]} and {_MEDS}", "[4]")
        return (_MEDS, "[4]")
    if g in ("child", "older"):
        tail = "; there are no commercial respirators designed for children (based on information available as of February 2019)" if (g == "child" and ci >= VPOOR) else ""
        return (_VULN_ACTION[ci] + tail, "[4]" + ("[5]" if tail else ""))
    if g == "pregnant":
        return (f"WHO lists pregnant women among the groups at higher risk from air pollution; {_VULN_ACTION[ci]}", "[5][4]")
    if g == "outdoor_worker":
        if ci >= VPOOR:
            return ("keep activity levels low and use a close-fitted N95 or N99 mask while going out (see the WHO caution)", "[3]")
        if ci == POOR:
            return ("avoid heavy exertion when outside and take lots of water breaks; WHO advises choosing the best time and location "
                    "for outdoor work", "[3][5]")
        return ("WHO advises people at risk because of their work to choose the best time and location for outdoor work; "
                "take frequent water breaks between work", "[5][3]")
    if g == "athlete":
        if ci >= POOR:
            return ("on poor to severe days avoid outdoor morning and late-evening walks, runs, jogging and exercise; "
                    "reschedule outdoor activities", "[4]")
        return ("WHO advises keeping up regular physical activity even when the air is not ideal, but adapting its timing and location "
                "to reduce exposure; avoid exertion for long periods", "[5][3]")
    return None


# Main pollutant in plain words (WHO spotlight page [6]; WHO fact sheet [7])
POLLUTANT_INFO = {
    # wording follows the sources closely (checked against the pages on 21 Oct 2026; exact sentences in the reference document, section 7)
    "pm10": ("PM10 = particles 10 microns or less across; they can penetrate and lodge deep inside the lungs, which can cause irritation and inflammation", "[6]"),
    "pm25": ("PM2.5 = smaller, more health-damaging particles 2.5 microns or less across (60 of them make up the width of a human hair); "
             "they can penetrate the lung barrier and enter the blood system", "[6]"),
    "o3": ("O₃ = ozone at ground level, caused by a chemical reaction of gases such as NO₂ in sunlight; WHO calls it a major factor in causing asthma "
           "or making it worse", "[6]"),
    "no2": ("NO₂ = a gas from the combustion of fuels in furnaces, gas stoves, transport, industry and power generation", "[6][7]"),
    "so2": ("SO₂ = a gas mainly from the combustion of fossil fuels for domestic heating, industries and power generation", "[6]"),
    "co": ("CO = a colourless, odourless and tasteless toxic gas produced by the incomplete combustion of fuels such as wood, petrol, charcoal, "
           "natural gas and kerosene", "[7]"),
}

# Rotating tips: (lowest category index, groups it is for (None = everyone), groups it must NOT be shown to, text, source).
# Only wording listed in docs/health_advisory_reference.md section 7 ("Tips"); each tip only from the category where its source allows it:
# N95/N99 only from Very Poor (and never for a child: no respirators are designed for children [5]); items from the NCDC advisory written for
# severe-plus AQI (HAP 2021 pp. 44-45) only from Poor or Very Poor. Profile-specific tips come first in the rotation.
TIPS = [
    # profile-specific
    (MOD, {"outdoor_worker"}, None, "Take frequent water breaks between work", "[3]"),
    (SAT, {"athlete"}, None, "Adapt the timing and location of your exercise to reduce exposure", "[5]"),
    (VPOOR, {"child"}, None, "There are no commercial respirators designed for children (based on information available as of February 2019)", "[5]"),
    (VPOOR, {"lung", "heart"}, None, "WHO advises special caution with respirators for people with heart or lung disease", "[5]"),
    # everyone
    (SAT, None, None, "Check the air quality index before leaving home", "[4]"),
    (SAT, None, None, "Avoid going to places with heavy traffic and congested areas", "[4]"),
    (SAT, None, None, "Use clean smokeless fuels (gas or electricity) for cooking and heating", "[4]"),
    (SAT, None, None, "Don't burn firecrackers, wood, leaves or garbage", "[4]"),
    (SAT, None, None, "Don't smoke cigarettes, bidis or other tobacco products", "[4]"),
    (POOR, None, None, "Keep doors and windows closed in the early morning and late evening; ventilate in the afternoon (12 to 4 pm)", "[4]"),
    (POOR, None, None, "Practise wet mopping instead of sweeping", "[4]"),
    (POOR, None, None, "Avoid burning mosquito coils and incense sticks in closed rooms", "[4]"),
    (POOR, None, None, "Paper masks, handkerchiefs, scarves and cloth are not effective in poor to severe pollution", "[3][4]"),
    (VPOOR, None, {"child"}, "Use a close-fitted N95 or N99 mask while going out (see the WHO caution below)", "[3]"),
    (VPOOR, None, None, "Keep washing your eyes with running water and gargle regularly with warm water", "[4]"),
    (VPOOR, None, None, "Eat a healthy diet and drink plenty of water", "[3][4]"),
    (VPOOR, None, None, "If you use an air purifier, avoid one that works by generating ozone", "[4][5]"),
    (VPOOR, None, None, "Use the air conditioner (home or car) in re-circulate mode", "[4]"),
]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def tips_for(cat, groups=()):
    """The tips allowed for this category and profile, profile-specific ones first: list of (text, source)."""
    ci, g = ORDER.index(cat), set(groups or ())
    own = [(t, s) for lo, only, never, t, s in TIPS if only and ci >= lo and (g & only)]
    general = [(t, s) for lo, only, never, t, s in TIPS if not only and ci >= lo and not (never and (g & never))]
    return own + general


def alert_number(issued):
    """Deterministic alert number from the issue time ('YYYY-MM-DD HH...'): hours since 2026-01-01 00:00. The same alert (same issue hour) always
    gets the same tip; alerts issued at different hours get the next tips in the rotation."""
    try:
        d = datetime.strptime(str(issued)[:13], "%Y-%m-%d %H")
    except ValueError:
        return 0
    return int((d - datetime(2026, 1, 1)).total_seconds() // 3600)


def short_time(s):
    """'2026-04-22 14:00' -> '22 Apr 14:00'."""
    try:
        return f"{int(s[8:10])} {MONTHS[int(s[5:7]) - 1]} {s[11:16]}"
    except (ValueError, IndexError):
        return s


STATION_SRC = "(station data)"

# ---- presentation only (26 Oct 2026): bold key phrases and icons. The TEXT of every part is unchanged; "marked" is the same text with **...** around
# the first occurrence of each phrase below (tests strip the markers and compare with "text").
EMPHASIS = sorted([
    "N95 or N99 mask", "remain indoors and keep activity levels low", "Remain indoors and keep activity levels low", "Remain indoors as much as possible",
    "avoid outdoor physical activities", "Avoid outdoor physical activities", "avoid outdoor physical exertion", "Avoid outdoor physical exertion",
    "avoid prolonged or strenuous outdoor physical exertion", "reduce prolonged or strenuous outdoor physical exertion",
    "avoid physical exertion for long periods", "avoid exertion for long periods", "avoid heavy exertion when outside",
    "keep your prescribed medicines readily available", "Keep prescribed medicines readily available", "seek medical advice promptly",
    "Consult the nearest doctor", "frequent water breaks", "lots of water breaks", "Limit outdoor activity at all times",
    "Usually cleanest at this station", "No clearly better time", "no commercial respirators designed for children",
    "special caution", "not effective", "No special precautions", "No need for special precautions", "cover the nose", "cover nose",
    "avoid indoor pollution sources", "step out only if urgent", "choose the best time and location", "adapting its timing and location",
    "Adapt the timing and location", "heavy traffic", "Keep doors and windows closed", "wet mopping", "re-circulate mode",
], key=len, reverse=True)


def mark(text):
    """text with **...** around the first occurrence of each EMPHASIS phrase (longest first, never nested or overlapping)."""
    spans = []
    for ph in EMPHASIS:
        i = text.find(ph)
        if i >= 0 and not any(i < b and i + len(ph) > a for a, b in spans):
            spans.append((i, i + len(ph)))
    for a, b in sorted(spans, reverse=True):
        text = text[:a] + "**" + text[a:b] + "**" + text[b:]
    return text


def strip_marks(s):
    return str(s).replace("**", "")


def icon_for(p):
    """simple icon key for an action line: mask, home, clock, doctor, medicine, walking (else info)."""
    t, k = p["text"].lower(), p["kind"]
    if k == "doctor" or t.startswith("consult"):
        return "doctor"
    if k == "best_time" or "cleaner hours" in t:
        return "clock"
    if "indoors" in t or "doors and windows" in t:
        return "home"
    if "n95" in t:
        return "mask"
    if any(w in t for w in ("exertion", "physical activit", "exercise", "walks", "runs", "outdoor work")):
        return "walking"
    if "medicines" in t:
        return "medicine"
    if "mask" in t or "respirator" in t:
        return "mask"
    return "info"


def merged_groups(lines):
    """health-group lines with IDENTICAL action text (and source) merged into one: "Lung disease, heart disease, older adult: <action>". The action
    sentence itself is unchanged; only the group names are joined. 'covers' lists the original lines it replaces."""
    merged = {}
    for g in lines:
        name, action = g["text"].split(": ", 1)
        key = (action, g["source"])
        if key in merged:
            merged[key]["names"].append(name)
            merged[key]["covers"].append(g["text"])
            merged[key]["groups"].append(g["group"])
        else:
            merged[key] = {"names": [name], "covers": [g["text"]], "groups": [g["group"]], "action": action, "source": g["source"]}
    out = []
    for m in merged.values():
        names = m["names"][0] + "".join(", " + n[0].lower() + n[1:] for n in m["names"][1:])
        text = f"{names}: {m['action']}"
        out.append({"kind": "group", "text": text, "source": m["source"], "marked": mark(text), "group": m["groups"][0], "groups": m["groups"],
                    "covers": m["covers"]})
    return out


def top_actions(out, level):
    """the user's TOP 3 actions (presentation summary), chosen from the existing parts WITHOUT rewording, in this order: up to 2 health-group lines
    (GROUP_ORDER; groups with an identical action merged into one line), or "what to do" when the profile has no group line; the best time to go out;
    the doctor line (alert level); the tip; "what to do"."""
    if level == "none":
        return [{**out["what_to_do"], "icon": "info"}]
    cands = merged_groups(out["groups"])[:2] or [out["what_to_do"]]
    cands += [out["best_time"], out["doctor"], out["tip"], out["what_to_do"]]
    seen, top = set(), []
    for p in cands:
        if p and p["text"] not in seen:
            seen.add(p["text"])
            top.append({**p, "icon": icon_for(p)})
        if len(top) == 3:
            break
    return top


def personal_advice(aqi, profile, forecasts=None, now_aqi=None, dominant=None, seq=0, diurnal=None):
    """Advice built from parts for one AQI value (the alert / advice basis) and a profile.
    forecasts: the +1/+6/+12/+24 h forecasts (for the trend; unavailable or 'past' ones are skipped); now_aqi: current AQI; dominant: main
    pollutant key; seq: alert number (alert_number(issue time)), picks the tip deterministically; diurnal: the station's typical time-of-day
    pattern (diurnal.py) for the best time to go out.
    Every part is {"kind", "text", "source"}. "short" = the pop-up lines (1-2 profile lines, trend, best time, 1 tip; the pop-up adds its own
    forecast headline), "full" = everything (Health advice tab, e-mail)."""
    import diurnal as dmod
    aqi = rint(aqi)
    base = advice(aqi, profile)
    cat, level, th = base["category"], base["level"], base["thresholds"]
    ci = ORDER.index(cat)
    groups = set(profile.get("groups", []))

    def part(kind, text, src):
        return {"kind": kind, "text": text, "source": src, "marked": mark(text)}

    out = {"category": cat, "level": level, "aqi": aqi, "seq": int(seq)}
    out["headline"] = part("headline", f"{cat} (AQI {aqi}): {IMPACT[cat]}", IMPACT_SRC[cat])
    general, vuln = MESSAGES[cat]
    out["what_to_do"] = (part("what_to_do", "What to do: " + (vuln if th["vulnerable"] else general), "[3]") if level != "none"
                         else part("what_to_do", "No special precautions needed for your profile at this level", "[3]"))
    out["groups"] = []
    if level != "none":
        for g in GROUP_ORDER:
            if g in groups:
                gl = _group_line(g, max(ci, SAT))
                if gl:
                    out["groups"].append({**part("group", f"{GROUP_NAME[g]}: {gl[0]}", gl[1]), "group": g})
    # trend from our own AQI forecasts
    fc = sorted([f for f in (forecasts or []) if f.get("available", True) and f.get("aqi") is not None and f.get("status") != "past"
                 and f.get("horizon", 99) <= 24], key=lambda f: f["horizon"])
    out["trend"] = trend_short = None
    if fc:
        worst = max(fc, key=lambda f: (f["aqi"], -f["horizon"]))
        best = min(fc, key=lambda f: (f["aqi"], f["horizon"]))
        ref = rint(now_aqi) if now_aqi is not None else fc[0]["aqi"]
        up, down = worst["aqi"] - ref >= 10, ref - best["aqi"] >= 10
        wt, bt = short_time(worst["target_end"]), short_time(best["target_end"])
        if up and down:
            direction = "changing"
            word = (f"changing, up to {worst['aqi']} ({category_of(worst['aqi'])}) around {wt} (+{worst['horizon']} h) "
                    f"and down to {best['aqi']} around {bt} (+{best['horizon']} h)")
            brief = f"up to {worst['aqi']} by {wt}, then down to {best['aqi']}"
        elif up:
            direction = "up"
            word = f"rising, highest {worst['aqi']} ({category_of(worst['aqi'])}) around {wt} (+{worst['horizon']} h)"
            brief = f"rising to {worst['aqi']} by {wt}"
        elif down:
            direction = "down"
            word = f"falling, down to {best['aqi']} ({category_of(best['aqi'])}) around {bt} (+{best['horizon']} h)"
            brief = f"falling to {best['aqi']} by {bt}"
        else:
            direction = "steady"
            word = f"about steady, between {best['aqi']} and {worst['aqi']} over the next {fc[-1]['horizon']} h"
            brief = f"steady ({best['aqi']}-{worst['aqi']})"
        out["trend"] = {**part("trend", "Next 24 h: " + word, FORECAST_SRC), "dir": direction}       # dir: icon on the page (up/down/changing/steady)
        trend_short = {**part("trend", "Next 24 h: " + brief, FORECAST_SRC), "dir": direction}
    # best time to go out: the station's typical time-of-day pattern (not the AQI forecast points); Very Poor / Severe: no good time
    out["best_time"], out["best_how"], out["best"] = None, None, None
    if level != "none":
        if ci >= VPOOR:
            out["best_time"] = part("best_time", "Limit outdoor activity at all times", "[3]")
        elif diurnal is not None:
            if diurnal.get("status") == "ok":
                out["best"] = {"cleanest": diurnal["best"]["label"], "worst": diurnal["worst"]["label"], "drop": diurnal["drop"]}
                out["best_time"] = part("best_time", f"Usually cleanest at this station: {diurnal['best']['label']}; usually worst: "
                                                     f"{diurnal['worst']['label']} (typical pattern from the last 4 weeks, not a forecast)", "[5]")
            elif diurnal.get("status") == "no_clear":
                out["best_time"] = part("best_time", "No clearly better time at this station (typical pattern from the last 4 weeks)", STATION_SRC)
            else:
                out["best_time"] = part("best_time", "No clearly better time at this station (not enough measurements in the last 4 weeks)",
                                        STATION_SRC)
            out["best_how"] = dmod.HOW
    pi = POLLUTANT_INFO.get(str(dominant or "").lower())
    out["pollutant"] = part("pollutant", "Main pollutant: " + pi[0], pi[1]) if pi else None
    tips = tips_for(cat, groups) if level != "none" else []
    out["tip"] = part("tip", "Tip: " + tips[int(seq) % len(tips)][0], tips[int(seq) % len(tips)][1]) if tips else None
    out["doctor"] = (part("doctor", "Consult the nearest doctor for breathlessness, giddiness, cough, chest discomfort or pain, or irritation "
                                    "in the eyes", "[4]") if level == "alert" else None)
    out["caution"] = part("caution", WHO_MASK, "[5]") if ci >= VPOOR else None
    # pop-up: 1-2 profile lines (brief: the action without the CPCB impact clause), trend, best time, 1 tip
    profile_lines = [{**part("group", g0["text"], g0["source"]), "group": g0["group"]} for g0 in out["groups"][:2]]
    if not profile_lines:
        profile_lines = [out["what_to_do"]]
    out["short"] = [x for x in (*profile_lines, trend_short, out["best_time"], out["tip"]) if x]
    out["full"] = [x for x in [out["headline"], out["what_to_do"], *out["groups"], out["trend"], out["best_time"], out["pollutant"],
                               out["tip"], out["doctor"], out["caution"]] if x]
    out["top3"] = top_actions(out, level)
    return out
