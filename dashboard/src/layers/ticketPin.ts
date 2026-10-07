// Small status-coloured map pin. Generated locally so registration is synchronous,
// including after a style reload; the bottom tip sits at the report coordinate.
export function ticketPinImage(hex: string) {
  const scale = 3, width = 96, height = 126;
  const data = new Uint8Array(width * height * 4);
  const rgb = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
  const within = (x: number, y: number, radius: number, tip: number) =>
    Math.hypot(x - 16, y - 15) <= radius ||
    (y >= 20 && y <= tip && Math.abs(x - 16) <= radius * 0.85 * (tip - y) / (tip - 20));
  for (let py = 0; py < height; py++) {
    for (let px = 0; px < width; px++) {
      const x = (px + 0.5) / scale, y = (py + 0.5) / scale;
      if (!within(x, y, 14, 42)) continue;
      const white = !within(x, y, 12, 38) || Math.hypot(x - 16, y - 15) < 4;
      const at = (py * width + px) * 4;
      data.set(white ? [255, 255, 255, 255] : [...rgb, 255], at);
    }
  }
  return { width, height, data };
}
