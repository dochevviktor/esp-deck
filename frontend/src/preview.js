// DejaVu Sans 2.37 coverage/metrics are extracted from the pinned firmware data.
// Compare this port against the native BMP fixtures; never use canvas.fillText.
export function renderPreview(visual, source, fonts) {
  const rgb = color => [1, 2, 3].map(i => parseInt(color.slice(i * 2 - 1, i * 2 + 1), 16));
  const bg = rgb(visual.background_color), inkColor = rgb(visual.text_color), edgeColor = rgb(visual.outline_color);
  const out = new Uint8ClampedArray(72 * 72 * 4), ink = new Uint8Array(72 * 72);
  const font = fonts[visual.font], glyphs = new Map(font.glyphs.map(g => [g[0], g]));
  const points = [...visual.text].map(c => c === "\n" ? 10 : glyphs.has(c.codePointAt(0)) ? c.codePointAt(0) : 63);
  const bounds = line => {
    let min = 0, pen = 0, max = 0;
    for (const point of line) {const g = glyphs.get(point); min = Math.min(min, pen + g[5]); max = Math.max(max, pen + g[5] + g[3]); pen += g[2];}
    return [Math.max(max, pen) - min, min];
  };
  const lines = [];
  const bx = visual.text_x ?? 3, by = visual.text_y ?? 3;
  const bw = Math.max(24, visual.text_width ?? 66), bh = visual.text_height ?? 66;
  const align = visual.text_align ?? 1, valign = visual.text_valign ?? 2;
  let position = 0;
  while (position < points.length && lines.length < 2) {
    const line = []; lines.push(line);
    while (points[position] === 32) position++;
    const start = position; let lastSpace = points.length;
    while (position < points.length && points[position] !== 10) {
      line.push(points[position]);
      if (bounds(line)[0] > bw) {line.pop(); break;}
      if (points[position] === 32) lastSpace = position;
      position++;
    }
    if (points[position] === 10) position++;
    else if (position < points.length && lastSpace < position && lastSpace > start) {line.length = lastSpace - start; position = lastSpace + 1;}
    while (line.at(-1) === 32) line.pop();
  }
  while (points[position] === 32 || points[position] === 10) position++;
  if (position < points.length) {
    const last = lines.at(-1);
    while (last.length && bounds([...last, 46, 46, 46])[0] > bw) last.pop();
    last.push(46, 46, 46);
  }
  for (let row = 0; row < lines.length; row++) {
    const [width, minimum] = bounds(lines[row]);
    let x = bx - minimum + (align === 0 ? 0 : align === 1 ? Math.trunc((bw - width) / 2) : bw - width);
    const spare = bh - lines.length * font.height;
    const y = by + (valign === 0 ? 0 : valign === 1 ? Math.trunc(spare / 2) : spare) + row * font.height;
    for (const point of lines[row]) {
      const [, offset, advance, w, h, ox, oy] = glyphs.get(point);
      for (let j = 0; j < h; j++) for (let i = 0; i < w; i++) {
        const px = x + ox + i, py = y + oy + j, n = j * w + i;
        if (px >= bx && px < bx + bw && py >= by && py < by + bh && px >= 0 && px < 72 && py >= 0 && py < 72) {
          const value = ((font.bits[offset + (n >> 1)] >> (n % 2 ? 0 : 4)) & 15) * 17;
          ink[py * 72 + px] = Math.max(ink[py * 72 + px], value);
        }
      }
      x += advance;
    }
  }
  const blend = (back, front, a) => Math.floor((back * (255 - a) + front * a + 127) / 255);
  let sw, sh, ox, oy;
  if (source) {
    const d = visual.fit === "crop" ? Math.min(source.width, source.height) : Math.max(source.width, source.height);
    sw = Math.max(1, Math.floor((source.width * 72 + Math.floor(d / 2)) / d));
    sh = Math.max(1, Math.floor((source.height * 72 + Math.floor(d / 2)) / d));
    ox = Math.trunc((72 - sw) / 2); oy = Math.trunc((72 - sh) / 2);
  }
  const coord = (at, src, scaled) => Math.max(0, Math.min((src - 1) * 256, Math.floor((2 * at + 1) * src * 128 / scaled) - 128));
  for (let y = 0; y < 72; y++) for (let x = 0; x < 72; x++) {
    let background = bg, edge = 0;
    if (source && x >= ox && y >= oy && x < ox + sw && y < oy + sh) {
      const sx = coord(x - ox, source.width, sw), sy = coord(y - oy, source.height, sh);
      let alpha = 0; const sum = [0, 0, 0];
      for (let j = 0; j < 2; j++) for (let i = 0; i < 2; i++) {
        const index = (Math.min((sy >> 8) + j, source.height - 1) * source.width + Math.min((sx >> 8) + i, source.width - 1)) * 4;
        const a = (i ? sx % 256 : 256 - sx % 256) * (j ? sy % 256 : 256 - sy % 256) * source.data[index + 3];
        alpha += a;
        for (let c = 0; c < 3; c++) sum[c] += source.data[index + c] * a;
      }
      background = sum.map((v, c) => Math.floor((v + bg[c] * (255 * 65536 - alpha) + 255 * 32768) / (255 * 65536)));
    }
    for (let j = Math.max(0, y - 1); j <= Math.min(71, y + 1); j++) for (let i = Math.max(0, x - 1); i <= Math.min(71, x + 1); i++) edge = Math.max(edge, ink[j * 72 + i]);
    const n = y * 72 + x;
    for (let c = 0; c < 3; c++) out[n * 4 + c] = blend(blend(background[c], edgeColor[c], edge), inkColor[c], ink[n]);
    out[n * 4 + 3] = 255;
  }
  return out;
}
