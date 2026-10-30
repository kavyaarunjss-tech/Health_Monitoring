/* "All stations now", view (a) "Each station": one ring gauge per station (ring filled to AQI/500, coloured by CPCB category, AQI in the centre,
   station name + category label below; grey "no data" / "N h old" when missing or old). Click a ring to open that station. Isolated component:
   delete this file (and its <script> tag) to drop the view. */
window.StationsEach = {
  render(el, data, current, onPick) {
    const R = 30, C = 2 * Math.PI * R;
    el.innerHTML = "<div class='st-rings'>" + data.stations.map((s) => {
      const has = s.aqi != null, frac = has ? Math.min(s.aqi, 500) / 500 : 0, age = stAge(s), old = s.status === "stale";
      return "<button type='button' class='st-ring" + (old ? " st-old" : "") + (has ? "" : " st-none") + "' data-station='" + s.id + "'" +
        (s.id === current ? " aria-current='true'" : "") + " aria-label='" + escHtml(s.name + ": " + (has ? "AQI " + s.aqi + ", " + s.category : "no data") + (age ? ", " + age : "")) + "'>" +
        "<svg viewBox='0 0 80 80' width='76' height='76' aria-hidden='true'><circle cx='40' cy='40' r='" + R + "' fill='none' stroke='var(--line)' stroke-width='9'/>" +
        (has ? "<circle class='" + STROKE(s.category) + "' cx='40' cy='40' r='" + R + "' fill='none' stroke-width='9' stroke-linecap='round' stroke-dasharray='" +
          (frac * C).toFixed(2) + " " + C.toFixed(2) + "' transform='rotate(-90 40 40)'/>" : "") +
        "<text x='40' y='45' text-anchor='middle' class='st-num'>" + (has ? s.aqi : "–") + "</text></svg>" +
        "<span class='st-name'>" + escHtml(ST_SHORT[s.id] || s.name) + "</span>" +
        (has ? catBadge(s.category) : "<span class='catpill st-nodata'>no data</span>") +
        (age && has ? "<span class='st-age" + (old ? " st-age-old" : "") + "'>" + (old ? "STALE · " : "") + age + "</span>" : "") + "</button>";
    }).join("") + "</div>";
    el.querySelectorAll(".st-ring").forEach((b) => b.onclick = () => onPick && onPick(b.dataset.station));
  },
};
