// Cuts lines to Makati's outline, so traffic can be drawn inside the city and nowhere else. A style filter cannot do it:
// it keeps or drops a whole line, and at city zoom TomTom's lines are long and run through the border.
// Pure geometry on [lng, lat]: the flat treatment is fine at the scale of a city.
type Pos = [number, number];
type Line = Pos[];

// Inside means inside an odd number of the loops: the city's loop is one, a hole in it (an enclave) is a second.
export function inside(p: Pos, loops: readonly Line[]): boolean {
  let odd = false;
  for (const loop of loops) {
    for (let i = 0, j = loop.length - 1; i < loop.length; j = i++) {
      const [xi, yi] = loop[i];
      const [xj, yj] = loop[j];
      if (yi > p[1] !== yj > p[1] && p[0] < ((xj - xi) * (p[1] - yi)) / (yj - yi) + xi) odd = !odd;
    }
  }
  return odd;
}

// Where along a->b (0 to 1) it crosses the side c->d, or null.
function crossing(a: Pos, b: Pos, c: Pos, d: Pos): number | null {
  const rx = b[0] - a[0];
  const ry = b[1] - a[1];
  const sx = d[0] - c[0];
  const sy = d[1] - c[1];
  const denominator = rx * sy - ry * sx;
  if (denominator === 0) return null; // parallel
  const t = ((c[0] - a[0]) * sy - (c[1] - a[1]) * sx) / denominator;
  const u = ((c[0] - a[0]) * ry - (c[1] - a[1]) * rx) / denominator;
  return t > 0 && t < 1 && u >= 0 && u <= 1 ? t : null;
}

// The parts of one line that are inside the city, as lines.
export function clipLine(line: Line, loops: readonly Line[]): Line[] {
  const out: Line[] = [];
  let current: Line | null = null;
  for (let i = 0; i < line.length - 1; i++) {
    const a = line[i];
    const b = line[i + 1];
    const [lo, hi] = [Math.min(a[0], b[0]), Math.max(a[0], b[0])];
    const [bottom, top] = [Math.min(a[1], b[1]), Math.max(a[1], b[1])];
    const cuts = [0, 1];
    for (const loop of loops) {
      for (let k = 0; k < loop.length - 1; k++) {
        const c = loop[k];
        const d = loop[k + 1];
        if (Math.max(c[0], d[0]) < lo || Math.min(c[0], d[0]) > hi) continue; // the side is off to one side of the segment
        if (Math.max(c[1], d[1]) < bottom || Math.min(c[1], d[1]) > top) continue;
        const t = crossing(a, b, c, d);
        if (t !== null) cuts.push(t);
      }
    }
    cuts.sort((x, y) => x - y);
    for (let k = 0; k < cuts.length - 1; k++) {
      const [t0, t1] = [cuts[k], cuts[k + 1]];
      if (t1 - t0 < 1e-12) continue;
      const at = (t: number): Pos => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
      if (inside(at((t0 + t1) / 2), loops)) {
        if (!current) out.push((current = [at(t0)]));
        current.push(at(t1));
      } else {
        current = null;
      }
    }
  }
  return out;
}

type Feature = { geometry: { type: string; coordinates: unknown }; properties?: Record<string, unknown> | null };

// Road segments cut to the city: the ones left, with the properties the layer paints from.
export function clipFeatures(features: readonly Feature[], loops: readonly Line[]) {
  const box = bounds(loops);
  const out = [];
  for (const f of features) {
    const g = f.geometry;
    const lines = (g.type === "LineString" ? [g.coordinates] : g.type === "MultiLineString" ? g.coordinates : []) as Line[];
    const kept = lines.filter((l) => touchesBox(l, box)).flatMap((l) => clipLine(l, loops));
    if (!kept.length) continue;
    out.push({
      type: "Feature" as const,
      geometry: { type: "MultiLineString" as const, coordinates: kept },
      properties: {
        traffic_level: f.properties?.traffic_level,
        road_type: f.properties?.road_type,
        traffic_road_coverage: f.properties?.traffic_road_coverage,
      },
    });
  }
  return { type: "FeatureCollection" as const, features: out };
}

function bounds(loops: readonly Line[]): [number, number, number, number] {
  const all = loops.flat();
  return [
    Math.min(...all.map((p) => p[0])),
    Math.max(...all.map((p) => p[0])),
    Math.min(...all.map((p) => p[1])),
    Math.max(...all.map((p) => p[1])),
  ];
}

// Whether the line's own box overlaps the city's: a quick way to leave out the ones nowhere near it.
function touchesBox(line: Line, [west, east, south, north]: [number, number, number, number]): boolean {
  const xs = line.map((p) => p[0]);
  const ys = line.map((p) => p[1]);
  return Math.min(...xs) <= east && Math.max(...xs) >= west && Math.min(...ys) <= north && Math.max(...ys) >= south;
}
