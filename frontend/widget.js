/**
 * Jeeves web widget — Web Component version.
 *
 * Install:
 *   <jeeves-widget tenant="<uuid>"></jeeves-widget>
 *   <script defer src="https://app.example.com/widget.js"></script>
 *
 * Attributes:
 *   tenant (required), title, subtitle, accent, icon (SVG string or image URL),
 *   position (left|right), greeting, privacy-url, custom-launcher (CSS selector),
 *   z-index, email-required (true|false), user-id, channel, base-url.
 *
 * Legacy install (still supported):
 *   <script async src="https://app.example.com/widget.js" data-tenant-id="<uuid>"></script>
 *
 * Runtime API:
 *   window.JeevesWidget.open()
 *   window.JeevesWidget.close()
 *   window.JeevesWidget.toggle()
 *   window.JeevesWidget.identify({ user_id: "..." })
 *   window.JeevesWidget.send("Message")
 *   window.JeevesWidget.reset()
 */
(function () {
  "use strict";

  if (window.JeevesWidget && window.JeevesWidget.__loaded) return;

  var _instanceCounter = 0;

  // Auto-detect API base URL from the script's own src attribute.
  // This lets customers embed <script src="https://jeeves-ai.up.railway.app/widget.js">
  // without manually setting base-url on the custom element.
  var _scriptSrc = "";
  try {
    var _s = document.currentScript || document.querySelector('script[src*="widget.js"]');
    if (_s) _scriptSrc = _s.src;
  } catch(e) {}
  var _defaultBaseUrl = _scriptSrc ? _scriptSrc.replace(/\/widget\.js.*$/, "") : location.origin;

  // ── Shared helpers ──

  function stoGet(key, fallback) {
    try { var raw = localStorage.getItem(key); return raw == null ? fallback : JSON.parse(raw); } catch (e) { return fallback; }
  }
  function stoSet(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) {}
  }
  function stoRemove(key) {
    try { localStorage.removeItem(key); } catch (e) {}
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

  var _defaultIcon = '<svg class="jw-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M5 3h14a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H8l-4 4V5a2 2 0 0 1 2-2z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/><path d="M8 9h8M8 13h6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>';

  // ════════════════════════════════════════════════════════════════
  // Web Component
  // ════════════════════════════════════════════════════════════════

  class JeevesWidget extends HTMLElement {
    constructor() {
      super();
      this._booted = false;
      this._uid = _instanceCounter++;
      this._cfg = {};
      this._state = {
        userId: "",
        extraFields: {},
        messages: [],
        unread: 0,
        sending: false,
        open: false,
        resolvedPending: false,
        ratingState: null,
        followUpTimeout: null,
        pollingTimer: null,
      };
      this._els = {};
    }

    connectedCallback() {
      if (this._booted) return;
      this._booted = true;
      this._readCfg();
      this._loadState();
      this._buildCSS();
      this._render();
      this._bindEvents();
      this._bindCustomLaunchers();
      this._renderIdentity();
      this._renderMessages();
      var self = this;
      this._state.pollingTimer = setInterval(function () { self._pollInbox(); }, 15000);
    }

    disconnectedCallback() {
      if (this._state.pollingTimer) clearInterval(this._state.pollingTimer);
      if (this._state.followUpTimeout) clearTimeout(this._state.followUpTimeout);
    }

    _readCfg() {
      function g(el, name, fallback) {
        var v = el.getAttribute(name);
        return v == null ? fallback : v;
      }
      var el = this;
      var pos = g(el, "position", "right");
      this._cfg = {
        tenant: g(el, "tenant", ""),
        title: g(el, "title", "Jeeves support"),
        subtitle: g(el, "subtitle", ""),
        accent: g(el, "accent", "#5e6ad2"),
        position: pos === "left" ? "left" : "right",
        greeting: g(el, "greeting", "Hi. How can I help?"),
        privacyUrl: g(el, "privacy-url", ""),
        customLauncher: g(el, "custom-launcher", ""),
        zIndex: parseInt(g(el, "z-index", "2147483600"), 10) || 2147483600,
        emailRequired: g(el, "email-required", "true") !== "false",
        channel: g(el, "channel", "web_widget"),
        icon: g(el, "icon", ""),
        initialUserId: g(el, "user-id", ""),
        baseUrl: g(el, "base-url", _defaultBaseUrl),
      };
      if (!this._cfg.tenant) console.warn("[Jeeves] missing tenant attribute");
    }

    _keys() {
      var t = this._cfg.tenant;
      return {
        user: "jeeves:user:" + t,
        messages: "jeeves:messages:" + t,
        seenInbox: "jeeves:seen-inbox:" + t,
        extraFields: "jeeves:extra-fields:" + t,
      };
    }

    _loadState() {
      var k = this._keys();
      this._state.userId = this._cfg.initialUserId || stoGet(k.user, "");
      if (this._cfg.initialUserId) stoSet(k.user, this._state.userId);
      this._state.extraFields = stoGet(k.extraFields, {});
      if (!this._state.extraFields || typeof this._state.extraFields !== "object") this._state.extraFields = {};
      this._state.messages = stoGet(k.messages, []);
      if (!Array.isArray(this._state.messages)) this._state.messages = [];
      this._state.ratingState = stoGet("jeeves:rating:" + this._cfg.tenant, null);
    }

    _saveMessages() {
      stoSet(this._keys().messages, this._state.messages);
    }

    _launcherIconHtml() {
      var ic = this._cfg.icon;
      if (!ic) return _defaultIcon;
      var t = ic.trim();
      if (t.indexOf("<svg") === 0) return t;
      return '<img class="jw-icon" src="' + esc(ic) + '" alt="">';
    }

    _buildCSS() {
      var cfg = this._cfg;
      var side = cfg.position === "left" ? "left" : "right";
      var opposite = cfg.position === "left" ? "right" : "left";

      this._css = [
        ":host{all:initial}",
        ".jw-wrap{position:fixed;" + side + ":20px;bottom:20px;z-index:" + cfg.zIndex + ";font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;color:#172033}",
        ".jw-launcher{width:56px;height:56px;border:0;border-radius:50%;background:" + cfg.accent + ";color:#fff;box-shadow:0 8px 24px rgba(15,23,42,.2);cursor:pointer;display:flex;align-items:center;justify-content:center;transition:transform .15s ease,box-shadow .15s ease}",
        ".jw-launcher:hover{transform:translateY(-1px);box-shadow:0 12px 28px rgba(15,23,42,.28)}",
        ".jw-input:focus,.jw-email-input:focus{border-color:rgba(0,0,0,.2);outline:none}.jw-launcher:focus-visible,.jw-close:focus-visible,.jw-send:focus-visible,.jw-start:focus-visible,.jw-input:focus-visible,.jw-email-input:focus-visible{outline:2px solid " + cfg.accent + ";outline-offset:2px}",
        ".jw-icon{width:25px;height:25px;display:block}",
        ".jw-badge{position:absolute;top:-4px;" + opposite + ":-4px;min-width:18px;height:18px;padding:0 4px;border-radius:4px;background:#ef4444;color:#fff;font:700 11px/18px system-ui;text-align:center;border:2px solid #fff;display:none}",
        ".jw-badge.show{display:block}",
        ".jw-panel{position:absolute;bottom:72px;" + side + ":0;width:376px;height:584px;max-height:min(584px,calc(100vh - 108px));background:#fff;border:1px solid rgba(0,0,0,.08);border-radius:10px;box-shadow:0 16px 48px rgba(0,0,0,.12);display:none;overflow:hidden;flex-direction:column}",
        ".jw-panel.open{display:flex}",
        ".jw-head{min-height:72px;padding:14px 16px;background:#0a0a0b;color:#fff;display:flex;align-items:center;gap:12px}",
        ".jw-avatar{width:38px;height:38px;border-radius:8px;background:" + cfg.accent + ";display:flex;align-items:center;justify-content:center;font-weight:800;color:#fff;flex:0 0 auto}",
        ".jw-head-text{min-width:0;flex:1}",
        ".jw-title{font-size:15px;font-weight:750;line-height:1.2;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}",
        ".jw-sub{font-size:12px;color:rgba(255,255,255,.5);margin-top:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}",
        ".jw-close{width:34px;height:34px;border:0;border-radius:6px;background:rgba(255,255,255,.08);color:#fff;cursor:pointer;font-size:20px;line-height:1}",
        ".jw-body{flex:1;min-height:0;display:flex;flex-direction:column;background:#fafafa}",
        ".jw-email{padding:18px;display:none;gap:10px;flex-direction:column}",
        ".jw-email.show{display:flex}",
        ".jw-email h3{margin:0;color:#172033;font-size:16px;line-height:1.3}",
        ".jw-email p{margin:0;color:#6b6b6b;font-size:13px;line-height:1.45}",
        ".jw-email-input,.jw-input{width:100%;border:1px solid rgba(0,0,0,.1);border-radius:6px;background:#fff;color:#172033;font:14px system-ui;padding:11px 12px;box-sizing:border-box}",
        ".jw-start,.jw-send{border:0;border-radius:6px;background:" + cfg.accent + ";color:#fff;font-weight:700;cursor:pointer}",
        ".jw-start{padding:11px 12px}",
        ".jw-privacy{font-size:11px;line-height:1.4;color:#6b6b6b}",
        ".jw-privacy a{color:" + cfg.accent + ";text-decoration:none}",
        ".jw-error{display:none;color:#b91c1c;font-size:12px;line-height:1.35}",
        ".jw-error.show{display:block}",
        ".jw-msgs{flex:1;min-height:0;overflow:auto;padding:14px;display:flex;flex-direction:column;gap:10px;scroll-behavior:smooth}",
        ".jw-msg{max-width:82%;padding:10px 12px;border-radius:8px;font-size:14px;line-height:1.42;white-space:pre-wrap;overflow-wrap:anywhere;box-shadow:0 1px 2px rgba(0,0,0,.04)}",
        ".jw-msg.bot{align-self:flex-start;background:#fff;color:#172033;border:1px solid rgba(0,0,0,.06)}",
        ".jw-msg.user{align-self:flex-end;background:" + cfg.accent + ";color:#fff}",
        ".jw-time{display:block;margin-top:5px;font-size:10px;opacity:.5}",
        ".jw-typing{display:none;align-self:flex-start;background:#fff;border:1px solid rgba(0,0,0,.06);color:#6b6b6b;border-radius:8px;padding:9px 11px;font-size:13px}",
        ".jw-typing.show{display:block}",
        ".jw-composer{display:flex;gap:8px;padding:12px;border-top:1px solid rgba(0,0,0,.06);background:#fff}",
        ".jw-send{width:44px;flex:0 0 44px;display:flex;align-items:center;justify-content:center}",
        ".jw-send:disabled{opacity:.55;cursor:default}",
        ".jw-footer{padding:0 12px 10px;background:#fff;color:#999;font-size:11px;text-align:center}",
        ".jw-footer a{color:#6b6b6b;text-decoration:none}",
        ".jw-followup{align-self:flex-start;background:#fff;border:1px solid rgba(0,0,0,.06);border-radius:8px;padding:10px 12px;margin-top:4px}",
        ".jw-followup-text{font-size:13px;color:#172033;margin-bottom:8px;line-height:1.3}",
        ".jw-followup-btns{display:flex;gap:6px}",
        ".jw-followup-btn{padding:6px 12px;border-radius:6px;border:1px solid rgba(0,0,0,.1);background:#fafafa;color:#172033;font-size:12px;font-weight:600;cursor:pointer;line-height:1}",
        ".jw-followup-btn:hover{background:rgba(0,0,0,.04)}",
        ".jw-rating{align-self:flex-start;background:#fff;border:1px solid rgba(0,0,0,.06);border-radius:8px;padding:14px;margin-top:4px;max-width:260px}",
        ".jw-rating-title{font-size:13px;font-weight:600;color:#172033;margin-bottom:10px;text-align:center}",
        ".jw-rating-btns{display:flex;gap:10px;justify-content:center;margin-bottom:10px}",
        ".jw-rating-btn{width:44px;height:44px;border-radius:50%;border:2px solid rgba(0,0,0,.1);background:#fff;cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:20px;transition:all .15s ease}",
        ".jw-rating-btn:hover{transform:scale(1.1);border-color:rgba(0,0,0,.2)}",
        ".jw-rating-btn.selected-up{border-color:#22c55e;background:#f0fdf4}",
        ".jw-rating-btn.selected-down{border-color:#ef4444;background:#fef2f2}",
        ".jw-rating-feedback{margin-top:8px}",
        ".jw-rating-textarea{width:100%;border:1px solid rgba(0,0,0,.1);border-radius:6px;padding:8px;font-size:12px;resize:none;font-family:inherit;box-sizing:border-box;min-height:60px}",
        ".jw-rating-submit{margin-top:6px;width:100%;padding:7px;border-radius:6px;border:0;background:#0a0a0b;color:#fff;font-size:12px;font-weight:600;cursor:pointer}",
        ".jw-rating-submit:disabled{opacity:.5;cursor:default}",
        ".jw-rating-thanks{text-align:center;font-size:13px;color:#16a34a;font-weight:500;padding:8px 0}",
        "@media (max-width:520px){.jw-wrap{left:12px;right:12px;bottom:12px}.jw-panel{position:fixed;left:10px;right:10px;bottom:78px;width:auto;height:calc(100vh - 104px);max-height:none}.jw-launcher{margin-" + side + ":auto}}",
        "@media (prefers-reduced-motion:reduce){.jw-launcher,.jw-msgs{transition:none;scroll-behavior:auto}}"
      ].join("");
    }

    _render() {
      this.attachShadow({ mode: "open" });
      this._buildCSS();
      var cfg = this._cfg;
      var iconHtml = this._launcherIconHtml();
      var baseHref = esc(cfg.baseUrl);

      this.shadowRoot.innerHTML =
        '<style>' + this._css + '</style>' +
        '<div class="jw-wrap">' +
          '<section class="jw-panel" role="dialog" aria-modal="false" aria-label="' + esc(cfg.title) + '">' +
            '<header class="jw-head">' +
              '<div class="jw-avatar" aria-hidden="true">J</div>' +
              '<div class="jw-head-text"><div class="jw-title">' + esc(cfg.title) + '</div>' + (cfg.subtitle ? '<div class="jw-sub">' + esc(cfg.subtitle) + '</div>' : '') + '</div>' +
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
              '<div class="jw-footer"><a href="' + baseHref + '" target="_blank" rel="noopener">Powered by Jeeves</a></div>' +
            '</div>' +
          '</section>' +
          '<button class="jw-launcher" type="button" aria-label="Open support chat" aria-expanded="false">' +
            iconHtml +
            '<span class="jw-badge"></span>' +
          '</button>' +
        '</div>';

      this._els = {
        panel: this.shadowRoot.querySelector(".jw-panel"),
        launcher: this.shadowRoot.querySelector(".jw-launcher"),
        badge: this.shadowRoot.querySelector(".jw-badge"),
        closeBtn: this.shadowRoot.querySelector(".jw-close"),
        emailForm: this.shadowRoot.querySelector(".jw-email"),
        emailInput: this.shadowRoot.querySelector(".jw-email-input"),
        emailError: this.shadowRoot.querySelector("[data-email-error]"),
        msgsEl: this.shadowRoot.querySelector(".jw-msgs"),
        typingEl: this.shadowRoot.querySelector(".jw-typing"),
        composer: this.shadowRoot.querySelector(".jw-composer"),
        input: this.shadowRoot.querySelector(".jw-input"),
        sendBtn: this.shadowRoot.querySelector(".jw-send"),
      };
    }

    _bindEvents() {
      var self = this;
      var els = this._els;

      els.launcher.addEventListener("click", function () { self.toggle(); });
      els.closeBtn.addEventListener("click", function () { self.close(); });

      els.emailForm.addEventListener("submit", function (e) {
        e.preventDefault();
        var value = (els.emailInput.value || "").trim();
        if (!isEmailish(value)) {
          els.emailError.classList.add("show");
          els.emailInput.focus();
          return;
        }
        self.identify({ user_id: value });
        self._renderIdentity();
        self._focusInput();
      });

      els.composer.addEventListener("submit", function (e) {
        e.preventDefault();
        self.send((els.input.value || "").trim());
      });

      els.msgsEl.addEventListener("click", function (e) {
        var btn = e.target.closest("[data-followup-yes]");
        if (btn) {
          self._handleFollowup(parseInt(btn.getAttribute("data-followup-idx"), 10), true);
          return;
        }
        btn = e.target.closest("[data-followup-no]");
        if (btn) {
          self._handleFollowup(parseInt(btn.getAttribute("data-followup-idx"), 10), false);
          return;
        }
        btn = e.target.closest("[data-rating-value]");
        if (btn) {
          self._handleRate(parseInt(btn.getAttribute("data-rating-idx"), 10), btn.getAttribute("data-rating-value"));
          return;
        }
        btn = e.target.closest("[data-rating-submit-idx]");
        if (btn) {
          self._handleSubmitRating(parseInt(btn.getAttribute("data-rating-submit-idx"), 10));
        }
      });

      document.addEventListener("keydown", function (e) {
        if (e.key === "Escape" && self._state.open) self.close();
      });
    }

    _bindCustomLaunchers() {
      var sel = this._cfg.customLauncher;
      if (!sel) return;
      var self = this;
      try {
        var nodes = document.querySelectorAll(sel);
        for (var i = 0; i < nodes.length; i += 1) {
          nodes[i].addEventListener("click", function (e) {
            e.preventDefault();
            self.open();
          });
        }
      } catch (e) {
        console.warn("[Jeeves] invalid custom launcher selector", sel);
      }
    }

    // ── Public API ──

    open() {
      this._state.open = true;
      this._state.unread = 0;
      this._els.panel.classList.add("open");
      this._els.launcher.setAttribute("aria-expanded", "true");
      this._updateBadge();
      this._renderIdentity();
      var self = this;
      setTimeout(function () { self._focusInput(); }, 50);
    }

    close() {
      this._state.open = false;
      this._els.panel.classList.remove("open");
      this._els.launcher.setAttribute("aria-expanded", "false");
      this._els.launcher.focus();
    }

    toggle() {
      this._state.open ? this.close() : this.open();
    }

    identify(data) {
      if (!data || typeof data !== "object") return;
      var value = data.user_id || data.email || data.id;
      if (value) {
        this._state.userId = String(value);
        stoSet(this._keys().user, this._state.userId);
      }
      var reserved = ["user_id", "email", "id", "message", "tenant_id", "channel"];
      var changed = false;
      for (var k in data) {
        if (!data.hasOwnProperty(k)) continue;
        if (reserved.indexOf(k) !== -1) continue;
        this._state.extraFields[k] = data[k];
        changed = true;
      }
      if (changed) stoSet(this._keys().extraFields, this._state.extraFields);
      this._renderIdentity();
    }

    send(text) {
      if (!text || this._state.sending) return;
      var cfg = this._cfg;
      var state = this._state;
      var els = this._els;
      if (cfg.emailRequired && !state.userId) {
        this.open();
        els.emailInput.focus();
        return;
      }
      els.input.value = "";
      state.resolvedPending = false;
      if (state.followUpTimeout) clearTimeout(state.followUpTimeout);
      this._addMessage(text, "user", true);
      this._setSending(true);
      this._setTyping(true);

      var body = {
        tenant_id: cfg.tenant,
        user_id: state.userId || "anonymous",
        message: text,
        channel: cfg.channel,
      };
      var hasExtra = false;
      for (var k in state.extraFields) {
        if (state.extraFields.hasOwnProperty(k) && state.extraFields[k] != null) { hasExtra = true; break; }
      }
      if (hasExtra) body.extra_fields = state.extraFields;

      var self = this;
      postJson(cfg.baseUrl + "/widget/chat", body, 30000).then(function (data) {
        var response = asText(data.response, "I could not produce a response.");
        self._addMessage(response, "bot", true);
        if (data.resolution === "resolved") {
          var hasQuestion = /[?]\s*$/.test(response.trim());
          if (!hasQuestion) self._scheduleFollowUp();
        }
      }).catch(function (err) {
        self._addMessage(err && err.message ? err.message : "Network error. Please try again.", "bot", true);
      }).then(function () {
        self._setTyping(false);
        self._setSending(false);
        self._focusInput();
      });
    }

    reset() {
      var state = this._state;
      state.userId = "";
      state.extraFields = {};
      state.messages = [];
      state.unread = 0;
      state.resolvedPending = false;
      state.ratingState = null;
      if (state.followUpTimeout) clearTimeout(state.followUpTimeout);
      var k = this._keys();
      stoRemove(k.user);
      stoRemove(k.messages);
      stoRemove(k.seenInbox);
      stoRemove(k.extraFields);
      stoRemove("jeeves:rating:" + this._cfg.tenant);
      this._renderIdentity();
      this._renderMessages();
      this._updateBadge();
    }

    getUnread() {
      return this._state.unread;
    }

    // ── Internal ──

    _renderIdentity() {
      if (!this._els.emailForm) return;
      var needsEmail = this._cfg.emailRequired && !this._state.userId;
      this._els.emailForm.classList.toggle("show", needsEmail);
      this._els.msgsEl.style.display = needsEmail ? "none" : "flex";
      this._els.composer.style.display = needsEmail ? "none" : "flex";
      if (!needsEmail && !this._state.messages.length) this._addMessage(this._cfg.greeting, "bot", true);
    }

    _addMessage(text, role, persist) {
      var clean = (typeof text === "object") ? text : asText(text, "").slice(0, 4000);
      if (!clean) return;
      var state = this._state;
      if (typeof clean === "object") {
        state.messages.push(clean);
      } else {
        state.messages.push({ role: role === "user" ? "user" : "bot", text: clean, at: nowIso() });
      }
      if (state.messages.length > 80) state.messages = state.messages.slice(state.messages.length - 80);
      if (persist !== false) this._saveMessages();
      this._renderMessages();
      if (!state.open && role !== "user") {
        state.unread += 1;
        this._updateBadge();
      }
    }

    _renderMessages() {
      if (!this._els.msgsEl) return;
      var self = this;
      var html = this._state.messages.map(function (m, idx) {
        if (m.type === "followup") return self._renderFollowupCard(m, idx);
        if (m.type === "rating") return self._renderRatingCard(m, idx);
        var time = "";
        try { time = new Date(m.at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }); } catch (e) {}
        return '<div class="jw-msg ' + (m.role === "user" ? "user" : "bot") + '">' +
          esc(m.text) + '<span class="jw-time">' + esc(time) + '</span></div>';
      }).join("");
      this._els.msgsEl.innerHTML = html;
      this._els.msgsEl.scrollTop = this._els.msgsEl.scrollHeight;
    }

    _renderFollowupCard(m, idx) {
      if (m.dismissed) return "";
      var btns = '<div class="jw-followup-btns">' +
        '<button class="jw-followup-btn" data-followup-idx="' + idx + '" data-followup-yes>Yes</button>' +
        '<button class="jw-followup-btn" data-followup-idx="' + idx + '" data-followup-no>No, all clear</button>' +
      '</div>';
      return '<div class="jw-followup">' +
        '<div class="jw-followup-text">' + esc(m.text || "Any other questions?") + '</div>' +
        btns +
      '</div>';
    }

    _renderRatingCard(m, idx) {
      if (m.submitted) {
        return '<div class="jw-rating"><div class="jw-rating-thanks">Thanks for your feedback!</div></div>';
      }
      var upClass = m.rating === "thumbs_up" ? "selected-up" : "";
      var downClass = m.rating === "thumbs_down" ? "selected-down" : "";
      var html = '<div class="jw-rating">' +
        '<div class="jw-rating-title">Rate this response</div>' +
        '<div class="jw-rating-btns">' +
          '<button class="jw-rating-btn ' + upClass + '" data-rating-idx="' + idx + '" data-rating-value="thumbs_up" aria-label="Good response">👍</button>' +
          '<button class="jw-rating-btn ' + downClass + '" data-rating-idx="' + idx + '" data-rating-value="thumbs_down" aria-label="Bad response">👎</button>' +
        '</div>';
      if (m.rating) {
        html += '<div class="jw-rating-feedback">' +
          '<textarea class="jw-rating-textarea" placeholder="Comment (optional)" maxlength="500">' + esc(m.feedback || "") + '</textarea>' +
          '<button class="jw-rating-submit" data-rating-submit-idx="' + idx + '"' + (m.feedbackSubmitted ? ' disabled' : '') + '>' +
            (m.feedbackSubmitted ? "Submitted" : "Submit") +
          '</button>' +
        '</div>';
      }
      html += '</div>';
      return html;
    }

    _setTyping(value) {
      this._els.typingEl.classList.toggle("show", !!value);
      this._els.msgsEl.scrollTop = this._els.msgsEl.scrollHeight;
    }

    _setSending(value) {
      this._state.sending = !!value;
      this._els.sendBtn.disabled = this._state.sending;
      this._els.input.disabled = this._state.sending;
    }

    _scheduleFollowUp() {
      var state = this._state;
      if (state.followUpTimeout) clearTimeout(state.followUpTimeout);
      var self = this;
      state.followUpTimeout = setTimeout(function () {
        if (state.resolvedPending) return;
        state.resolvedPending = true;
        self._addMessage({ type: "followup", text: "Any other questions?", dismissed: false }, "bot", true);
      }, 180000);
    }

    _handleFollowup(idx, hasMore) {
      this._state.messages[idx].dismissed = true;
      this._saveMessages();
      this._renderMessages();
      var self = this;
      if (!hasMore) {
        setTimeout(function () {
          if (self._state.ratingState && self._state.ratingState.submitted) return;
          self._addMessage({ type: "rating", rating: null, feedback: "", submitted: false }, "bot", true);
        }, 600);
      } else {
        this._state.resolvedPending = false;
        this._els.input.focus();
      }
    }

    _handleRate(idx, value) {
      var m = this._state.messages[idx];
      m.rating = value;
      m.submitted = true;
      this._saveMessages();
      this._renderMessages();
      this._state.ratingState = { index: idx, value: value, submitted: false };
      stoSet("jeeves:rating:" + this._cfg.tenant, this._state.ratingState);
      var self = this;
      postJson(this._cfg.baseUrl + "/widget/rating", {
        tenant_id: this._cfg.tenant,
        user_id: this._state.userId || "anonymous",
        rating: value,
      }).catch(function () {});
    }

    _handleSubmitRating(idx) {
      var m = this._state.messages[idx];
      if (!m || !m.rating) return;
      var ta = this.shadowRoot.querySelector(".jw-rating-textarea");
      var feedback = ta ? (ta.value || "").slice(0, 500) : "";
      m.feedback = feedback;
      m.feedbackSubmitted = true;
      this._saveMessages();
      this._renderMessages();
      if (this._state.ratingState && this._state.ratingState.index === idx) {
        this._state.ratingState.feedback = feedback;
        this._state.ratingState.submitted = true;
        stoSet("jeeves:rating:" + this._cfg.tenant, this._state.ratingState);
      }
      postJson(this._cfg.baseUrl + "/widget/rating", {
        tenant_id: this._cfg.tenant,
        user_id: this._state.userId || "anonymous",
        rating: m.rating,
        feedback: feedback,
      }).catch(function () {});
    }

    _pollInbox() {
      if (!this._state.userId) return;
      var self = this;
      var viewing = self._state.open ? 'true' : 'false';
      fetch(this._cfg.baseUrl + "/widget/inbox?tenant_id=" + encodeURIComponent(this._cfg.tenant) + "&user_id=" + encodeURIComponent(this._state.userId) + "&viewing=" + viewing)
        .then(function (r) { return r.ok ? r.json() : { messages: [] }; })
        .then(function (data) {
          var seen = stoGet(self._keys().seenInbox, []);
          if (!Array.isArray(seen)) seen = [];
          var changed = false;
          (data.messages || []).forEach(function (m) {
            if (seen.indexOf(m.id) >= 0) return;
            seen.push(m.id);
            changed = true;
            self._addMessage(m.message, "bot", true);
          });
          if (changed) stoSet(self._keys().seenInbox, seen.slice(-200));
        })
        .catch(function () {});
    }

    _updateBadge() {
      var u = this._state.unread;
      this._els.badge.textContent = u > 9 ? "9+" : String(u);
      this._els.badge.classList.toggle("show", u > 0);
    }

    _focusInput() {
      if (this._cfg.emailRequired && !this._state.userId) this._els.emailInput.focus();
      else this._els.input.focus();
    }
  }

  // ════════════════════════════════════════════════════════════════
  // Register Web Component
  // ════════════════════════════════════════════════════════════════

  if (typeof customElements !== "undefined") {
    customElements.define("jeeves-widget", JeevesWidget);
  }

  // ════════════════════════════════════════════════════════════════
  // Backward compat: auto-create from legacy async script tag
  // ════════════════════════════════════════════════════════════════

  (function () {
    if (typeof customElements === "undefined" || !customElements.get("jeeves-widget")) return;
    var script = document.currentScript;
    if (!script) {
      var scripts = document.getElementsByTagName("script");
      script = scripts[scripts.length - 1];
    }
    var tenant = script.getAttribute("data-tenant-id");
    if (!tenant) return;

    var el = document.createElement("jeeves-widget");
    el.setAttribute("tenant", tenant);
    var map = {
      "data-title": "title", "data-subtitle": "subtitle", "data-accent": "accent",
      "data-position": "position", "data-greeting": "greeting",
      "data-privacy-url": "privacy-url", "data-custom-launcher": "custom-launcher",
      "data-z-index": "z-index", "data-email-required": "email-required",
      "data-user-id": "user-id", "data-channel": "channel", "data-icon": "icon",
      "data-base-url": "base-url",
    };
    for (var dataAttr in map) {
      var val = script.getAttribute(dataAttr);
      if (val != null) el.setAttribute(map[dataAttr], val);
    }
    document.body.appendChild(el);
  })();

  // ════════════════════════════════════════════════════════════════
  // Public API proxy (controls first instance on page)
  // ════════════════════════════════════════════════════════════════

  function _first() {
    try { return document.querySelector("jeeves-widget"); } catch (e) { return null; }
  }

  window.JeevesWidget = {
    __loaded: true,
    open: function () { var w = _first(); if (w) w.open(); },
    close: function () { var w = _first(); if (w) w.close(); },
    toggle: function () { var w = _first(); if (w) w.toggle(); },
    identify: function (d) { var w = _first(); if (w) w.identify(d); },
    send: function (t) { var w = _first(); if (w) w.send(t); },
    reset: function () { var w = _first(); if (w) w.reset(); },
    unread: function () { var w = _first(); return w ? w.getUnread() : 0; },
  };
})();
