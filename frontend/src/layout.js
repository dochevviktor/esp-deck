export const defaults = {image_url: "", image_revision: "", asset_id: "", text: "", font: 16,
  text_color: "#FFFFFF", outline_color: "#000000", background_color: "#000000", fit: "contain"};
export const blankKey = () => ({visual: {...defaults}, mode: "managed", press: null, release: null, state: null});
export function rearrange(layout, from, to, operation) {
  if (![from, to].every(n => Number.isInteger(n) && n >= 0 && n < 15)) throw Error("Invalid key");
  const next = structuredClone(layout);
  if (from === to) return next;
  if (operation === "swap") [next.keys[from], next.keys[to]] = [next.keys[to], next.keys[from]];
  else if (operation === "copy") next.keys[to] = structuredClone(next.keys[from]);
  else if (operation === "move") next.keys.splice(to, 0, ...next.keys.splice(from, 1));
  else throw Error("Unknown operation");
  return next;
}
export function previewVisual(key, variant, states) {
  if (variant === "live" && key.state) {
    const name = typeof key.state.entity === "string" ? key.state.entity : key.state.entity.entity_id;
    const state = states[name]?.state;
    variant = ["on", "off"].includes(state) ? state : "unavailable";
  }
  return {...defaults, ...key.visual, ...(key.state?.[variant] || {})};
}
