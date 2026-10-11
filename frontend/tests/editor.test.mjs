import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {deflateSync} from "node:zlib";
import {renderPreview} from "../src/preview.js";
import {decodeArtwork} from "../src/png.js";
import {defaults, rearrange, previewVisual, blankKey, pageKeys, allKeys} from "../src/layout.js";

const source = readFileSync(new URL("../../components/stream_deck/render_font_data.cpp", import.meta.url), "utf8");
const fonts = {};
for (const size of [12, 16, 20]) fonts[size] = {
  bits: [...source.match(new RegExp(`BITS_${size}\\[\\] = \\{([\\s\\S]*?)\\};`))[1].matchAll(/0x([a-f0-9]{2})/g)].map(m => parseInt(m[1], 16)),
  glyphs: [...source.match(new RegExp(`GLYPHS_${size}\\[\\] = \\{([\\s\\S]*?)\\};`))[1].matchAll(/\{([^}]+)\}/g)].map(m => m[1].split(",").map(Number)),
  height: Number(source.match(new RegExp(`const Font FONT_${size}[^\\n]+, ${size}, (\\d+)\\}`))[1]),
};
const fixture = name => readFileSync(new URL(`../../tests/fixtures/rendering/${name}`, import.meta.url));
test("preview matches production renderer BMP fixtures including all v2 alignments pixel for pixel", () => {
  const rgb = fixture("asymmetric.rgb"), rgba = new Uint8Array(72 * 72 * 4);
  for (let n = 0; n < 72 * 72; n++) {rgba.set(rgb.slice(n * 3, n * 3 + 3), n * 4); rgba[n * 4 + 3] = 255;}
  const asymmetric = {data: rgba, width: 72, height: 72};
  const alpha = {data: new Uint8Array(18 * 9 * 4), width: 18, height: 9};
  for (let y = 0; y < 9; y++) for (let x = 0; x < 18; x++) alpha.data.set([x * 15, y * 31, 220, x < 6 ? 0 : x < 12 ? 128 : 255], (y * 18 + x) * 4);
  const cases = [
    ["empty", {}, null], ["asymmetric", {}, asymmetric], ["alpha_contain", {}, alpha], ["alpha_crop", {fit: "crop"}, alpha],
    ...[12, 16, 20].map(font => [`font_${font}`, {text: "Café", font}, null]),
    ["two_lines", {text: "Desk\nReady"}, null], ["truncated", {text: "Supercalifragilistic desk controller display"}, null],
    ["unsupported", {text: "Lamp 💡"}, null], ["combined", {text: "Desk", text_color: "#FFDC40"}, asymmetric],
    ...[0, 1, 2].flatMap(text_align => [0, 1, 2].map(text_valign => [
      `position_${text_align}_${text_valign}`, {text: "Positioned label wraps", text_x: 24, text_y: 12,
        text_width: 48, text_height: 36, text_align, text_valign}, null])),
  ];
  for (const [name, patch, image] of cases) {
    const pixels = renderPreview({...defaults, background_color: "#102030", ...patch}, image, fonts), expected = fixture(`${name}.native.bmp`);
    for (let y = 0; y < 72; y++) for (let x = 0; x < 72; x++) for (let c = 0; c < 3; c++) {
      assert.equal(pixels[(y * 72 + x) * 4 + c], expected[54 + (y * 72 + 71 - x) * 3 + 2 - c], `${name} at ${x},${y},${c}`);
    }
  }
});
test("page views resolve overlay inherit, explicit clear and replacement without mutating saved pages", () => {
  const keys = Array.from({length: 15}, (_, i) => ({...blankKey(), visual: {...defaults, text: String(i)}}));
  const layout = {version: 2, pages: [{id: "main", keys}], overlays: [{id: "shift", keys: {"0": null, "1": {...blankKey(), visual: {...defaults, text: "Override"}}}}]};
  const resolved = pageKeys(layout, "main", "shift");
  assert.equal(resolved[0].visual.text, ""); assert.equal(resolved[1].visual.text, "Override");
  assert.equal(resolved[2].visual.text, "2"); resolved[2].visual.text = "edit";
  assert.equal(keys[2].visual.text, "2"); assert.equal(allKeys(layout).length, 16);
});
test("move inserts, swap exchanges, copy owns its configuration and no operation calls a binding", () => {
  const layout = {version: 1, keys: Array.from({length: 15}, (_, i) => ({...blankKey(), visual: {...defaults, text: String(i)}, press: {action: "light.toggle"}}))};
  assert.deepEqual(rearrange(layout, 0, 4, "move").keys.slice(0, 5).map(k => k.visual.text), ["1", "2", "3", "4", "0"]);
  const swapped = rearrange(layout, 1, 14, "swap");
  assert.equal(swapped.keys[14].visual.text, "1"); assert.equal(swapped.keys[1].visual.text, "14");
  const copy = rearrange(layout, 1, 10, "copy"); copy.keys[10].visual.text = "Changed";
  assert.equal(copy.keys[1].visual.text, "1"); assert.equal(layout.keys[10].visual.text, "10");
  assert.throws(() => rearrange(layout, -1, 3, "swap"));
});
test("state preview inherits artwork and tracks actual on/off/unavailable state", () => {
  const key = {...blankKey(), visual: {...defaults, asset_id: "a".repeat(64)}, state: {entity: {entity_id: "light.desk"}, on: {text: "ON"}, off: {text: "OFF"}, unavailable: {text: "?"}}};
  assert.equal(previewVisual(key, "live", {"light.desk": {state: "on"}}).text, "ON");
  assert.equal(previewVisual(key, "live", {}).text, "?");
  assert.equal(previewVisual(key, "off", {}).asset_id, key.visual.asset_id);
});
test("PNG preview preserves every RGBA byte across all five filters", async () => {
  const raw = Buffer.alloc(72 * 289), expected = Buffer.alloc(72 * 288);
  for (let n = 0; n < expected.length; n++) expected[n] = (n * 17 + Math.floor(n / 288)) % 256;
  for (let y = 0; y < 72; y++) {
    const f = y % 5; raw[y * 289] = f;
    for (let x = 0; x < 288; x++) {
      const n = y * 288 + x, a = x >= 4 ? expected[n - 4] : 0, b = y ? expected[n - 288] : 0, c = y && x >= 4 ? expected[n - 292] : 0;
      const p = a + b - c, pa = Math.abs(p - a), pb = Math.abs(p - b), pc = Math.abs(p - c);
      raw[y * 289 + x + 1] = expected[n] - [0, a, b, Math.floor((a + b) / 2), pa <= pb && pa <= pc ? a : pb <= pc ? b : c][f];
    }
  }
  const chunk = (name, data) => {const output = Buffer.alloc(data.length + 12); output.writeUInt32BE(data.length); output.write(name, 4); data.copy(output, 8); return output;};
  const header = Buffer.from([0, 0, 0, 72, 0, 0, 0, 72, 8, 6, 0, 0, 0]);
  const png = Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk("IHDR", header), chunk("IDAT", deflateSync(raw)), chunk("IEND", Buffer.alloc(0))]);
  const decoded = await decodeArtwork(png);
  assert.deepEqual(Buffer.from(decoded.data), expected);
  await assert.rejects(decodeArtwork(png.slice(0, -1)));
  await assert.rejects(decodeArtwork(Buffer.alloc(32769)));
});
