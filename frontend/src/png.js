// Canonical server PNG only: RGBA8, 72 x 72, non-interlaced, <=32 KiB.
// Reading the RGBA bytes avoids browser canvas premultiplication/color conversion.
export async function decodeArtwork(bytes) {
  const fail = () => {throw Error("Invalid normalized artwork");};
  if (bytes.length > 32768 || bytes.length < 45 || [...bytes.slice(0, 8)].join() !== "137,80,78,71,13,10,26,10") fail();
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const chunks = []; let header = false, end = false;
  for (let at = 8, count = 0; at < bytes.length; count++) {
    if (count > 256 || at + 12 > bytes.length) fail();
    const size = view.getUint32(at), kind = String.fromCharCode(...bytes.slice(at + 4, at + 8));
    if (at + size + 12 > bytes.length) fail();
    if (kind === "IHDR") {
      if (header || at !== 8 || size !== 13 || view.getUint32(at + 8) !== 72 || view.getUint32(at + 12) !== 72 || [...bytes.slice(at + 16, at + 21)].join() !== "8,6,0,0,0") fail();
      header = true;
    } else if (kind === "IDAT" && header && !end) chunks.push(bytes.slice(at + 8, at + 8 + size));
    else if (kind === "IEND" && size === 0 && at + 12 === bytes.length) end = true;
    else fail();
    at += size + 12;
  }
  if (!header || !end || !chunks.length) fail();
  const reader = new Blob(chunks).stream().pipeThrough(new DecompressionStream("deflate")).getReader();
  const raw = new Uint8Array(72 * 289); let length = 0;
  try {for (;;) {const {done, value} = await reader.read(); if (done) break; if (length + value.length > raw.length) fail(); raw.set(value, length); length += value.length;}}
  finally {await reader.cancel();}
  if (length !== raw.length) fail();
  const pixels = new Uint8Array(72 * 288);
  for (let y = 0; y < 72; y++) {
    const filter = raw[y * 289]; if (filter > 4) fail();
    for (let x = 0; x < 288; x++) {
      const at = y * 288 + x, a = x >= 4 ? pixels[at - 4] : 0, b = y ? pixels[at - 288] : 0, c = y && x >= 4 ? pixels[at - 292] : 0;
      const p = a + b - c, pa = Math.abs(p - a), pb = Math.abs(p - b), pc = Math.abs(p - c);
      const predictor = [0, a, b, Math.floor((a + b) / 2), pa <= pb && pa <= pc ? a : pb <= pc ? b : c][filter];
      pixels[at] = raw[y * 289 + x + 1] + predictor;
    }
  }
  return {data: pixels, width: 72, height: 72};
}
