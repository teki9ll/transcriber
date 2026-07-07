(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const els = {
    talk: $("talk"),
    ringFg: $("ring-fg"),
    status: $("status"),
    connDot: $("conn-dot"),
    deviceChip: $("device-chip"),
    modelSelect: $("model-select"),
    resultCard: $("result-card"),
    resultText: $("result-text"),
    copiedBadge: $("copied-badge"),
    metaBadge: $("meta-badge"),
    copyAgain: $("copy-again"),
    history: $("history"),
    clearHistory: $("clear-history"),
    backendInfo: $("backend-info"),
    hotkeyBtn: $("hotkey-btn"),
    hotkeyLabel: $("hotkey-label"),
    hotkeyToggle: $("hotkey-toggle"),
    autopasteToggle: $("autopaste-toggle"),
    pastedBadge: $("pasted-badge"),
  };

  const RING_C = 2 * Math.PI * 92;
  els.ringFg.style.strokeDasharray = RING_C;

  let ws = null;
  let talking = false;
  let serverState = "connecting";
  let peak = 0.0001;

  // hotkey UI state
  let capturing = false;
  let hkState = { enabled: false, key: null, available: false };

  function send(obj) {
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(obj));
  }

  // ---------- level meter ----------
  function setRing(level, color) {
    els.ringFg.style.strokeDashoffset = RING_C * (1 - Math.max(0, Math.min(1, level)));
    if (color) els.ringFg.style.stroke = color;
  }
  setInterval(() => {
    if (serverState !== "recording") {
      peak *= 0.8;
      setRing(peak < 0.01 ? 0 : peak * 0.9, null);
    }
  }, 60);
  function applyLevel(rms) {
    if (serverState !== "recording") return;
    peak = Math.max(peak * 0.92, rms);
    setRing(Math.min(1, rms / (peak * 1.1 + 0.002)), null);
  }

  // ---------- status ----------
  const STATE_TEXT = { idle: "ready", recording: "recording…", transcribing: "transcribing…", loading: "loading model…" };
  function setState(s) {
    serverState = s;
    els.status.textContent = STATE_TEXT[s] || s;
    els.status.dataset.state = s;
    els.talk.classList.toggle("recording", s === "recording");
    els.talk.classList.toggle("busy", s === "transcribing" || s === "loading");
    els.talk.disabled = s === "transcribing" || s === "loading";
    if (s === "recording") setRing(0.12, "#ff5d6c");
    if (s === "idle") { setRing(0, "#3ddc97"); peak = 0.0001; }
  }
  function setConnected(on) { els.connDot.classList.toggle("live", on); }

  // ---------- push to talk ----------
  function startTalk() {
    if (talking || els.talk.disabled) return;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    talking = true;
    peak = 0.0001;
    send({ action: "start" });
  }
  function stopTalk() {
    if (!talking) return;
    talking = false;
    send({ action: "stop" });
  }
  els.talk.addEventListener("pointerdown", (e) => { e.preventDefault(); startTalk(); });
  ["pointerup", "pointerleave", "pointercancel"].forEach((ev) => els.talk.addEventListener(ev, stopTalk));

  function isTypingTarget(t) {
    return t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable);
  }
  document.addEventListener("keydown", (e) => {
    if (e.code === "Space" && !isTypingTarget(e.target)) {
      if (capturing) return;            // don't trigger PTT while capturing a hotkey
      e.preventDefault();
      if (!e.repeat) startTalk();
    }
  });
  document.addEventListener("keyup", (e) => {
    if (e.code === "Space" && !isTypingTarget(e.target)) {
      if (capturing) return;
      e.preventDefault();
      stopTalk();
    }
  });

  // ---------- hotkey capture ----------
  const MOD_PRETTY = { ctrl: "Ctrl", alt: "Alt", shift: "Shift", cmd: "Win" };
  const MOUSE_PRETTY = {
    mouse_left: "Mouse Left", mouse_middle: "Mouse Middle", mouse_right: "Mouse Right",
    mouse_x1: "Mouse 4", mouse_x2: "Mouse 5",
  };
  function prettyCombo(spec) {
    if (!spec) return "—";
    return spec.split("+").map((t) => {
      if (MOUSE_PRETTY[t]) return MOUSE_PRETTY[t];
      if (MOD_PRETTY[t]) return MOD_PRETTY[t];
      if (/^f\d+$/.test(t)) return t.toUpperCase();
      if (t.length === 1) return t.toUpperCase();
      return t.charAt(0).toUpperCase() + t.slice(1);
    }).join(" + ");
  }
  function mapKey(e) {
    const k = e.key;
    if (k === " ") return "space";
    if (/^F\d{1,2}$/.test(k)) return k.toLowerCase();
    if (k.length === 1) return k.toLowerCase();
    const named = { Enter: "enter", Tab: "tab", Pause: "pause", Insert: "insert", Home: "home",
      End: "end", PageUp: "pageup", PageDown: "pagedown", ArrowUp: "up", ArrowDown: "down",
      ArrowLeft: "left", ArrowRight: "right", Backspace: "backspace", Delete: "delete",
      CapsLock: "capslock", ScrollLock: "scrolllock", NumLock: "numlock" };
    return named[k] || null;
  }
  function renderHotkey() {
    els.hotkeyBtn.disabled = !hkState.available;
    els.hotkeyToggle.disabled = !hkState.available;
    els.hotkeyToggle.checked = !!hkState.enabled;
    if (capturing) {
      els.hotkeyLabel.textContent = "press keys…";
      els.hotkeyBtn.classList.add("capturing");
    } else {
      els.hotkeyLabel.textContent = hkState.available ? prettyCombo(hkState.key) : "n/a";
      els.hotkeyBtn.classList.remove("capturing");
    }
    els.hotkeyBtn.title = hkState.available
      ? "Click, then press a key combo or mouse button (Esc to cancel)"
      : "pynput not installed (uv sync --extra hotkey)";
  }
  els.hotkeyBtn.addEventListener("click", () => {
    if (els.hotkeyBtn.disabled) return;
    capturing = true;
    renderHotkey();
    els.hotkeyBtn.blur();
  });
  const MOUSE_BTN = { 0: "mouse_left", 1: "mouse_middle", 2: "mouse_right", 3: "mouse_x1", 4: "mouse_x2" };
  let captureSuppress = false;   // swallow the mouseup/auxclick following a captured mousedown
  function currentMods(e) {
    const mods = [];
    if (e.ctrlKey) mods.push("ctrl");
    if (e.altKey) mods.push("alt");
    if (e.shiftKey) mods.push("shift");
    if (e.metaKey) mods.push("cmd");
    return mods;
  }
  function applyCombo(combo) {
    capturing = false;
    send({ action: "set_hotkey", key: combo });
    hkState.key = combo;          // optimistic, confirmed by broadcast
    renderHotkey();
  }
  document.addEventListener("keydown", (e) => {
    if (!capturing) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    if (e.key === "Escape") { capturing = false; renderHotkey(); return; }
    if (["Control", "Alt", "Shift", "Meta"].includes(e.key)) return;  // wait for a real key
    const main = mapKey(e);
    if (!main) { capturing = false; renderHotkey(); return; }
    applyCombo([...currentMods(e), main].join("+"));
  });
  document.addEventListener("mousedown", (e) => {
    if (!capturing) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    captureSuppress = true;        // also absorb the matching mouseup/auxclick (stops x1/x2 nav)
    setTimeout(() => { captureSuppress = false; }, 300);
    const token = MOUSE_BTN[e.button];
    if (!token) { capturing = false; renderHotkey(); return; }
    applyCombo([...currentMods(e), token].join("+"));
  });
  ["mouseup", "auxclick"].forEach((ev) =>
    document.addEventListener(ev, (e) => {
      if (captureSuppress) { e.preventDefault(); e.stopPropagation(); }
    })
  );
  document.addEventListener("contextmenu", (e) => {
    if (capturing || captureSuppress) e.preventDefault();
  });
  els.hotkeyToggle.addEventListener("change", () => {
    send({ action: "set_hotkey_enabled", enabled: els.hotkeyToggle.checked });
    hkState.enabled = els.hotkeyToggle.checked;
  });
  els.autopasteToggle.addEventListener("change", () => {
    send({ action: "set_auto_paste", enabled: els.autopasteToggle.checked });
  });

  // ---------- results / history ----------
  function showResult({ text, copied, pasted, elapsed, model }) {
    els.resultCard.hidden = false;
    els.resultText.textContent = text || "";
    els.copiedBadge.hidden = !copied;
    els.pastedBadge.hidden = !pasted;
    els.metaBadge.textContent = `${model ?? ""} · ${elapsed ?? 0}s`.replace(/^ · /, "");
    if (text) addHistory(text, model, elapsed);
  }
  function addHistory(text, model) {
    const li = document.createElement("li");
    const left = document.createElement("span");
    left.className = "txt";
    left.textContent = text;
    const t = document.createElement("span");
    t.className = "time";
    t.textContent = `${nowStamp()} · ${model ?? ""}`;
    const btn = document.createElement("button");
    btn.className = "copy";
    btn.textContent = "copy";
    btn.addEventListener("click", () => copyText(text, btn));
    left.appendChild(t);
    li.appendChild(left);
    li.appendChild(btn);
    els.history.prepend(li);
    while (els.history.children.length > 50) els.history.lastChild.remove();
  }
  function nowStamp() {
    return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  }
  async function copyText(text, btn) {
    try {
      await navigator.clipboard.writeText(text);
      if (btn) { const o = btn.textContent; btn.textContent = "copied ✓"; setTimeout(() => (btn.textContent = o), 1200); }
    } catch { /* clipboard API may be blocked; server already copied the latest */ }
  }
  els.copyAgain.addEventListener("click", () => copyText(els.resultText.textContent, els.copyAgain));
  els.clearHistory.addEventListener("click", () => { els.history.innerHTML = ""; });

  // ---------- model switching ----------
  function populateModels(models, current) {
    els.modelSelect.innerHTML = "";
    models.forEach((m) => {
      const opt = document.createElement("option");
      opt.value = m; opt.textContent = m;
      if (m === current) opt.selected = true;
      els.modelSelect.appendChild(opt);
    });
  }
  els.modelSelect.addEventListener("change", () => send({ action: "set_model", model: els.modelSelect.value }));

  // ---------- websocket ----------
  function connect() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(`${proto}://${location.host}/ws`);
    ws.onopen = () => setConnected(true);
    ws.onclose = () => { setConnected(false); setState("connecting"); setTimeout(connect, 1500); };
    ws.onerror = () => { try { ws.close(); } catch {} };
    ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data);
      switch (msg.type) {
        case "info":
          els.deviceChip.textContent = msg.cuda ? `GPU · ${msg.device_name}` : `CPU only`;
          els.deviceChip.title = `device=${msg.device} backend=${msg.backend}`;
          els.backendInfo.textContent = `backend: ${msg.backend}`;
          break;
        case "models": populateModels(msg.models, msg.current); break;
        case "model_changed": els.modelSelect.value = msg.model; break;
        case "status": setState(msg.state); break;
        case "level": applyLevel(msg.rms); break;
        case "result": showResult(msg); break;
        case "hotkey":
          hkState = { enabled: !!msg.enabled, key: msg.key, available: !!msg.available };
          renderHotkey();
          break;
        case "auto_paste": els.autopasteToggle.checked = !!msg.enabled; break;
        case "error": console.warn("server error:", msg.message); break;
      }
    };
  }

  renderHotkey();
  setState("connecting");
  connect();
})();
