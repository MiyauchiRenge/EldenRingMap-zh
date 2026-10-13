/**
 * Where a marker is, in the game's own words.
 *
 * data/regions.json carries the world map's own region labels (with rectangles); beside a region goes
 * the nearest grace or POI, which is the part you can act on. The rectangles overlap and leave gaps -
 * the starting area has none at all, because the game reveals it from the start - so a name that
 * shares a decent run of characters with a region name settles the cases the rectangles get wrong.
 */
import { layerLabel, state } from './core.js';

/* Where a marker is, in the game's own words.
 *
 * "The Lands Between" is the whole game, so it tells a player nothing about which
 * of the eleven Nomadic Merchants - or which of the 3,300 items - a marker is.
 * data/regions.json (build_markers.py) carries the region labels the world map
 * itself shows: Limgrave, Liurnia of the Lakes, Caelid, Ainsel River, Realm of
 * Shadow. Those labels have rectangles, but the rectangles overlap and leave
 * gaps, and the starting area has no rectangle at all because the game reveals it
 * from the start - that one is flagged `default` and is what a marker falls back
 * to when no rectangle is near.
 *
 * Beside the region goes the nearest grace or POI, which is the part that is
 * actually actionable: "Liurnia of the Lakes (Bellum Church)". It is dropped when
 * the marker's own name already says it - a grace is its own nearest place, and a
 * merchant's name carries its spot.
 */
export const REGION_NEAR_MAX = 400;      // master px; further away is not "here"
export const REGION_FAMILY = { M11: 'M10' };   // the DLC's underground shares M10's labels
export const dictName = (d) => (d ? (d[I18n.lang] || d.en || '') : '');

/**
 * Longest run of characters two names share, so a place can vouch for a region.
 *
 * The rectangles are the map pieces' reveal areas, which are narrower than the
 * regions the labels name: the grace "Liurnia Lake Shore" sits just outside the
 * Liurnia rectangle, in Limgrave's. The game's own text settles it - a grace name
 * that shares a decent run with a region name ("利耶尼亚湖" / "湖之利耶尼亚",
 * "Liurnia Lake Shore" / "Liurnia of the Lakes") is evidence the rectangle rule
 * does not have.
 */
export function sharedRun(a, b) {
  let best = 0;
  const prev = new Array(b.length + 1).fill(0);
  for (let i = 1; i <= a.length; i++) {
    let last = 0;
    for (let j = 1; j <= b.length; j++) {
      const cur = prev[j];
      prev[j] = a[i - 1] === b[j - 1] ? last + 1 : 0;
      if (prev[j] > best) best = prev[j];
      last = cur;
    }
  }
  return best;
}

export function regionFor(m, near) {
  if (!m || m.px == null || !state.regions.length) return null;
  const layer = REGION_FAMILY[m.master] || m.master;
  const usable = state.regions.filter((r) => !r.masters || !layer || r.masters.includes(layer));
  // A nearby place whose name names a region wins over the rectangles.
  for (const name of [dictName(near), ...Object.values(near || {})]) {
    if (!name || name.length < 3) continue;
    const hinted = usable.filter((r) => sharedRun(name, dictName(r.names)) >= 3);
    if (hinted.length === 1) return hinted[0];
  }
  let best = null, bestD = Infinity, fallback = null;
  for (const r of usable) {
    if (r.default) { fallback = r; continue; }
    const [l, top, right, b] = r.rect;
    const dx = m.px < l ? l - m.px : (m.px > right ? m.px - right : 0);
    const dy = m.py < top ? top - m.py : (m.py > b ? m.py - b : 0);
    const d = Math.sqrt(dx * dx + dy * dy);
    if (d < bestD) { bestD = d; best = r; }
  }
  return (best && bestD <= REGION_NEAR_MAX) ? best : (fallback || best);
}

export function nearFor(m) {
  if (!m || m.px == null) return null;
  let best = null, bestD = Infinity;
  for (const p of state.places) {
    if (p === m || p.master !== m.master) continue;
    const d = (p.px - m.px) ** 2 + (p.py - m.py) ** 2;
    if (d < bestD) { bestD = d; best = p; }
  }
  if (!best) return null;
  const mine = m.names ? Object.values(m.names) : [];
  return Object.values(best.names || {}).some((v) => v && mine.includes(v))
    ? null : best.names;
}

export function annotatePlace(m) {
  const n = nearFor(m);
  if (n) m.near = n;
  const r = regionFor(m, n);
  if (r) m.region = r.names;
  return m;
}

export function placeLabel(m) {
  const region = dictName(m.region);
  const near = dictName(m.near);
  if (region) return near ? `${region}（${near}）` : region;
  return m.master ? layerLabel(m.master) : '';
}
