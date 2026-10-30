/* "All stations now", view (b) "By category": one donut of how many stations are in each CPCB category (centre "8 stations", legend with counts).
   Hovering or tapping a segment or a legend entry lists the station names in it (each name opens that station). Isolated component: delete this file
   (and its <script> tag) to drop the view. */
window.StationsByCat = {
  render(el, data, current, onPick) {
    const groups = {};
    data.stations.forEach((s) => { const k = s.aqi == null ? "No data" : s.category; (groups[k] = groups[k] || []).push(s); });
    const keys = CPCB_CATS.filter((c) => groups[c]).concat(groups["No data"] ? ["No data"] : []);
    const segs = keys.map((k) => ({ value: groups[k].length, cls: k === "No data" ? "" : STROKE(k), hatch: k === "No data", cat: k,
                                    label: k + ": " + groups[k].length + " station" + (groups[k].length === 1 ? "" : "s") }));
    const n = data.stations.length;
    el.innerHTML = "<div class='st-bycat'>" + donutSvg(segs, [String(n), "stations"], 170, "Stations per CPCB category: " + segs.map((x) => x.label).join(", ")) +
      "<div><ul class='dn-legend st-legend'>" + keys.map((k, i) => "<li><button type='button' data-i='" + i + "'><span class='sw " + (k === "No data" ? "sw-hatch" : CAT_CLASS(k)) +
        "' aria-hidden='true'></span>" + escHtml(k) + " <b>" + groups[k].length + "</b></button></li>").join("") + "</ul>" +
      "<p class='st-list small' aria-live='polite'>Hover or tap a category to see its stations.</p></div></div>";
    const list = el.querySelector(".st-list");
    const show = (i) => {
      const k = keys[i];
      list.innerHTML = "<b>" + escHtml(k) + ":</b> " + groups[k].map((s) => "<button type='button' class='linklike' data-station='" + s.id + "'>" +
        escHtml(ST_SHORT[s.id] || s.name) + (s.aqi != null ? " (" + s.aqi + (stAge(s) ? ", " + stAge(s) : "") + ")" : "") + "</button>").join(", ");
      list.querySelectorAll("button").forEach((b) => b.onclick = () => onPick && onPick(b.dataset.station));
      el.querySelectorAll(".st-legend button").forEach((b) => b.setAttribute("aria-pressed", String(+b.dataset.i === i)));
    };
    el.querySelectorAll(".dn-seg").forEach((c) => { c.addEventListener("mouseenter", () => show(+c.dataset.i)); c.addEventListener("click", () => show(+c.dataset.i)); });
    el.querySelectorAll(".st-legend button").forEach((b) => { b.addEventListener("mouseenter", () => show(+b.dataset.i)); b.addEventListener("click", () => show(+b.dataset.i)); });
    const cur = data.stations.find((s) => s.id === current);
    if (cur) show(keys.indexOf(cur.aqi == null ? "No data" : cur.category));       // start with the open station's category
  },
};
