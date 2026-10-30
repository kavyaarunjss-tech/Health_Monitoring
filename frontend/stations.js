/* "All stations now" card: the shell (title, toggle "Each station | By category", loading). The two views are separate components so the one not chosen
   can be removed later by deleting its file and its entry in VIEWS:
     stations_each.js  -> window.StationsEach   (a) one ring gauge per station (default)
     stations_bycat.js -> window.StationsByCat  (b) one donut of stations per CPCB category
   Data: GET /api/stations/now (replay: at the replay clock; live: newest values with their age). The choice is remembered in localStorage aqiStationsView. */
const ST_SHORT = { silkboard: "Silk Board", hebbal: "Hebbal", jayanagar: "Jayanagar", chikkaballapura: "Chikkaballapur", chikkamagaluru: "Chikkamagaluru",
                   mysuru: "Mysuru", ramanagara: "Ramanagara", madikeri: "Madikeri" };
const ST_VIEWS = [["each", "Each station", () => window.StationsEach], ["bycat", "By category", () => window.StationsByCat]];
function stView() {
  let v = "each";
  try { v = localStorage.getItem("aqiStationsView") || "each"; } catch (e) { /* storage blocked: default */ }
  return ST_VIEWS.some((x) => x[0] === v && x[2]()) ? v : "each";
}
function stAge(s) {                         // "no data" / "N h old" / "" (fresh) for a station
  if (s.aqi == null) return "no data";
  return s.age_hours >= 1 ? Math.round(s.age_hours) + " h old" : "";
}
function renderStations(box, data, current, onPick) {
  if (!box) return;
  if (!data) { box.innerHTML = "<p class='small muted'>No station data.</p>"; return; }
  box.dataset.clock = data.clock;
  const view = stView();
  const stale = data.stations.filter((s) => s.status === "stale");
  const head = "<div class='st-head'><div><h2 class='card-title'>All stations now</h2><p class='small muted'>" +
    (data.mode === "live" ? "Newest observed CPCB AQI at each station, with its age"
                          : "Observed CPCB AQI at each station for the hour ending " + escHtml(data.clock_end || String(data.clock).slice(0, 16)) + " IST (replay time)") +
    ". Click a station to open it.</p></div><div class='seg' role='group' aria-label='Station view'>" +
    ST_VIEWS.filter((x) => x[2]()).map((x) => "<button type='button' data-view='" + x[0] + "' aria-pressed='" + (x[0] === view) + "'>" + x[1] + "</button>").join("") + "</div></div>" +
    (stale.length ? "<p class='wk-stale' role='status'>DATA IS OLD: " + (stale.length === data.stations.length ? "every station's" : stale.length + " stations'") +
      " newest value is more than 24 h old (" + stale.map((s) => ST_SHORT[s.id] + " " + Math.round(s.age_hours) + " h").join(", ") + ").</p>" : "");
  box.innerHTML = head + "<div class='st-body'></div>";
  const comp = ST_VIEWS.find((x) => x[0] === view)[2]();
  comp.render(box.querySelector(".st-body"), data, current, onPick);
  box.querySelectorAll(".seg button").forEach((b) => b.onclick = () => {
    try { localStorage.setItem("aqiStationsView", b.dataset.view); } catch (e) { /* not remembered */ }
    renderStations(box, data, current, onPick);
  });
}
async function loadStations(box, params, current, onPick) {   // fetch + render; answers that arrive out of order are dropped
  const my = (box._st = (box._st || 0) + 1);
  try {
    const r = await apiFetch("/api/stations/now?" + new URLSearchParams(params).toString(), { cache: "no-store" });
    const d = r.ok ? await r.json() : null;
    if (my === box._st) { box._data = d; renderStations(box, d, current, onPick); }
  } catch (e) { /* the server bar reports connection problems */ }
}
