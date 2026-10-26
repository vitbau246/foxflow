// FoxFlow action recorder. recorder.py injects this into every frame while a
// profile is recording and receives the events through the __foxflowRecord
// binding. Only trusted (user-made) events are recorded. Each element gets
// several selectors, most stable first; replay uses the first that matches.
(() => {
  const KEY = "__foxflowRecorder";
  const existing = window[KEY];
  if (existing) { existing.active = true; return; }
  const state = { active: true };
  Object.defineProperty(window, KEY, { value: state, enumerable: false, configurable: true });

  const send = (event) => {
    try { return Promise.resolve(window.__foxflowRecord(event)); } catch (e) { return Promise.resolve(false); }
  };

  const TEXT_TYPES = new Set(["", "text", "search", "email", "password", "tel", "url", "number",
    "date", "time", "datetime-local", "month", "week", "color"]);
  const KEYS = new Set(["Enter", "Escape", "Tab", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight",
    "PageUp", "PageDown", "Home", "End", "Backspace", "Delete", "F5"]);
  const EDIT_KEYS = new Set(["ArrowLeft", "ArrowRight", "Home", "End", "Backspace", "Delete", "Tab"]);
  const CLICKABLE = "a,button,input,select,textarea,label,summary,option,[role=button],[role=link]," +
    "[role=menuitem],[role=tab],[role=checkbox],[role=radio],[role=option],[role=switch],[onclick]";

  const esc = (s) => String(s).replace(/\\/g, "\\\\").replace(/"/g, '\\"');
  const norm = (s) => String(s || "").replace(/\s+/g, " ").trim();
  const count = (sel) => { try { return document.querySelectorAll(sel).length; } catch (e) { return 0; } };

  function isTextField(el) {
    if (!el || el.nodeType !== 1) return false;
    if (el.isContentEditable) return true;
    if (el.localName === "textarea") return true;
    return el.localName === "input" && TEXT_TYPES.has((el.getAttribute("type") || "").toLowerCase());
  }
  function isToggle(el) {
    return el && el.localName === "input" && ["checkbox", "radio"].includes((el.type || "").toLowerCase());
  }
  // Ids such as "ember123", ":r5:" or "input-8f3a2c" change on every page load.
  function stableId(id) {
    return id && id.length <= 64 && !/\d{3,}|^\d|[:\s]|[0-9a-f]{6,}/i.test(id);
  }
  function stableClass(c) {
    return c && c.length <= 40 && !/\d{3,}|[0-9a-f]{6,}|^(css|sc|jsx|emotion|svelte)-|__|:/i.test(c);
  }
  // Playwright's :text-is() also matches the whitespace-normalised textContent.
  function ownText(el) {
    return norm(String(el.textContent || "").slice(0, 2000)).slice(0, 200);
  }
  function countTextIs(tag, text) {
    const list = document.getElementsByTagName(tag);
    if (list.length > 3000) return 2;
    let n = 0;
    for (const e of list) if (ownText(e) === text && ++n > 1) break;
    return n;
  }
  function roleOf(el) {
    const role = el.getAttribute("role");
    if (role) return role;
    const tag = el.localName;
    if (tag === "a" && el.hasAttribute("href")) return "link";
    if (tag === "button" || (tag === "input" && ["submit", "button", "reset"].includes(el.type))) return "button";
    return "";
  }

  function cssPath(el) {
    const parts = [];
    for (let node = el; node && node.nodeType === 1 && node !== document.documentElement; node = node.parentElement) {
      if (node !== el && node.id && stableId(node.id)) {
        parts.unshift(`#${CSS.escape(node.id)}`);
        const sel = parts.join(" > ");
        if (count(sel) === 1) return sel;
        break;
      }
      let part = node.localName;
      const parent = node.parentElement;
      if (parent) {
        const same = Array.from(parent.children).filter((c) => c.localName === node.localName);
        if (same.length > 1) part += `:nth-of-type(${same.indexOf(node) + 1})`;
      }
      parts.unshift(part);
      if (count(parts.join(" > ")) === 1) return parts.join(" > ");
    }
    return parts.join(" > ");
  }

  function selectorsFor(el) {
    const out = [];
    const tag = el.localName;
    const add = (sel, unique) => { if (sel && unique && !out.includes(sel)) out.push(sel); };
    for (const a of ["data-testid", "data-test", "data-test-id", "data-qa", "data-cy"]) {
      const v = el.getAttribute(a);
      if (v) add(`[${a}="${esc(v)}"]`, count(`[${a}="${esc(v)}"]`) === 1);
    }
    if (el.id && stableId(el.id)) add(`#${CSS.escape(el.id)}`, count(`#${CSS.escape(el.id)}`) === 1);
    for (const a of ["name", "placeholder", "aria-label", "title", "alt"]) {
      const v = el.getAttribute(a);
      if (v && v.length <= 120) add(`${tag}[${a}="${esc(v)}"]`, count(`${tag}[${a}="${esc(v)}"]`) === 1);
    }
    if (!isTextField(el) && tag !== "select") {
      const text = ownText(el);
      if (text && text.length <= 60) add(`${tag}:text-is("${esc(text)}")`, countTextIs(tag, text) === 1);
    }
    const href = tag === "a" && el.getAttribute("href");
    if (href && href.length <= 200 && !href.startsWith("javascript:")) {
      add(`a[href="${esc(href)}"]`, count(`a[href="${esc(href)}"]`) === 1);
    }
    const classes = Array.from(el.classList).filter(stableClass).slice(0, 3);
    if (classes.length) {
      const sel = tag + classes.map((c) => "." + CSS.escape(c)).join("");
      add(sel, count(sel) === 1);
    }
    add(cssPath(el), true);
    return out.slice(0, 6);
  }

  function describe(el) {
    const tag = el.localName;
    const text = isTextField(el) || tag === "select" ? "" : ownText(el).slice(0, 60);
    const hint = text || el.getAttribute("aria-label") || el.getAttribute("placeholder") ||
      el.getAttribute("name") || el.getAttribute("title") || el.getAttribute("alt") || el.id || "";
    return { selectors: selectorsFor(el), tag, role: roleOf(el), hint: norm(hint).slice(0, 80) };
  }

  function clickTarget(node) {
    const el = node && node.nodeType === 1 ? node : node && node.parentElement;
    if (!el) return null;
    const target = el.closest(CLICKABLE) || el;
    // A click on the page background does nothing worth replaying.
    return target === document.body || target === document.documentElement ? null : target;
  }
  function editable(node) {
    const el = node && node.nodeType === 1 ? node : node && node.parentElement;
    if (!el) return null;
    if (el.isContentEditable) {
      let root = el;
      while (root.parentElement && root.parentElement.isContentEditable) root = root.parentElement;
      return root;
    }
    return isTextField(el) ? el : null;
  }

  // Hover menus: Facebook's reaction bar, dropdowns, tooltips. They are built (or
  // shown) while something else is hovered; a click inside one is recorded with
  // that element to hover first. `revealed` holds when nodes were added or shown.
  const revealed = new WeakMap();
  const hovers = [];  // {el, start}, oldest first
  new MutationObserver((mutations) => {
    if (!state.active) return;
    const now = Date.now();
    for (const m of mutations) {
      if (m.type === "childList") {
        for (const n of m.addedNodes) if (n.nodeType === 1) revealed.set(n, now);
      } else if (m.target.nodeType === 1) {
        revealed.set(m.target, now);
      }
    }
  }).observe(document, { childList: true, subtree: true, attributes: true,
    attributeFilter: ["style", "hidden", "aria-hidden", "aria-expanded", "open"] });
  document.addEventListener("mouseover", (e) => {
    if (!state.active || !e.isTrusted) return;
    const el = clickTarget(e.target);
    if (!el || (hovers.length && hovers[hovers.length - 1].el === el)) return;
    hovers.push({ el, start: Date.now() });
    if (hovers.length > 30) hovers.shift();
  }, true);
  function hoverBefore(target) {
    // When did the part of the page holding the target appear?
    let shown = 0;
    for (let n = target, depth = 0; n && n.nodeType === 1 && depth < 30; n = n.parentElement, depth++) {
      shown = Math.max(shown, revealed.get(n) || 0);
    }
    if (!shown) return null;
    const now = Date.now();
    for (let i = hovers.length - 1; i >= 0; i--) {
      const h = hovers[i];
      const end = i + 1 < hovers.length ? hovers[i + 1].start : now;
      if (now - h.start > 10000) break;
      if (h.el === target || h.el.contains(target) || target.contains(h.el) || !h.el.isConnected) continue;
      // It appeared while that element was hovered, or just after (menus open late).
      if (shown >= h.start && shown <= end + 1500 && end - h.start >= 150) return h.el;
    }
    return null;
  }

  // Keystrokes in one field are sent as a single fill once typing pauses or
  // anything else happens, so the event order stays the order the user acted in.
  let pending = null;
  function flush() {
    if (!pending) return;
    const p = pending;
    pending = null;
    clearTimeout(p.timer);
    const el = p.el;
    const value = el.isContentEditable ? el.innerText : el.value;
    send({ type: "fill", value, sensitive: (el.type || "").toLowerCase() === "password",
      typing_ms: p.last - p.first, keystrokes: p.count, ...describe(el) });
  }

  document.addEventListener("input", (e) => {
    if (!state.active || !e.isTrusted) return;
    const el = editable(e.target);
    if (!el) return;
    const now = Date.now();
    if (pending && pending.el !== el) flush();
    if (!pending) pending = { el, first: now, count: 0 };
    pending.last = now;
    pending.count += 1;
    clearTimeout(pending.timer);
    pending.timer = setTimeout(flush, 800);
  }, true);

  document.addEventListener("change", (e) => {
    if (!state.active || !e.isTrusted) return;
    const el = e.target;
    if (!el || el.nodeType !== 1) return;
    if (isTextField(el)) {
      if (pending && pending.el === el) flush();
      return;
    }
    flush();
    if (el.localName === "select") {
      const option = el.selectedOptions && el.selectedOptions[0];
      send({ type: "select", value: el.value, option: option ? norm(option.text) : "", ...describe(el) });
    } else if (isToggle(el)) {
      send({ type: el.checked || el.type === "radio" ? "check" : "uncheck", ...describe(el) });
    }
  }, true);

  document.addEventListener("click", (e) => {
    if (!state.active || !e.isTrusted || e.button !== 0) return;
    const el = clickTarget(e.composedPath ? e.composedPath()[0] : e.target);
    if (!el) return;
    // Fields are focused by the fill step; toggles and selects record a change.
    if (isTextField(el) || isToggle(el) || el.localName === "select" || el.localName === "option") return;
    if (el.localName === "label" && el.control) return;
    if (el.localName === "input" && (el.type || "").toLowerCase() === "file") return;
    flush();
    const hover = hoverBefore(el);
    send({ type: "click", ...describe(el), ...(hover ? { hover: describe(hover) } : {}) });
  }, true);

  document.addEventListener("keydown", (e) => {
    if (!state.active || !e.isTrusted || e.repeat || e.isComposing) return;
    const key = e.key;
    if (["Control", "Shift", "Alt", "Meta"].includes(key)) return;
    const inField = !!editable(e.target);
    const mods = [];
    if (e.ctrlKey) mods.push("Control");
    if (e.altKey) mods.push("Alt");
    if (e.metaKey) mods.push("Meta");
    if (mods.length) {
      // Copy, paste, select-all... in a field end up in the field's value.
      if (inField && key !== "Enter") return;
      if (e.shiftKey) mods.push("Shift");
    } else {
      if (!KEYS.has(key)) return;
      if (inField && EDIT_KEYS.has(key)) return;
    }
    flush();
    // In a field the key goes to that field; anywhere else to the page.
    const target = editable(e.target);
    send({ type: "press", key: [...mods, key.length === 1 ? key.toLowerCase() : key].join("+"),
      ...(target ? describe(target) : {}) });
  }, true);

  // Only scrolling the user did: sites also scroll on their own.
  if (window === window.top) {
    let userScrollAt = 0, timer = null;
    const mark = (e) => { if (e.isTrusted) userScrollAt = Date.now(); };
    window.addEventListener("wheel", mark, { capture: true, passive: true });
    window.addEventListener("touchmove", mark, { capture: true, passive: true });
    window.addEventListener("keydown", (e) => {
      if (["PageDown", "PageUp", "ArrowDown", "ArrowUp", " ", "End", "Home"].includes(e.key) && !editable(e.target)) mark(e);
    }, true);
    window.addEventListener("scroll", (e) => {
      if (!state.active || (e.target !== document && e.target !== window)) return;
      if (Date.now() - userScrollAt > 1500) return;
      clearTimeout(timer);
      timer = setTimeout(() => {
        if (state.active) send({ type: "scroll", x: Math.round(window.scrollX), y: Math.round(window.scrollY) });
      }, 700);
    }, { capture: true, passive: true });
  }

  window.addEventListener("pagehide", flush, true);
  Object.defineProperty(state, "stop", { value: () => { flush(); state.active = false; } });

  // A new document asks whether a recording is still going before it listens.
  send({ type: "ping" }).then((active) => { if (!active) state.active = false; });
})();
