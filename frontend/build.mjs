// No runtime CDN dependencies. Compile the editor and reuse the firmware glyphs.
import {build} from "esbuild";
import {readFile, writeFile, mkdir} from "node:fs/promises";
import {fileURLToPath} from "node:url";
import path from "node:path";
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const source = await readFile(path.join(root, "components/stream_deck/render_font_data.cpp"), "utf8");
const fonts = {};
for (const size of [12, 16, 20]) {
  const bits = [...source.match(new RegExp(`BITS_${size}\\[\\] = \\{([\\s\\S]*?)\\};`))[1].matchAll(/0x([a-f0-9]{2})/g)].map(m => parseInt(m[1], 16));
  const glyphs = [...source.match(new RegExp(`GLYPHS_${size}\\[\\] = \\{([\\s\\S]*?)\\};`))[1].matchAll(/\{([^}]+)\}/g)].map(m => m[1].split(",").map(Number));
  const height = Number(source.match(new RegExp(`const Font FONT_${size}[^\\n]+, ${size}, (\\d+)\\}`))[1]);
  fonts[size] = {bits, glyphs, height};
}
const result = await build({absWorkingDir: path.join(root, "frontend"), entryPoints: ["src/panel.js"],
  bundle: true, format: "esm", target: "es2022", minify: true, legalComments: "inline", write: false,
  define: {ESP_DECK_FONTS: JSON.stringify(fonts)}});
const artifacts = new Map([
  ["esp-deck.js", result.outputFiles[0].contents],
  ["LICENSE-DejaVu.txt", Buffer.from((await readFile(path.join(root, "assets/fonts/LICENSE-DejaVu.txt"), "utf8")).replace(/[ \t]+$/gm, ""))],
]);
const dest = path.join(root, "custom_components/esp_deck/frontend");
await mkdir(dest, {recursive: true});
for (const [name, bytes] of artifacts) {
  const target = path.join(dest, name);
  if (process.argv.includes("--check")) {
    if (!Buffer.from(await readFile(target)).equals(Buffer.from(bytes))) throw Error(`Stale bundled artifact: ${name}`);
  } else await writeFile(target, bytes);
}
console.log(process.argv.includes("--check") ? "Editor bundle verified" : "Editor bundled");
