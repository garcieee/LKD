import { test } from "node:test";
import assert from "node:assert/strict";
import { MAKATI, lockBounds } from "./makati.ts";

// Ground size in km at the city's latitude, independent of the Mercator math under test.
function sizeKm([[w, s], [e, n]]: ReturnType<typeof lockBounds>) {
  const lat = (s + n) / 2;
  return { w: (e - w) * 111.32 * Math.cos((lat * Math.PI) / 180), h: (n - s) * 110.57 };
}

for (const [name, vw, vh] of [
  ["desktop", 1440, 900],
  ["phone", 390, 844],
  ["square", 800, 800],
] as const) {
  test(`${name}: city plus margin fits, screen shape matches, short axis only`, () => {
    const b = lockBounds(vw, vh);
    const [[w, s], [e, n]] = MAKATI.bounds;
    const m = MAKATI.lockMargin;
    assert.ok(b[0][0] <= w - m + 1e-9 && b[1][0] >= e + m - 1e-9, "city + margin inside, east-west");
    assert.ok(b[0][1] <= s - m + 1e-9 && b[1][1] >= n + m - 1e-9, "city + margin inside, north-south");
    const k = sizeKm(b);
    assert.ok(Math.abs(k.w / k.h / (vw / vh) - 1) < 0.01, "same aspect as the screen");
    const grewEW = b[0][0] < w - m - 1e-6;
    const grewNS = b[0][1] < s - m - 1e-6;
    assert.ok(!(grewEW && grewNS), "grows along one axis only");
  });
}

test("a collapsed container still gives usable bounds", () => {
  for (const [vw, vh] of [[0, 0], [500, 0], [0, 500]]) {
    assert.ok(lockBounds(vw, vh).flat().every(Number.isFinite));
  }
});
