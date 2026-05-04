/**
 * Jeeves web widget.
 *
 * Install:
 *   <script async src="https://app.example.com/widget.js" data-tenant-id="<uuid>"></script>
 *
 * Optional data attributes:
 *   data-title, data-subtitle, data-accent, data-position, data-greeting,
 *   data-user-id, data-email-required, data-privacy-url, data-custom-launcher,
 *   data-z-index.
 *
 * Runtime API:
 *   window.JeevesWidget.open()
 *   window.JeevesWidget.close()
 *   window.JeevesWidget.toggle()
 *   window.JeevesWidget.identify({ user_id: "user@example.com", plan: "pro" })
 *   window.JeevesWidget.send("Message")
 *   window.JeevesWidget.reset()
 */
(function () {
  "use strict";

  if (window.JeevesWidget && window.JeevesWidget.__loaded) return;

  var script = document.currentScript;
  if (!script) {
    var scripts = document.getElementsByTagName("script");
    script = scripts[scripts.length - 1];
  }

  function attr(name, fallback) {
    var value = script && script.getAttribute(name);
    return value == null || value === "" ? fallback : value;
  }

  var TENANT = attr("data-tenant-id", "");
  if (!TENANT) {
    console.warn("[Jeeves] missing data-tenant-id");
    return;
  }

  var BASE = (function () {
    try { return new URL(script.src).origin; } catch (e) { return ""; }
  })();

  var cfg = {
    title: attr("data-title", "Jeeves support"),
    subtitle: attr("data-subtitle", "AI agent online"),
    accent: attr("data-accent", "#2563eb"),
    position: attr("data-position", "right") === "left" ? "left" : "right",
    greeting: attr("data-greeting", "Hi. How can I help?"),
    privacyUrl: attr("data-privacy-url", ""),
    customLauncher: attr("data-custom-launcher", ""),
    zIndex: parseInt(attr("data-z-index", "2147483600"), 10) || 2147483600,
    emailRequired: attr("data-email-required", "true") !== "false",
    initialUserId: attr("data-user-id", ""),
    channel: attr("data-channel", "web_widget"),
  };

  var keys = {
    user: "jeeves:user:" + TENANT,
    messages: "jeeves:messages:" + TENANT,
    seenInbox: "jeeves:seen-inbox:" + TENANT,
    extraFields: "jeeves:extra-fields:" + TENANT,
  };

  function storageGet(key, fallback) {
    try {
      var raw = window.localStorage.getItem(key);
      return raw == null ? fallback : JSON.parse(raw);
    } catch (e) {
      return fallback;
    }
  }

  function storageSet(key, value) {
    try { window.localStorage.setItem(key, JSON.stringify(value)); } catch (e) {}
  }

  function storageRemove(key) {
    try { window.localStorage.removeItem(key); } catch (e) {}
  }

  function esc(text) {
    return String(text == null ? "" : text).replace(/[&<>"']/g, function (c) {
      return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c];
    });
  }

  function asText(value, fallback) {
    if (typeof value === "string") return value;
    if (value == null) return fallback || "";
    try { return JSON.stringify(value, null, 2); } catch (e) { return fallback || String(value); }
  }

  function isEmailish(value) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
  }

  function nowIso() {
    return new Date().toISOString();
  }

  var userId = cfg.initialUserId || storageGet(keys.user, "");
  if (cfg.initialUserId) storageSet(keys.user, userId);
  var extraFields = storageGet(keys.extraFields, {});
  if (!extraFields || typeof extraFields !== "object") extraFields = {};

  var messages = storageGet(keys.messages, []);
  if (!Array.isArray(messages)) messages = [];
  var unread = 0;
  var sending = false;
  var open = false;

  var host = document.createElement("div");
  host.id = "jeeves-widget-root";
  host.style.position = "relative";
  host.style.zIndex = String(cfg.zIndex);
  var root = host.attachShadow ? host.attachShadow({ mode: "open" }) : host;

  var side = cfg.position === "left" ? "left" : "right";
  var opposite = cfg.position === "left" ? "right" : "left";
  var css = [
    ":host{all:initial}",
    ".jw-wrap{position:fixed;" + side + ":20px;bottom:20px;z-index:" + cfg.zIndex + ";font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;color:#172033}",
    ".jw-launcher{width:56px;height:56px;border:0;border-radius:50%;background:" + cfg.accent + ";color:#fff;box-shadow:0 12px 28px rgba(15,23,42,.28);cursor:pointer;display:flex;align-items:center;justify-content:center;transition:transform .15s ease,box-shadow .15s ease}",
    ".jw-launcher:hover{transform:translateY(-1px);box-shadow:0 16px 34px rgba(15,23,42,.34)}",
    ".jw-launcher:focus-visible,.jw-close:focus-visible,.jw-send:focus-visible,.jw-start:focus-visible,.jw-input:focus-visible,.jw-email-input:focus-visible{outline:3px solid rgba(37,99,235,.25);outline-offset:2px}",
    ".jw-icon{width:25px;height:25px;display:block}",
    ".jw-badge{position:absolute;top:-4px;" + opposite + ":-4px;min-width:19px;height:19px;padding:0 5px;border-radius:999px;background:#ef4444;color:#fff;font:700 11px/19px system-ui;text-align:center;border:2px solid #fff;display:none}",
    ".jw-badge.show{display:block}",
    ".jw-panel{position:absolute;bottom:72px;" + side + ":0;width:376px;height:584px;max-height:min(584px,calc(100vh - 108px));background:#fff;border:1px solid rgba(15,23,42,.12);border-radius:8px;box-shadow:0 24px 64px rgba(15,23,42,.24);display:none;overflow:hidden;flex-direction:column}",
    ".jw-panel.open{display:flex}",
    ".jw-head{min-height:72px;padding:14px 16px;background:#111827;color:#fff;display:flex;align-items:center;gap:12px}",
    ".jw-avatar{width:38px;height:38px;border-radius:8px;background:" + cfg.accent + ";display:flex;align-items:center;justify-content:center;font-weight:800;color:#fff;flex:0 0 auto}",
    ".jw-head-text{min-width:0;flex:1}",
    ".jw-title{font-size:15px;font-weight:750;line-height:1.2;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}",
    ".jw-sub{font-size:12px;color:#cbd5e1;margin-top:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}",
    ".jw-close{width:34px;height:34px;border:0;border-radius:8px;background:rgba(255,255,255,.08);color:#fff;cursor:pointer;font-size:20px;line-height:1}",
    ".jw-body{flex:1;min-height:0;display:flex;flex-direction:column;background:#f8fafc}",
    ".jw-email{padding:18px;display:none;gap:10px;flex-direction:column}",
    ".jw-email.show{display:flex}",
    ".jw-email h3{margin:0;color:#172033;font-size:16px;line-height:1.3}",
    ".jw-email p{margin:0;color:#64748b;font-size:13px;line-height:1.45}",
    ".jw-email-input,.jw-input{width:100%;border:1px solid #cbd5e1;border-radius:8px;background:#fff;color:#172033;font:14px system-ui;padding:11px 12px;box-sizing:border-box}",
    ".jw-start,.jw-send{border:0;border-radius:8px;background:" + cfg.accent + ";color:#fff;font-weight:700;cursor:pointer}",
    ".jw-start{padding:11px 12px}",
    ".jw-privacy{font-size:11px;line-height:1.4;color:#64748b}",
    ".jw-privacy a{color:" + cfg.accent + ";text-decoration:none}",
    ".jw-error{display:none;color:#b91c1c;font-size:12px;line-height:1.35}",
    ".jw-error.show{display:block}",
    ".jw-msgs{flex:1;min-height:0;overflow:auto;padding:14px;display:flex;flex-direction:column;gap:10px;scroll-behavior:smooth}",
    ".jw-msg{max-width:82%;padding:10px 12px;border-radius:8px;font-size:14px;line-height:1.42;white-space:pre-wrap;overflow-wrap:anywhere;box-shadow:0 1px 2px rgba(15,23,42,.06)}",
    ".jw-msg.bot{align-self:flex-start;background:#fff;color:#172033;border:1px solid #e2e8f0}",
    ".jw-msg.user{align-self:flex-end;background:" + cfg.accent + ";color:#fff}",
    ".jw-time{display:block;margin-top:5px;font-size:10px;opacity:.62}",
    ".jw-typing{display:none;align-self:flex-start;background:#fff;border:1px solid #e2e8f0;color:#64748b;border-radius:8px;padding:9px 11px;font-size:13px}",
    ".jw-typing.show{display:block}",
    ".jw-composer{display:flex;gap:8px;padding:12px;border-top:1px solid #e2e8f0;background:#fff}",
    ".jw-send{width:44px;flex:0 0 44px;display:flex;align-items:center;justify-content:center}",
    ".jw-send:disabled{opacity:.55;cursor:default}",
    ".jw-footer{padding:0 12px 10px;background:#fff;color:#94a3b8;font-size:11px;text-align:center}",
    ".jw-footer a{color:#64748b;text-decoration:none}",
    "@media (max-width:520px){.jw-wrap{left:12px;right:12px;bottom:12px}.jw-panel{position:fixed;left:10px;right:10px;bottom:78px;width:auto;height:calc(100vh - 104px);max-height:none}.jw-launcher{margin-" + side + ":auto}}",
    "@media (prefers-reduced-motion:reduce){.jw-launcher,.jw-msgs{transition:none;scroll-behavior:auto}}"
  ].join("");

  root.innerHTML =
    '<style>' + css + '</style>' +
    '<div class="jw-wrap">' +
      '<section class="jw-panel" role="dialog" aria-modal="false" aria-label="' + esc(cfg.title) + '">' +
        '<header class="jw-head">' +
          '<div class="jw-avatar" aria-hidden="true">J</div>' +
          '<div class="jw-head-text"><div class="jw-title">' + esc(cfg.title) + '</div><div class="jw-sub">' + esc(cfg.subtitle) + '</div></div>' +
          '<button class="jw-close" type="button" aria-label="Close chat">x</button>' +
        '</header>' +
        '<div class="jw-body">' +
          '<form class="jw-email" novalidate>' +
            '<h3>Start a conversation</h3>' +
            '<p>Enter your email so the team can follow up if needed.</p>' +
            '<input class="jw-email-input" type="email" inputmode="email" autocomplete="email" placeholder="you@example.com"/>' +
            '<div class="jw-error" data-email-error>Please enter a valid email.</div>' +
            '<button class="jw-start" type="submit">Continue</button>' +
            '<div class="jw-privacy">By continuing, your conversation may be stored by this business.' +
              (cfg.privacyUrl ? ' <a href="' + esc(cfg.privacyUrl) + '" target="_blank" rel="noopener">Privacy notice</a>.' : '') +
            '</div>' +
          '</form>' +
          '<div class="jw-msgs" aria-live="polite" aria-relevant="additions"></div>' +
          '<div class="jw-typing">Jeeves is typing...</div>' +
          '<form class="jw-composer">' +
            '<input class="jw-input" type="text" autocomplete="off" maxlength="4000" placeholder="Type your message..."/>' +
            '<button class="jw-send" type="submit" aria-label="Send message">' +
              '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M5 12h13M13 6l6 6-6 6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>' +
            '</button>' +
          '</form>' +
          '<div class="jw-footer"><a href="' + esc(BASE) + '" target="_blank" rel="noopener">Powered by Jeeves</a></div>' +
        '</div>' +
      '</section>' +
      '<button class="jw-launcher" type="button" aria-label="Open support chat" aria-expanded="false">' +
        '<svg class="jw-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M7.5 18.5 4 21v-4.2A8.2 8.2 0 0 1 2.5 12C2.5 7 6.8 3 12 3s9.5 4 9.5 9-4.3 9-9.5 9a10.3 10.3 0 0 1-4.5-1.1Z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><path d="M8 11.5h8M8 14.5h5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>' +
        '<span class="jw-badge"></span>' +
      '</button>' +
    '</div>';

  function boot() {
    document.body.appendChild(host);
    bindDom();
    bindCustomLaunchers();
    renderIdentity();
    renderMessages();
    pollInbox();
    setInterval(pollInbox, 15000);
  }

  if (document.body) boot();
  else document.addEventListener("DOMContentLoaded", boot);

  var panel, launcher, badge, closeBtn, emailForm, emailInput, emailError, msgsEl, typingEl, composer, input, sendBtn;

  function bindDom() {
    panel = root.querySelector(".jw-panel");
    launcher = root.querySelector(".jw-launcher");
    badge = root.querySelector(".jw-badge");
    closeBtn = root.querySelector(".jw-close");
    emailForm = root.querySelector(".jw-email");
    emailInput = root.querySelector(".jw-email-input");
    emailError = root.querySelector("[data-email-error]");
    msgsEl = root.querySelector(".jw-msgs");
    typingEl = root.querySelector(".jw-typing");
    composer = root.querySelector(".jw-composer");
    input = root.querySelector(".jw-input");
    sendBtn = root.querySelector(".jw-send");

    launcher.addEventListener("click", toggle);
    closeBtn.addEventListener("click", closeWidget);
    emailForm.addEventListener("submit", function (e) {
      e.preventDefault();
      var value = (emailInput.value || "").trim();
      if (!isEmailish(value)) {
        emailError.classList.add("show");
        emailInput.focus();
        return;
      }
      identify({ user_id: value });
      renderIdentity();
      focusInput();
    });
    composer.addEventListener("submit", function (e) {
      e.preventDefault();
      send((input.value || "").trim());
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && open) closeWidget();
    });
  }

  function bindCustomLaunchers() {
    if (!cfg.customLauncher) return;
    try {
      var nodes = document.querySelectorAll(cfg.customLauncher);
      for (var i = 0; i < nodes.length; i += 1) {
        nodes[i].addEventListener("click", function (e) {
          e.preventDefault();
          openWidget();
        });
      }
    } catch (e) {
      console.warn("[Jeeves] invalid custom launcher selector", cfg.customLauncher);
    }
  }

  function identify(data) {
    if (!data || typeof data !== "object") return;
    // Extract user identifier
    var value = data.user_id || data.email || data.id;
    if (value) {
      userId = String(value);
      storageSet(keys.user, userId);
    }
    // Merge arbitrary extra fields (exclude reserved keys)
    var reserved = ["user_id", "email", "id", "message", "tenant_id", "channel"];
    var changed = false;
    for (var k in data) {
      if (!data.hasOwnProperty(k)) continue;
      if (reserved.indexOf(k) !== -1) continue;
      extraFields[k] = data[k];
      changed = true;
    }
    if (changed) storageSet(keys.extraFields, extraFields);
    renderIdentity();
  }

  function reset() {
    userId = "";
    extraFields = {};
    messages = [];
    unread = 0;
    storageRemove(keys.user);
    storageRemove(keys.messages);
    storageRemove(keys.seenInbox);
    storageRemove(keys.extraFields);
    renderIdentity();
    renderMessages();
    updateBadge();
  }

  function renderIdentity() {
    if (!emailForm) return;
    var needsEmail = cfg.emailRequired && !userId;
    emailForm.classList.toggle("show", needsEmail);
    msgsEl.style.display = needsEmail ? "none" : "flex";
    composer.style.display = needsEmail ? "none" : "flex";
    if (!needsEmail && !messages.length) addMessage(cfg.greeting, "bot", true);
  }

  function addMessage(text, role, persist) {
    var clean = asText(text, "").slice(0, 4000);
    if (!clean) return;
    messages.push({ role: role === "user" ? "user" : "bot", text: clean, at: nowIso() });
    if (messages.length > 80) messages = messages.slice(messages.length - 80);
    if (persist !== false) storageSet(keys.messages, messages);
    renderMessages();
    if (!open && role !== "user") {
      unread += 1;
      updateBadge();
    }
  }

  function renderMessages() {
    if (!msgsEl) return;
    msgsEl.innerHTML = messages.map(function (m) {
      var time = "";
      try { time = new Date(m.at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }); } catch (e) {}
      return '<div class="jw-msg ' + (m.role === "user" ? "user" : "bot") + '">' +
        esc(m.text) + '<span class="jw-time">' + esc(time) + '</span></div>';
    }).join("");
    msgsEl.scrollTop = msgsEl.scrollHeight;
  }

  function setTyping(value) {
    typingEl.classList.toggle("show", !!value);
    msgsEl.scrollTop = msgsEl.scrollHeight;
  }

  function setSending(value) {
    sending = !!value;
    sendBtn.disabled = sending;
    input.disabled = sending;
  }

  function send(text) {
    if (!text || sending) return;
    if (cfg.emailRequired && !userId) {
      openWidget();
      emailInput.focus();
      return;
    }
    input.value = "";
    addMessage(text, "user", true);
    setSending(true);
    setTyping(true);

    var body = {
      tenant_id: TENANT,
      user_id: userId || "anonymous",
      message: text,
      channel: cfg.channel,
    };
    // Include extra_fields if any are set
    var hasExtra = false;
    for (var k in extraFields) {
      if (extraFields.hasOwnProperty(k) && extraFields[k] != null) { hasExtra = true; break; }
    }
    if (hasExtra) body.extra_fields = extraFields;

    postJson(BASE + "/widget/chat", body, 30000).then(function (data) {
      addMessage(asText(data.response, "I could not produce a response."), "bot", true);
    }).catch(function (err) {
      addMessage(err && err.message ? err.message : "Network error. Please try again.", "bot", true);
    }).then(function () {
      setTyping(false);
      setSending(false);
      focusInput();
    });
  }

  function postJson(url, body, timeoutMs) {
    var controller = window.AbortController ? new AbortController() : null;
    var timer = controller ? setTimeout(function () { controller.abort(); }, timeoutMs) : null;
    return fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: controller ? controller.signal : undefined,
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (data) {
        if (!r.ok) throw new Error(asText(data.detail, "The support agent is unavailable."));
        return data;
      });
    }).finally(function () {
      if (timer) clearTimeout(timer);
    });
  }

  function pollInbox() {
    if (!userId) return;
    fetch(BASE + "/widget/inbox?tenant_id=" + encodeURIComponent(TENANT) + "&user_id=" + encodeURIComponent(userId))
      .then(function (r) { return r.ok ? r.json() : { messages: [] }; })
      .then(function (data) {
        var seen = storageGet(keys.seenInbox, []);
        if (!Array.isArray(seen)) seen = [];
        var changed = false;
        (data.messages || []).forEach(function (m) {
          if (seen.indexOf(m.id) >= 0) return;
          seen.push(m.id);
          changed = true;
          addMessage(m.message, "bot", true);
        });
        if (changed) storageSet(keys.seenInbox, seen.slice(-200));
      })
      .catch(function () {});
  }

  function openWidget() {
    open = true;
    unread = 0;
    panel.classList.add("open");
    launcher.setAttribute("aria-expanded", "true");
    updateBadge();
    renderIdentity();
    setTimeout(focusInput, 50);
  }

  function closeWidget() {
    open = false;
    panel.classList.remove("open");
    launcher.setAttribute("aria-expanded", "false");
    launcher.focus();
  }

  function toggle() {
    open ? closeWidget() : openWidget();
  }

  function updateBadge() {
    badge.textContent = unread > 9 ? "9+" : String(unread);
    badge.classList.toggle("show", unread > 0);
  }

  function focusInput() {
    if (cfg.emailRequired && !userId) emailInput.focus();
    else input.focus();
  }

  window.JeevesWidget = {
    __loaded: true,
    open: openWidget,
    close: closeWidget,
    toggle: toggle,
    identify: identify,
    send: send,
    reset: reset,
    unread: function () { return unread; },
  };
})();
