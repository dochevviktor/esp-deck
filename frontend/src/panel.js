import {renderPreview} from "./preview.js";
import {blankKey, defaults, positioning, rearrange, previewVisual, pageKeys, allKeys} from "./layout.js";
import {decodeArtwork} from "./png.js";

const fonts = ESP_DECK_FONTS;
const escape = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
const entityId = ref => typeof ref === "string" ? ref : ref?.entity_id || "";
const messages = {
  draft_conflict: "This draft changed in another window. Export your edits or reload the saved draft before saving again.",
  artwork_busy: "The artwork queue is full. Try again shortly.", artwork_library_full: "The artwork library is full. Remove unused artwork in Library settings.",
  artwork_in_use: "This artwork is saved in a draft, applied layout or backup, or is still being fetched. Remove those references and wait two minutes before deleting.",
  invalid_image: "This file is damaged or unsupported. Choose a valid PNG or JPEG.", animated_image: "Animated images are not supported. Choose a still PNG or JPEG.",
  upload_too_large: "Choose an image smaller than 10 MiB.", image_dimensions_exceeded: "Images can be up to 4096 × 4096 pixels.",
  invalid_text: "Labels can contain up to 48 characters and 96 UTF-8 bytes.", artwork_not_found: "The artwork is missing from this deck’s library. Upload it again before applying.",
  entry_not_loaded: "This deck is not loaded. Open integration settings to repair its connection.",
  artwork_origin_required: "Set the Home Assistant artwork address in Library settings. It must match an origin allowed by the device firmware.",
};
const styles = `
:host{display:block;height:100%;overflow:auto;background:var(--primary-background-color,#f6f7f9);color:var(--primary-text-color,#17202a);font:14px system-ui}
*{box-sizing:border-box}button,input,select,textarea{font:inherit;color:inherit}button,select,input,textarea{border:1px solid var(--divider-color,#d4d9df);border-radius:8px;background:var(--card-background-color,#fff);padding:10px;min-height:44px}button{cursor:pointer}button:hover{border-color:var(--primary-color,#007d91)}button:focus-visible,input:focus-visible,select:focus-visible{outline:3px solid var(--primary-color,#007d91);outline-offset:2px}button:disabled{opacity:.5;cursor:default}.primary{background:var(--primary-color,#007d91);color:var(--text-primary-color,#fff);border-color:transparent}a{color:var(--primary-color,#007d91)}header{display:flex;align-items:center;gap:14px;padding:18px 24px;background:var(--card-background-color,#fff);border-bottom:1px solid var(--divider-color,#d4d9df)}h1{font-size:21px;margin:0}h2{font-size:17px;margin:0 0 16px}h3{font-size:14px;margin:14px 0 8px}p{line-height:1.5}.muted,small{color:var(--secondary-text-color,#66717e)}main{max-width:1250px;margin:auto;padding:24px}.toolbar,.row{display:flex;gap:10px;flex-wrap:wrap;align-items:center}.toolbar{margin-bottom:18px}.toolbar .spacer{flex:1}.pill{padding:6px 10px;border-radius:20px;background:var(--secondary-background-color,#e8eef0)}.workspace{display:grid;grid-template-columns:minmax(370px,1.1fr) minmax(320px,1fr);gap:24px;align-items:start}.card{padding:22px;background:var(--card-background-color,#fff);border:1px solid var(--divider-color,#d4d9df);border-radius:14px}.deck{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:12px;background:#171b22;padding:20px;border-radius:16px;margin:18px 0}.key{padding:7px;aspect-ratio:1;min-width:0;min-height:0;background:#252b35;border:2px solid #424955;border-radius:11px;position:relative}.key[aria-pressed=true]{border-color:#4ed5e3;box-shadow:0 0 0 2px #4ed5e330}.key canvas{display:block;width:100%;height:100%;border-radius:4px;image-rendering:pixelated}.key small{position:absolute;right:2px;bottom:0;color:white;background:#171b22b0;border-radius:3px;font-size:10px;padding:0 3px}.tabs{display:flex;gap:4px;border-bottom:1px solid var(--divider-color,#d4d9df);margin-bottom:18px}.tabs button{flex:1;border:none;border-radius:0}.tabs [aria-selected=true]{color:var(--primary-color,#007d91);border-bottom:3px solid currentColor}label{display:flex;flex-direction:column;gap:6px;margin-bottom:14px}label input, label select, label textarea{width:100%}.row label{flex:1;min-width:90px}input[type=color]{padding:4px}.notice{padding:12px 16px;border-left:3px solid var(--primary-color,#007d91);background:var(--secondary-background-color,#e8eef0);margin:12px 0;line-height:1.5}.error{border-color:#ce4848}#notice:empty{display:none}.large-preview{width:144px;height:144px;image-rendering:pixelated;border:1px solid var(--divider-color);border-radius:8px}.preview-row{display:flex;gap:16px;align-items:center;margin-bottom:18px}details{border-top:1px solid var(--divider-color,#d4d9df);padding-top:14px;margin-top:18px}summary{cursor:pointer;padding:6px 0 14px}.library{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;max-height:300px;overflow:auto}.asset{padding:5px}.asset canvas{display:block;width:100%;aspect-ratio:1;image-rendering:pixelated}.asset[aria-pressed=true]{border:2px solid var(--primary-color,#007d91)}.upload input{border-style:dashed}textarea{resize:vertical}#status-text{line-height:1.5}#deck-choice{max-width:350px}.keyops{margin:16px 0}.keyops select{width:95px}.keyops button{flex:1}#loading{padding:20px}.badge{font-size:12px}.crop{margin:16px 0;padding:12px;background:var(--secondary-background-color,#eef2f3);border-radius:8px}
@media(max-width:850px){main{padding:14px}.workspace{grid-template-columns:1fr}.deck{gap:8px;padding:14px}.card{padding:16px}header{padding:12px}.toolbar{gap:8px}.toolbar .spacer{display:none}#deck-choice{max-width:180px}}
`;

class ESPDeckPanel extends HTMLElement {
  constructor() {
    super(); this.attachShadow({mode: "open"}); this.selected = 0; this.tab = "binding";
    this.variant = "base"; this.history = []; this.images = new Map(); this.previewEpoch = 0; this.busy = false;
    this.onLeave = event => {if (this.dirty) {event.preventDefault(); event.returnValue = "";}};
  }
  set hass(value) {this._hass = value; if (this.isConnected && !this.started) this.start();}
  get hass() {return this._hass;}
  connectedCallback() {window.addEventListener("beforeunload", this.onLeave); if (this.hass && !this.started) this.start();}
  disconnectedCallback() {clearInterval(this.timer); window.removeEventListener("beforeunload", this.onLeave); this.started = false; this.previewEpoch++;}
  $(selector) {return this.shadowRoot.querySelector(selector);}
  $$(selector) {return [...this.shadowRoot.querySelectorAll(selector)];}
  async start() {
    this.started = true;
    this.shadowRoot.innerHTML = `<style>${styles}</style><header><ha-menu-button></ha-menu-button><h1>ESP Deck</h1></header><main><div id="loading">Loading your decks…</div></main>`;
    this.$("ha-menu-button").hass = this.hass;
    try {
      this.entries = await this.hass.callWS({type: "esp_deck/entries"});
      if (!this.isConnected) return;
      if (!this.entries.length) {this.$("#loading").innerHTML = 'Add ESP Deck in <a href="/config/integrations">Devices & services</a> to start editing.'; return;}
      this.entry = this.entry || this.entries.find(e => e.loaded)?.entry_id || this.entries[0].entry_id;
      await this.load();
      this.timer = setInterval(() => this.poll(), 2000);
    } catch (error) {this.$("#loading").textContent = messages[error.code] || "Could not load ESP Deck. An administrator account and a loaded integration are required.";}
  }
  command(operation, parameters = {}) {return this.hass.callWS({type: "esp_deck/command", entry_id: this.entry, operation, parameters});}
  async load() {
    const [record, library, status] = await Promise.all([this.command("get_layout"), this.command("artwork_list"), this.command("status")]);
    this.record = record; this.layout = structuredClone(record.draft); this.library = library; this.status = status;
    this.history = []; this.dirty = false; this.images.clear(); this.render();
  }
  async poll() {
    if (this.busy || !this.record || !this.isConnected) return;
    try {this.status = await this.command("status"); this.updateStatus(); this.draw();} catch {this.$("#status-text").textContent = "Connection lost. Your unsaved edits remain in this window.";}
  }
  async run(action) {
    if (this.busy) return;
    this.busy = true; this.updateStatus(); this.notice("");
    try {await action();} catch (error) {this.notice(messages[error.code || error.message] || `Could not finish: ${error.code || error.message || "connection error"}`, true);}
    finally {this.busy = false; this.updateStatus();}
  }
  notice(text, error = false) {if (this.$("#notice")) {this.$("#notice").textContent = text; this.$("#notice").className = `notice${error ? " error" : ""}`;}}
  remember() {this.history.push(structuredClone(this.layout)); if (this.history.length > 30) this.history.shift();}
  edit(callback, full = false) {
    this.remember(); const previous = this.layout; callback(this.layout.keys[this.selected]);
    if (previous === this.layout && this.editOverlay && this.layout.version === 2) this.layout.overlays.find(p => p.id === this.editOverlay).keys[this.selected] = structuredClone(this.layout.keys[this.selected]);
    this.dirty = true; if (full) this.render(); else {this.updateStatus(); this.draw();}
  }
  bindKeys() {
    if (this.layout.version !== 2) {this.editPage = this.editOverlay = null; return;}
    if (!this.layout.pages.some(p => p.id === this.editPage)) this.editPage = this.layout.default_page;
    if (!this.layout.overlays.some(p => p.id === this.editOverlay)) this.editOverlay = null;
    Object.defineProperty(this.layout, "keys", {value: pageKeys(this.layout, this.editPage, this.editOverlay), configurable: true, writable: true});
  }
  async save(apply) {
    if (this.dirty) {
      await this.command("save_layout", {layout: this.layout, expected_revision: this.record.draft_revision});
      this.record.draft_revision++; this.record.draft = structuredClone(this.layout); this.dirty = false;
    }
    if (apply) await this.command("apply_layout", {expected_revision: this.record.draft_revision});
    this.status = await this.command("status");
    this.record.applied_revision = this.status.applied_revision;
    if (apply) this.record.applied = structuredClone(this.record.draft);
    if (this.layout.version === 2) this.render();
    this.notice(apply ? "Layout applied. The backend is synchronizing your deck." : "Draft saved. Apply when you’re ready to update the deck.");
  }
  updateStatus() {
    if (!this.$("#draft-status")) return;
    this.$("#draft-status").textContent = this.dirty ? "Unsaved edits" : this.record.draft_revision !== this.status.applied_revision ? "Saved draft · not applied" : "Applied layout";
    const state = this.status?.state || "offline";
    this.$("#connection").textContent = this.busy ? "Working…" : state.replaceAll("_", " ");
    const failure = this.status?.error || this.status?.binding_error || this.status?.tiles?.find(t => t.phase === "failed")?.error;
    this.$("#status-text").textContent = failure ? (messages[failure] || `Deck needs attention: ${failure}. Retry synchronization or open repair settings.`) : state === "ready" ? "Visuals rendered. Physical display readback is unavailable." : "The backend keeps bindings and visuals synchronized when this editor is closed.";
    for (const control of this.$$("button, input, select, textarea")) control.disabled = this.busy;
    this.$("#undo").disabled = this.busy || !this.history.length;
  }
  render() {
    this.bindKeys();
    this.previewEpoch++;
    this.shadowRoot.innerHTML = `<style>${styles}</style>
      <header><ha-menu-button></ha-menu-button><h1>ESP Deck</h1><select id="deck-choice" aria-label="Deck">${this.entries.map(e => `<option value="${escape(e.entry_id)}" ${e.entry_id === this.entry ? "selected" : ""}>${escape(e.title)}</option>`).join("")}</select></header>
      <main><div class="toolbar"><span id="draft-status" class="pill"></span><span id="connection" class="pill"></span><span class="spacer"></span><button id="undo">Undo</button><button id="reload" data-work>Reload saved</button><button id="save" data-work>Save draft</button><button id="apply" data-work class="primary">Apply</button></div>
      <div id="notice" role="status" aria-live="polite"></div><div class="workspace"><section class="card"><h2>Your deck</h2><p class="muted">Select a key to edit. Drag keys to swap, or use the controls below.</p>
      <div class="deck" role="group" aria-label="15 keys, five columns and three rows">${this.layout.keys.map((key, i) => `<button class="key" data-key="${i}" aria-label="Key ${i + 1}" aria-pressed="${i === this.selected}" draggable="true"><canvas width="72" height="72"></canvas><small>${i + 1}</small></button>`).join("")}</div>
      <div class="row keyops"><label>Destination<select id="destination">${this.layout.keys.map((_, i) => `<option value="${i}" ${i === (this.selected + 1) % 15 ? "selected" : ""}>Key ${i + 1}</option>`).join("")}</select></label><button id="move" data-work>Move</button><button id="swap" data-work>Swap</button><button id="copy" data-work>Copy</button><button id="clear" data-work>Clear key</button></div>
      <label>Preview state<select id="preview-state">${["base", "live", "on", "off", "unavailable"].map(v => `<option ${this.variant === v ? "selected" : ""}>${v}</option>`).join("")}</select></label>
      <p id="status-text" class="muted"></p><div class="row"><button id="retry" data-work>Retry synchronization</button><a href="/config/integrations/integration/esp_deck">Repair / integration settings</a></div>
      <details><summary>Library settings & backup</summary><label>Home Assistant address reachable by the deck<input id="origin" value="${escape(this.library.origin)}" placeholder="http://homeassistant.local:8123"></label><p class="muted">v1 firmware must already allow this origin. Changing this address does not provision the device. Plain HTTP artwork should be non-sensitive.</p><div class="row"><button id="set-origin" data-work>Save address</button><button id="revoke" data-work>Revoke download links</button><button id="collect" data-work>Remove unused artwork</button></div><p class="muted">Saved draft, applied and backup artwork is retained. Recent downloads have a two-minute grace period.</p><div class="row"><button id="export">Export draft</button><button id="export-applied">Export applied</button><button id="restore" data-work>Restore backup to draft</button></div><label>Import layout<input type="file" id="import" accept="application/json,.json"></label><p class="muted">Exports contain bindings and artwork hashes, without download credentials or source images. Keep them private. Artwork must be available in this deck’s library when importing.</p></details>
      </section><section class="card" id="editor"></section></div></main>`;
    this.renderPages();
    if (this.status.capabilities?.origin_provisioning) {
      this.$("#set-origin").textContent = "Verify & provision address";
      this.$("#origin").closest("label").nextElementSibling.textContent = "The device tests this address before saving its allowlist. Choose a LAN address the deck can reach, or HTTPS with a trusted certificate.";
    }
    this.$("ha-menu-button").hass = this.hass;
    this.$("#deck-choice").onchange = e => {
      if (this.dirty) {e.target.value = this.entry; this.notice("Save or export your edits before switching decks.", true); return;}
      this.entry = e.target.value; this.run(() => this.load());
    };
    this.$$(".key").forEach(button => {
      button.onclick = () => {this.selected = Number(button.dataset.key); this.render();};
      button.onkeydown = event => {
        const offset = {ArrowLeft: -1, ArrowRight: 1, ArrowUp: -5, ArrowDown: 5}[event.key];
        if (offset) {event.preventDefault(); this.selected = Math.max(0, Math.min(14, this.selected + offset)); this.render(); this.$(`[data-key="${this.selected}"]`).focus();}
      };
      button.ondragstart = event => event.dataTransfer.setData("text/esp-deck-key", button.dataset.key);
      button.ondragover = event => event.preventDefault();
      button.ondrop = event => {event.preventDefault(); const raw = event.dataTransfer.getData("text/esp-deck-key"); if (/^(\d|1[0-4])$/.test(raw)) this.changeOrder(Number(raw), Number(button.dataset.key), "swap");};
    });
    for (const op of ["move", "swap", "copy"]) this.$(`#${op}`).onclick = () => this.changeOrder(this.selected, Number(this.$("#destination").value), op);
    this.$("#clear").onclick = () => this.edit(() => {this.layout.keys[this.selected] = blankKey();}, true);
    this.$("#undo").onclick = () => {if (this.history.length) {this.layout = this.history.pop(); this.dirty = true; this.render();}};
    this.$("#reload").onclick = () => {if (this.dirty) this.notice("Unsaved edits were replaced by the saved draft."); this.run(() => this.load());};
    this.$("#save").onclick = () => this.run(() => this.save(false));
    this.$("#apply").onclick = () => this.run(() => this.save(true));
    this.$("#preview-state").onchange = e => {this.variant = e.target.value; this.draw();};
    this.$("#retry").onclick = () => this.run(async () => {this.status = await this.command("sync");});
    this.$("#set-origin").onclick = () => this.run(async () => {this.library = await this.command("artwork_configure", {origin: this.$("#origin").value}); this.notice(this.status.capabilities?.origin_provisioning ? "Artwork access verified by the device and saved." : "Artwork address saved. Apply or retry to check the device response.");});
    this.$("#revoke").onclick = () => this.run(async () => {this.library = await this.command("artwork_revoke"); this.notice("Previous download links revoked. New links are being sent to the deck.");});
    this.$("#collect").onclick = () => this.run(async () => {if (this.dirty) throw Error("Save your draft before removing unused artwork."); const result = await this.command("artwork_collect"); this.library = await this.command("artwork_list"); this.renderEditor(); this.notice(`Removed ${result.removed_files} unused files.`);});
    this.$("#export").onclick = () => {
      const layout = structuredClone(this.layout);
      for (const key of allKeys(layout)) {
        if (key.state) delete key.state.entity.registry_id;
        for (const edge of ["press", "release"]) for (const ref of key[edge]?.target?.entity_id || []) delete ref.registry_id;
      }
      this.download({format: "esp_deck_layout", version: 1, layout});
    };
    this.$("#export-applied").onclick = () => this.run(async () => this.download(await this.command("export_layout", {which: "applied"})));
    this.$("#restore").onclick = () => this.run(async () => {const document = await this.command("export_layout", {which: "backup"}); this.edit(() => {this.layout = document.layout;}, true); this.notice("Previous applied layout restored to the editor. Save or Apply to keep it.");});
    this.$("#import").onchange = event => this.run(async () => {const file = event.target.files[0]; if (!file) return; if (file.size > 131072) throw Error("Layout is too large"); const document = JSON.parse(await file.text()); await this.command("import_layout", {document, expected_revision: this.record.draft_revision}); await this.load(); this.notice("Layout imported as a saved draft. Apply to activate it.");});
    this.renderEditor(); this.updateStatus(); this.draw();
  }
  changeOrder(from, to, operation) {
    this.remember(); const keys = rearrange({keys: this.layout.keys}, from, to, operation).keys;
    if (this.layout.version === 1) this.layout.keys = keys;
    else if (this.editOverlay) this.layout.overlays.find(p => p.id === this.editOverlay).keys = Object.fromEntries(keys.map((k, i) => [i, k]));
    else this.layout.pages.find(p => p.id === this.editPage).keys = keys;
    this.selected = to; this.dirty = true; this.render();
  }
  renderPages() {
    if (this.status.capabilities?.input_correlation !== "pull_context_v2") return;
    const element = document.createElement("div"); element.className = "row";
    this.$(".deck").before(element);
    if (this.layout.version === 1) {
      element.innerHTML = '<button id="enable-pages">Enable pages & overlays</button>';
      this.$("#enable-pages").onclick = () => {this.remember(); this.layout = {version: 2, default_page: "main", pages: [{id: "main", name: "Main", keys: this.layout.keys}], overlays: []}; this.dirty = true; this.render();};
      return;
    }
    const options = (items, current) => items.map(p => `<option value="${escape(p.id)}" ${p.id === current ? "selected" : ""}>${escape(p.name)}</option>`).join("");
    element.innerHTML = `<label>Edit page<select id="edit-page">${options(this.layout.pages, this.editPage)}</select></label><label>Edit overlay<select id="edit-overlay"><option value="">Base page</option>${options(this.layout.overlays, this.editOverlay)}</select></label><label>Name<input id="page-name" maxlength="48" value="${escape((this.editOverlay ? this.layout.overlays.find(p => p.id === this.editOverlay) : this.layout.pages.find(p => p.id === this.editPage)).name)}"></label><button id="add-page">Add page</button><button id="add-overlay">Add overlay</button><button id="remove-page">Remove selected</button><button id="default-page">Start on this page</button><label>Active page<select id="active-page">${options(this.record.applied?.pages || [], this.status.active_page)}</select></label>${this.editOverlay ? '<button id="inherit-key">Inherit selected key</button><button id="clear-overlay-key">Clear selected key</button>' : ""}`;
    this.$("#edit-page").onchange = e => {this.editPage = e.target.value; this.render();};
    this.$("#edit-overlay").onchange = e => {this.editOverlay = e.target.value; this.render();};
    const mutate = action => {this.remember(); action(); this.dirty = true; this.render();};
    this.$("#page-name").onchange = e => mutate(() => {(this.editOverlay ? this.layout.overlays.find(p => p.id === this.editOverlay) : this.layout.pages.find(p => p.id === this.editPage)).name = e.target.value;});
    for (const kind of ["page", "overlay"]) this.$(`#add-${kind}`).onclick = () => {
      const items = this.layout[kind === "page" ? "pages" : "overlays"], cap = kind === "page" ? 8 : 4;
      if (items.length >= cap) {this.notice(`Up to ${cap} ${kind}s are supported.`, true); return;}
      mutate(() => {let n = 1; while (items.some(p => p.id === `${kind}_${n}`)) n++; const id = `${kind}_${n}`;
        items.push({id, name: `${kind === "page" ? "Page" : "Overlay"} ${n}`, keys: kind === "page" ? Array.from({length: 15}, blankKey) : {}});
        if (kind === "page") {this.editPage = id; this.editOverlay = null;} else this.editOverlay = id;
      });
    };
    this.$("#remove-page").onclick = () => {
      if (!this.editOverlay && this.layout.pages.length === 1) {this.notice("Keep at least one page.", true); return;}
      const id = this.editOverlay || this.editPage;
      if (allKeys(this.layout).some(k => k.navigation?.target === id)) {this.notice("Remove navigation bindings to this page or overlay first.", true); return;}
      mutate(() => {const kind = this.editOverlay ? "overlays" : "pages"; this.layout[kind] = this.layout[kind].filter(p => p.id !== id); if (this.layout.default_page === id) this.layout.default_page = this.layout.pages[0].id;});
    };
    this.$("#default-page").onclick = () => mutate(() => {this.layout.default_page = this.editPage;});
    this.$("#active-page").onchange = e => this.run(async () => {this.status = await this.command("select_page", {page: e.target.value});});
    if (this.editOverlay) {
      this.$("#inherit-key").onclick = () => mutate(() => {delete this.layout.overlays.find(p => p.id === this.editOverlay).keys[this.selected];});
      this.$("#clear-overlay-key").onclick = () => mutate(() => {this.layout.overlays.find(p => p.id === this.editOverlay).keys[this.selected] = null;});
    }
  }
  download(document) {const url = URL.createObjectURL(new Blob([JSON.stringify(document, null, 2)], {type: "application/json"})); const link = documentElement("a"); link.href = url; link.download = "esp-deck-layout.json"; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);}
  entities(domains) {return Object.values(this.hass.states).filter(s => !domains || domains.includes(s.entity_id.split(".")[0])).sort((a, b) => a.entity_id.localeCompare(b.entity_id));}
  entityOptions(current, domains) {const entries = this.entities(domains); if (current && !entries.some(s => s.entity_id === current)) entries.unshift({entity_id: current, attributes: {friendly_name: "Missing entity"}}); return `<option value="">None</option>${entries.map(s => `<option value="${escape(s.entity_id)}" ${s.entity_id === current ? "selected" : ""}>${escape(s.attributes.friendly_name || s.entity_id)} · ${escape(s.entity_id)}</option>`).join("")}`;}
  renderEditor() {
    const key = this.layout.keys[this.selected];
    this.$("#editor").innerHTML = `<h2>Key ${this.selected + 1}</h2><div class="preview-row"><canvas id="large-preview" class="large-preview" width="72" height="72"></canvas><p class="muted">Preview only.<br>Selecting a key never runs its action.<br><small>Bundled glyphs · fixed bottom label</small></p></div><div class="tabs" role="tablist">${["binding", "appearance", "state rules"].map(tab => `<button role="tab" aria-selected="${this.tab === tab}" data-tab="${tab}">${tab[0].toUpperCase() + tab.slice(1)}</button>`).join("")}</div><div id="fields"></div>`;
    this.$$('[data-tab]').forEach(button => button.onclick = () => {this.tab = button.dataset.tab; this.renderEditor(); this.draw();});
    this.$(".preview-row small").textContent = this.status.capabilities?.positioning ? "Bundled glyphs · bounded label position" : "Bundled glyphs · fixed bottom label";
    if (this.tab === "binding") this.renderBinding(key);
    if (this.tab === "appearance") this.renderAppearance(key);
    if (this.tab === "state rules") this.renderRules(key);
    this.draw();
  }
  renderBinding(key) {
    const current = entityId(key.press?.target?.entity_id?.[0]);
    this.$("#fields").innerHTML = `<label>Entity preset<select id="preset-entity">${this.entityOptions(current, ["light", "switch", "input_boolean", "script", "scene"])}</select></label><button id="preset" class="primary" data-work>Use preset</button><p class="muted">Lights and switches get toggle actions and on/off/unavailable colors. Scripts and scenes run on press. A preset replaces this key’s current configuration.</p><label>Binding mode<select id="mode"><option value="managed" ${key.mode === "managed" ? "selected" : ""}>Managed actions</option><option value="automation" ${key.mode === "automation" ? "selected" : ""}>Home Assistant automation</option></select></label><div id="edges"></div>`;
    this.$("#preset").onclick = () => this.run(async () => {const id = this.$("#preset-entity").value; if (!id) throw Error("Select an entity first"); const label = key.visual.text || (this.hass.states[id]?.attributes.friendly_name || id.split(".")[1]).slice(0, 24); const result = await this.command("preset", {entity_id: id, label}); this.edit(() => {this.layout.keys[this.selected] = result.key;}, true);});
    this.$("#mode").onchange = event => this.edit(k => {k.mode = event.target.value; if (k.mode === "automation") {k.press = null; k.release = null; delete k.navigation;}}, true);
    if (this.layout.version === 2 && this.status.capabilities?.input_correlation === "pull_context_v2") {
      const label = document.createElement("label"); label.textContent = "Navigation / modifier";
      const select = document.createElement("select"); select.id = "navigation";
      select.innerHTML = '<option value="">Normal binding</option>' + ["page", "overlay", "momentary"].flatMap(kind => (kind === "page" ? this.layout.pages : this.layout.overlays).map(p => `<option value="${kind}:${escape(p.id)}">${kind === "momentary" ? "Hold overlay" : kind === "overlay" ? "Toggle overlay" : "Go to page"} · ${escape(p.name)}</option>`)).join("");
      select.value = key.navigation ? `${key.navigation.kind}:${key.navigation.target}` : "";
      label.append(select); this.$("#edges").before(label);
      select.onchange = e => this.edit(k => {if (!e.target.value) delete k.navigation; else {const [kind, target] = e.target.value.split(":"); k.navigation = {kind, target}; k.mode = "managed"; k.press = k.release = null;}}, true);
      if (key.navigation) {this.$("#edges").textContent = "This key controls pages or overlays. A momentary overlay ends when this accepted press is released."; return;}
    }
    if (key.mode === "automation") {this.$("#edges").innerHTML = `<p>Use the <code>esp_deck_key</code> event in an <a href="/config/automation/dashboard">HA automation</a>. Filter entry_id <code>${escape(this.entry)}</code>, key <code>${this.selected}</code>, and edge <code>press</code> or <code>release</code>. Managed actions are disabled for this key.</p>`; return;}
    this.$("#edges").innerHTML = ["press", "release"].map(edge => {
      const binding = key[edge]; const targets = binding?.target?.entity_id || [];
      return `<details ${edge === "press" ? "open" : ""}><summary>${edge === "press" ? "Press action" : "Release action (optional)"}</summary><label>Target entity<select id="${edge}-entity">${this.entityOptions(entityId(targets[0]))}</select></label><label>Action<select id="${edge}-action"><option value="">None</option>${Object.entries(this.hass.services).flatMap(([domain, services]) => Object.keys(services).filter(s => domain !== "esp_deck").map(service => `${domain}.${service}`)).sort().map(action => `<option ${binding?.action === action ? "selected" : ""}>${escape(action)}</option>`).join("")}</select></label><details><summary>Advanced action data (JSON)</summary><textarea id="${edge}-data" rows="3" aria-label="${edge} action data">${escape(JSON.stringify(binding?.data || {}, null, 2))}</textarea><p class="muted">Use <a href="/config/script/dashboard">HA scripts</a> for conditions, delays and multiple actions.${targets.length > 1 ? " This binding has multiple targets; choosing an entity replaces the target list." : ""}</p></details></details>`;
    }).join("");
    for (const edge of ["press", "release"]) {
      const update = changedTarget => {
        try {const target = this.$(`#${edge}-entity`).value, action = this.$(`#${edge}-action`).value, data = JSON.parse(this.$(`#${edge}-data`).value); this.edit(k => {k[edge] = action ? {action, data, target: {entity_id: changedTarget ? (target ? [{entity_id: target}] : []) : (k[edge]?.target?.entity_id || (target ? [{entity_id: target}] : []))}} : null;});} catch {this.notice("Action data must be valid JSON.", true);}
      };
      this.$(`#${edge}-entity`).onchange = () => update(true);
      this.$(`#${edge}-action`).onchange = () => update(false);
      this.$(`#${edge}-data`).onchange = () => update(false);
    }
  }
  appearanceFields(visual, prefix) {
    return `<label>Label<textarea id="${prefix}text" maxlength="48" rows="2">${escape(visual.text)}</textarea></label><div class="row"><label>Font size<select id="${prefix}font">${[12, 16, 20].map(n => `<option ${Number(visual.font) === n ? "selected" : ""}>${n}</option>`).join("")}</select></label><label>Image fit<select id="${prefix}fit">${["contain", "crop"].map(v => `<option ${visual.fit === v ? "selected" : ""}>${v}</option>`).join("")}</select></label></div><div class="row">${[["text_color", "Text color"], ["outline_color", "Outline color"], ["background_color", "Background"]].map(([field, title]) => `<label>${title}<input type="color" id="${prefix}${field}" value="${escape(visual[field])}"></label>`).join("")}</div>`;
  }
  bindAppearance(prefix, apply) {
    for (const field of ["text", "font", "fit", "text_color", "outline_color", "background_color"]) this.$(`#${prefix}${field}`).onchange = event => this.edit(key => apply(key, field, field === "font" ? Number(event.target.value) : event.target.value));
    if (this.status.capabilities?.positioning) {
      const key = this.layout.keys[this.selected];
      const appearance = {...positioning, ...key.visual, ...(prefix === "s-" ? key.state[this.ruleVariant] : {})};
      const box = document.createElement("div"); box.className = "row";
      box.innerHTML = [["text_x", "Label left", 0, 48], ["text_y", "Label top", 0, 71], ["text_width", "Label width", 24, 72], ["text_height", "Label height", 1, 72]].map(([field, name, min, max]) => `<label>${name}<input id="${prefix}${field}" type="number" min="${min}" max="${max}" value="${appearance[field]}"></label>`).join("") + [["text_align", ["Left", "Center", "Right"]], ["text_valign", ["Top", "Middle", "Bottom"]]].map(([field, labels]) => `<label>${field === "text_align" ? "Horizontal alignment" : "Vertical alignment"}<select id="${prefix}${field}">${labels.map((name, i) => `<option value="${i}" ${appearance[field] === i ? "selected" : ""}>${name}</option>`).join("")}</select></label>`).join("");
      this.$(`#${prefix}background_color`).closest(".row").after(box);
      for (const field of Object.keys(positioning)) this.$(`#${prefix}${field}`).onchange = e => this.edit(k => apply(k, field, Number(e.target.value)));
    }
  }
  renderAppearance(key) {
    this.$("#fields").innerHTML = this.appearanceFields({...defaults, ...key.visual}, "v-") + `<label class="upload">Upload artwork<input id="upload" type="file" accept="image/png,image/jpeg"></label><p class="muted">PNG or JPEG · up to 10 MiB / 4096 × 4096. Artwork is stored as 72 × 72 PNG; labels stay editable on the device.</p><div class="row"><button id="remove-image">Remove image</button><button id="delete-image" data-work>Delete selected artwork</button></div><div id="crop-fields"></div><h3>Artwork library</h3><div class="library">${this.library.variants.map(asset => `<button class="asset" data-asset="${asset.asset_id}" aria-label="Artwork ${asset.asset_id.slice(0, 8)}" aria-pressed="${key.visual.asset_id === asset.asset_id}"><canvas width="72" height="72"></canvas></button>`).join("")}</div>${key.visual.image_url ? '<p class="notice">This tile uses an existing external image URL. The editor does not fetch arbitrary external images. Upload artwork for an exact preview.</p>' : ""}`;
    this.bindAppearance("v-", (k, field, value) => k.visual[field] = value);
    this.$("#upload").onchange = event => {const file = event.target.files[0]; if (file) this.run(async () => {
      if (file.size > 10 * 1024 * 1024) throw Error("upload_too_large");
      const result = await this.hass.fetchWithAuth(`/api/esp_deck/upload/${encodeURIComponent(this.entry)}`, {method: "POST", headers: {"Content-Type": file.type}, body: file});
      const data = await result.json(); if (!result.ok) throw Error(data.error);
      this.library = await this.command("artwork_list"); this.selectAsset(data.asset_id);
    });};
    this.$("#remove-image").onclick = () => this.edit(k => Object.assign(k.visual, {asset_id: "", image_url: "", image_revision: ""}), true);
    this.$("#delete-image").onclick = () => this.run(async () => {if (!key.visual.asset_id) throw Error("Select artwork first"); await this.command("artwork_delete", {asset_id: key.visual.asset_id}); this.library = await this.command("artwork_list"); this.edit(k => Object.assign(k.visual, {asset_id: "", image_url: "", image_revision: ""}), true);});
    this.$$("[data-asset]").forEach(button => button.onclick = () => this.selectAsset(button.dataset.asset));
    if (constAsset(key, this.library)) {
      const asset = constAsset(key, this.library), t = asset.transform;
      this.$("#crop-fields").innerHTML = `<div class="crop"><h3>Crop & fit</h3><label>Source fit<select id="crop-fit"><option ${t.fit === "contain" ? "selected" : ""}>contain</option><option ${t.fit === "crop" ? "selected" : ""}>crop</option></select></label><label>Zoom<input id="crop-zoom" type="range" min="1" max="4" step="0.05" value="${t.zoom}"></label><label>Horizontal offset<input id="crop-x" type="range" min="-1" max="1" step="0.05" value="${t.x}"></label><label>Vertical offset<input id="crop-y" type="range" min="-1" max="1" step="0.05" value="${t.y}"></label><button id="crop-update" data-work>Update crop preview</button></div>`;
      this.$("#crop-update").onclick = () => this.run(async () => {const transform = {fit: this.$("#crop-fit").value, zoom: Number(this.$("#crop-zoom").value), x: Number(this.$("#crop-x").value), y: Number(this.$("#crop-y").value)}; const result = await this.command("artwork_variant", {source_id: asset.source_id, transform}); this.library = await this.command("artwork_list"); this.selectAsset(result.asset_id);});
    }
  }
  selectAsset(asset_id) {this.edit(k => Object.assign(k.visual, {asset_id, image_url: "", image_revision: ""}), true);}
  renderRules(key) {
    this.ruleVariant ||= "on";
    this.$("#fields").innerHTML = `<label>State source<select id="state-entity">${this.entityOptions(entityId(key.state?.entity))}</select></label><p class="muted">Rules follow the actual entity state. Unknown states use “unavailable”. Unchanged artwork is reused when only the label changes.</p>${key.state ? `<label>Edit state<select id="rule-variant">${["on", "off", "unavailable"].map(v => `<option ${this.ruleVariant === v ? "selected" : ""}>${v}</option>`).join("")}</select></label>${this.appearanceFields({...defaults, ...key.visual, ...key.state[this.ruleVariant]}, "s-")}<label>State artwork<select id="state-art"><option value="inherit">Use base artwork</option><option value="clear">No image</option>${this.library.variants.map(v => `<option value="${v.asset_id}">${v.asset_id.slice(0, 8)}</option>`).join("")}</select></label><button id="reset-rule">Reset this state to base appearance</button>` : ""}`;
    this.$("#state-entity").onchange = event => this.edit(k => {k.state = event.target.value ? {entity: {entity_id: event.target.value}, on: {}, off: {}, unavailable: {}} : null;}, true);
    if (!key.state) return;
    this.$("#rule-variant").onchange = event => {this.ruleVariant = event.target.value; this.variant = this.ruleVariant; this.render();};
    this.bindAppearance("s-", (k, field, value) => {k.state[this.ruleVariant][field] = value; this.variant = this.ruleVariant; this.$("#preview-state").value = this.variant;});
    const patch = key.state[this.ruleVariant];
    this.$("#state-art").value = patch.asset_id || (patch.image_url === "" ? "clear" : "inherit");
    this.$("#state-art").onchange = event => this.edit(k => {const v = k.state[this.ruleVariant]; delete v.asset_id; delete v.image_url; delete v.image_revision; if (event.target.value !== "inherit") Object.assign(v, {asset_id: event.target.value === "clear" ? "" : event.target.value, image_url: "", image_revision: ""}); this.variant = this.ruleVariant;}, true);
    this.$("#reset-rule").onclick = () => this.edit(k => {k.state[this.ruleVariant] = {};}, true);
  }
  async pixels(asset_id) {
    if (!asset_id) return null;
    if (!this.images.has(asset_id)) {
      const entry = this.entry;
      this.images.set(asset_id, (async () => {
        const response = await this.hass.fetchWithAuth(`/api/esp_deck/preview/${encodeURIComponent(entry)}/${asset_id}`);
        if (!response.ok) throw Error("Artwork preview unavailable");
        return decodeArtwork(new Uint8Array(await response.arrayBuffer()));
      })());
    }
    return this.images.get(asset_id);
  }
  async draw() {
    if (!this.layout) return;
    const epoch = ++this.previewEpoch;
    const targets = this.$$(".key").map(button => [button.querySelector("canvas"), previewVisual(this.layout.keys[Number(button.dataset.key)], this.variant, this.hass.states)]);
    if (this.$("#large-preview")) targets.push([this.$("#large-preview"), previewVisual(this.layout.keys[this.selected], this.variant, this.hass.states)]);
    this.$$("[data-asset]").forEach(button => targets.push([button.querySelector("canvas"), {...defaults, asset_id: button.dataset.asset}]));
    await Promise.all(targets.map(async ([canvas, visual]) => {
      try {const pixels = await this.pixels(visual.asset_id); if (epoch === this.previewEpoch && canvas.isConnected) canvas.getContext("2d").putImageData(new ImageData(renderPreview(visual, pixels, fonts), 72, 72), 0, 0);} catch {if (epoch === this.previewEpoch) this.notice("Artwork preview unavailable. Reload the library or upload the missing artwork.", true);}
    }));
  }
}
const constAsset = (key, library) => library.variants.find(a => a.asset_id === key.visual.asset_id);
const documentElement = name => document.createElement(name);
if (!customElements.get("esp-deck-panel")) customElements.define("esp-deck-panel", ESPDeckPanel);
