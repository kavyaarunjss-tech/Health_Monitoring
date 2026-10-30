"""WCAG AA contrast scan of every visible text on a page (used by test_readability.py in light AND dark mode).

ALLTEXT_JS returns the failures: each element with its own visible text (HTML or SVG <text>), compared with the first opaque background behind
it (ancestors); text over a gradient or image is skipped (cannot be measured), as are disabled controls (WCAG exempts them) and deliberately dimmed
elements (effective opacity < 0.99, e.g. stale rings that carry a 'STALE' label). AA: 4.5:1, or 3:1 for large text (>= 24 px, or >= 18.66 px bold).
"""
ALLTEXT_JS = r"""(() => {
  const rgba = (c) => { const m = (c || '').match(/[\d.]+/g); if (!m) return null; return [+m[0], +m[1], +m[2], m.length > 3 ? +m[3] : 1]; };
  const lum = (c) => { const f = (v) => { v /= 255; return v <= .03928 ? v / 12.92 : Math.pow((v + .055) / 1.055, 2.4); }; return .2126 * f(c[0]) + .7152 * f(c[1]) + .0722 * f(c[2]); };
  const bgOf = (el) => {
    for (let e = el; e && e.nodeType === 1; e = e.parentElement) {
      const cs = getComputedStyle(e);
      if (cs.backgroundImage && cs.backgroundImage !== 'none' && !/^url\("data:image\/svg/.test(cs.backgroundImage)) return null;
      const b = rgba(cs.backgroundColor); if (b && b[3] > .5) return b;
    }
    return rgba(getComputedStyle(document.documentElement).backgroundColor) || [255, 255, 255, 1];
  };
  const opac = (el) => { let o = 1; for (let e = el; e && e.nodeType === 1; e = e.parentElement) o *= +getComputedStyle(e).opacity; return o; };
  const out = []; let n = 0;
  document.querySelectorAll('body *').forEach((el) => {
    if (['SCRIPT', 'STYLE', 'NOSCRIPT', 'TITLE', 'OPTION'].includes(el.tagName)) return;
    const own = Array.from(el.childNodes).filter((x) => x.nodeType === 3).map((x) => x.textContent).join('').trim();
    if (!own) return;
    if (!el.getClientRects().length) return;
    const cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || cs.display === 'none') return;
    if (el.closest('[hidden], :disabled, [aria-disabled=true]')) return;
    if (opac(el) < .99) return;
    const svg = el instanceof SVGElement;
    const fg = rgba(svg ? cs.fill : cs.color), bg = bgOf(el);
    if (!fg || !bg) return;
    n++;
    const L1 = lum(fg), L2 = lum(bg), r = (Math.max(L1, L2) + .05) / (Math.min(L1, L2) + .05);
    const size = parseFloat(cs.fontSize), bold = +cs.fontWeight >= 700, need = (size >= 24 || (bold && size >= 18.66)) ? 3 : 4.5;
    if (r < need) out.push({ text: own.slice(0, 40), r: Math.round(r * 100) / 100, need, fg: (svg ? cs.fill : cs.color), bg: 'rgb(' + bg.slice(0, 3).join(',') + ')',
                             where: (el.id ? '#' + el.id : el.tagName.toLowerCase()) + (el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\s+/).join('.') : '') });
  });
  return { checked: n, fails: out };
})()"""
