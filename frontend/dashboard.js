(function () {
  "use strict";

  var API = window.location.origin;
  var token = "";
  var tenantId = "";

  // ---- API helpers ----
  function api(path, opts) {
    opts = opts || {};
    opts.headers = opts.headers || {};
    if (token) opts.headers["Authorization"] = "Bearer " + token;
    opts.headers["Content-Type"] = "application/json";
    return fetch(API + path, opts).then(function (r) {
      return r.json().then(function (data) {
        if (!r.ok) throw new Error(data.detail || "Request failed: " + r.status);
        return data;
      });
    });
  }

  function showMsg(id, text, type) {
    var el = document.getElementById(id);
    if (!el) return;
    el.textContent = text;
    el.className = "form-msg show " + type;
    if (type === "success") setTimeout(function () { el.className = "form-msg"; }, 4000);
  }

  function clearMsg(id) {
    var el = document.getElementById(id);
    if (el) el.className = "form-msg";
  }

  // ---- Screens ----
  function showScreen(name) {
    document.getElementById("login-screen").classList.toggle("hidden", name !== "login");
    document.getElementById("dashboard-screen").classList.toggle("hidden", name !== "dashboard");
  }

  // ---- Login ----
  function initLogin() {
    var saved = sessionStorage.getItem("jeeves_token");
    var savedTenant = sessionStorage.getItem("jeeves_tenant");
    if (saved) {
      token = saved;
      tenantId = savedTenant || "";
      showScreen("dashboard");
      initDashboard();
      return;
    }

    document.getElementById("login-form").addEventListener("submit", function (e) {
      e.preventDefault();
      var email = document.getElementById("login-email").value.trim();
      var password = document.getElementById("login-password").value;
      var errEl = document.getElementById("login-error");
      errEl.textContent = "";

      api("/login", {
        method: "POST",
        body: JSON.stringify({ email: email, password: password }),
      }).then(function (data) {
        token = data.access_token;
        tenantId = data.tenant_id || "";
        sessionStorage.setItem("jeeves_token", token);
        if (data.tenant_id) sessionStorage.setItem("jeeves_tenant", data.tenant_id);
        showScreen("dashboard");
        initDashboard();
      }).catch(function (err) {
        errEl.textContent = err.message;
      });
    });

    document.getElementById("logout-btn").addEventListener("click", function () {
      token = "";
      tenantId = "";
      sessionStorage.removeItem("jeeves_token");
      sessionStorage.removeItem("jeeves_tenant");
      showScreen("login");
    });
  }

  // ---- Tabs ----
  function initTabs() {
    document.querySelectorAll(".tab").forEach(function (tab) {
      tab.addEventListener("click", function () {
        document.querySelectorAll(".tab").forEach(function (t) { t.classList.remove("active"); });
        document.querySelectorAll(".tab-content").forEach(function (c) { c.classList.remove("active"); });
        tab.classList.add("active");
        var target = document.getElementById("tab-" + tab.dataset.tab);
        if (target) target.classList.add("active");
      });
    });
  }

  // ---- Dashboard init ----
  function initDashboard() {
    initTabs();
    initConnectors();
    initWebhooks();
    initWriteback();
    initCRM();
    loadOverview();
  }

  // ---- Connectors ----
  function initConnectors() {
    var providers = ["shopify", "woocommerce", "stripe"];
    providers.forEach(function (p) { setupConnectorForm(p); });
    loadConnectors();
  }

  function setupConnectorForm(provider) {
    var form = document.getElementById("form-" + provider);
    var btnConnect = document.getElementById("btn-connect-" + provider);
    var btnTest = document.getElementById("btn-test-" + provider);
    var btnDisconnect = document.getElementById("btn-disconnect-" + provider);
    var msgId = "msg-" + provider;

    if (!form) return;

    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var creds = {};
      if (provider === "shopify") {
        creds = {
          shop_domain: document.getElementById("shopify-shop").value.trim(),
          access_token: document.getElementById("shopify-token").value.trim(),
        };
      } else if (provider === "woocommerce") {
        creds = {
          store_url: document.getElementById("woo-url").value.trim(),
          consumer_key: document.getElementById("woo-key").value.trim(),
          consumer_secret: document.getElementById("woo-secret").value.trim(),
        };
      } else if (provider === "stripe") {
        creds = {
          secret_key: document.getElementById("stripe-key").value.trim(),
        };
      }

      var meta = {};
      if (provider === "shopify") meta.domain = creds.shop_domain;

      btnConnect.disabled = true;
      clearMsg(msgId);

      api("/integrations/native/" + provider, {
        method: "POST",
        body: JSON.stringify({
          provider: provider,
          credentials: creds,
          meta: meta,
        }),
      }).then(function () {
        showMsg(msgId, "Connected successfully!", "success");
        loadConnectors();
      }).catch(function (err) {
        showMsg(msgId, err.message, "error");
      }).finally(function () {
        btnConnect.disabled = false;
      });
    });

    btnTest.addEventListener("click", function () {
      clearMsg(msgId);
      api("/integrations/native/" + provider + "/test", {
        method: "POST",
      }).then(function (data) {
        if (data.ok) showMsg(msgId, "Connection test passed!", "success");
        else showMsg(msgId, "Test failed: " + (data.error || "unknown"), "error");
      }).catch(function (err) {
        showMsg(msgId, err.message, "error");
      });
    });

    btnDisconnect.addEventListener("click", function () {
      if (!confirm("Disconnect " + provider + "?")) return;
      clearMsg(msgId);
      api("/integrations/native/" + provider, { method: "DELETE" }).then(function () {
        showMsg(msgId, "Disconnected.", "success");
        loadConnectors();
      }).catch(function (err) {
        showMsg(msgId, err.message, "error");
      });
    });
  }

  function loadConnectors() {
    api("/integrations").then(function (data) {
      var connected = {};
      (data.native_connectors || []).forEach(function (nc) {
        connected[nc.provider] = nc.status === "connected";
      });

      ["shopify", "woocommerce", "stripe"].forEach(function (p) {
        var badge = document.getElementById("badge-" + p);
        var btnTest = document.getElementById("btn-test-" + p);
        var btnDisconnect = document.getElementById("btn-disconnect-" + p);
        var btnConnect = document.getElementById("btn-connect-" + p);
        var form = document.getElementById("form-" + p);

        var isConnected = connected[p];
        if (badge) {
          badge.textContent = isConnected ? "Connected" : "Not connected";
          badge.className = "badge " + (isConnected ? "connected" : "disconnected");
        }
        if (btnTest) btnTest.disabled = !isConnected;
        if (btnDisconnect) btnDisconnect.classList.toggle("hidden", !isConnected);
        if (btnConnect) btnConnect.textContent = isConnected ? "Update" : "Connect";
        if (form) {
          var inputs = form.querySelectorAll("input");
          for (var i = 0; i < inputs.length; i++) {
            if (inputs[i].type === "password") inputs[i].value = "";
          }
        }
      });
    }).catch(function () {});
  }

  // ---- Webhooks ----
  function initWebhooks() {
    loadWebhookConfig();

    document.getElementById("form-incoming-webhook").addEventListener("submit", function (e) {
      e.preventDefault();
      var mapping = {};
      try {
        mapping = JSON.parse(document.getElementById("field-mapping").value || "{}");
      } catch (err) {
        showMsg("msg-incoming-webhook", "Invalid JSON in field mapping", "error");
        return;
      }

      api("/integrations/webhook", {
        method: "POST",
        body: JSON.stringify({
          incoming_url: document.getElementById("incoming-url").value.trim() || null,
          incoming_secret: document.getElementById("incoming-secret").value || null,
          field_mapping: mapping,
          enabled: document.getElementById("incoming-enabled").checked,
        }),
      }).then(function () {
        showMsg("msg-incoming-webhook", "Incoming webhook saved!", "success");
        loadWebhookConfig();
      }).catch(function (err) {
        showMsg("msg-incoming-webhook", err.message, "error");
      });
    });

    document.getElementById("form-outgoing-webhook").addEventListener("submit", function (e) {
      e.preventDefault();
      var events = [];
      document.querySelectorAll("#form-outgoing-webhook input[type=checkbox]:checked").forEach(function (cb) {
        if (cb.value && cb.value !== "incoming-enabled" && cb.value !== "outgoing-enabled") events.push(cb.value);
      });

      api("/integrations/webhook", {
        method: "POST",
        body: JSON.stringify({
          outgoing_url: document.getElementById("outgoing-url").value.trim() || null,
          outgoing_secret: document.getElementById("outgoing-secret").value || null,
          events: events,
          enabled: document.getElementById("outgoing-enabled").checked,
        }),
      }).then(function () {
        showMsg("msg-outgoing-webhook", "Outgoing webhook saved!", "success");
        loadWebhookConfig();
      }).catch(function (err) {
        showMsg("msg-outgoing-webhook", err.message, "error");
      });
    });
  }

  function loadWebhookConfig() {
    api("/integrations/webhook").then(function (data) {
      document.getElementById("incoming-url").value = data.incoming_url || "";
      document.getElementById("incoming-secret").value = "";
      document.getElementById("incoming-enabled").checked = data.enabled !== false;
      document.getElementById("field-mapping").value = data.field_mapping ? JSON.stringify(data.field_mapping, null, 2) : "{}";

      document.getElementById("outgoing-url").value = data.outgoing_url || "";
      document.getElementById("outgoing-secret").value = "";
      document.getElementById("outgoing-enabled").checked = data.enabled !== false;

      var events = data.events || [];
      document.querySelectorAll("#form-outgoing-webhook input[type=checkbox]").forEach(function (cb) {
        if (cb.value && cb.value !== "incoming-enabled" && cb.value !== "outgoing-enabled") {
          cb.checked = events.indexOf(cb.value) !== -1;
        }
      });
    }).catch(function () {});
  }

  // ---- Writeback ----
  function initWriteback() {
    loadWritebackConfig();

    document.getElementById("writeback-type").addEventListener("change", function () {
      var type = this.value;
      document.getElementById("writeback-hubspot-note-group").style.display = (type === "hubspot_note" || type === "webhook") ? "" : "none";
      document.getElementById("writeback-webhook-url-group").style.display = type === "webhook" ? "" : "none";
    });

    document.getElementById("form-writeback").addEventListener("submit", function (e) {
      e.preventDefault();
      var type = document.getElementById("writeback-type").value;
      api("/integrations/writeback", {
        method: "POST",
        body: JSON.stringify({
          type: type,
          hubspot_note_enabled: document.getElementById("writeback-hubspot-note").checked,
          webhook_url: document.getElementById("writeback-webhook-url").value.trim() || null,
        }),
      }).then(function () {
        showMsg("msg-writeback", "Writeback saved!", "success");
        loadWritebackConfig();
      }).catch(function (err) {
        showMsg("msg-writeback", err.message, "error");
      });
    });
  }

  function loadWritebackConfig() {
    api("/integrations/writeback").then(function (data) {
      document.getElementById("writeback-type").value = data.type || "off";
      document.getElementById("writeback-hubspot-note").checked = !!data.hubspot_note_enabled;
      document.getElementById("writeback-webhook-url").value = data.webhook_url || "";
      // Trigger change to show/hide fields
      document.getElementById("writeback-type").dispatchEvent(new Event("change"));
    }).catch(function () {});
  }

  // ---- CRM ----
  function initCRM() {
    loadCRMConfig();

    document.getElementById("primary-identifier").addEventListener("change", function () {
      document.getElementById("identifier-field-group").style.display = this.value === "custom" ? "" : "none";
    });

    document.getElementById("form-crm").addEventListener("submit", function (e) {
      e.preventDefault();
      var identifier = document.getElementById("primary-identifier").value;
      var body = { provider: "custom_rest", primary_identifier: identifier };
      if (identifier === "custom") {
        body.capabilities = { identifier_field: document.getElementById("identifier-field").value.trim() };
      }

      api("/crm/config", {
        method: "POST",
        body: JSON.stringify(body),
      }).then(function () {
        showMsg("msg-crm", "CRM settings saved!", "success");
      }).catch(function (err) {
        showMsg("msg-crm", err.message, "error");
      });
    });
  }

  function loadCRMConfig() {
    api("/crm/config").then(function (data) {
      document.getElementById("primary-identifier").value = data.primary_identifier || "email";
      if (data.capabilities && data.capabilities.identifier_field) {
        document.getElementById("identifier-field").value = data.capabilities.identifier_field;
      }
      document.getElementById("primary-identifier").dispatchEvent(new Event("change"));
    }).catch(function () {});
  }

  // ---- Overview ----
  function loadOverview() {
    var container = document.getElementById("overview-status");
    api("/integrations").then(function (data) {
      var connectors = data.native_connectors || [];
      var hasWebhook = data.webhook_config && data.webhook_config.enabled;
      var writeback = data.writeback_config && data.writeback_config.type !== "off";

      var items = [];
      connectors.forEach(function (nc) {
        items.push('<div class="status-item"><h4>' + nc.provider + '</h4><div class="status-value">' +
          (nc.status === "connected" ? "Connected" : "Error") + '</div><div class="status-label">Updated: ' +
          new Date(nc.updated_at).toLocaleString() + '</div></div>');
      });

      items.push('<div class="status-item"><h4>Incoming Webhook</h4><div class="status-value">' +
        (hasWebhook ? "Active" : "Inactive") + '</div></div>');
      items.push('<div class="status-item"><h4>Writeback</h4><div class="status-value">' +
        (writeback ? "Active" : "Inactive") + '</div></div>');

      container.innerHTML = items.join("");
    }).catch(function () {
      container.innerHTML = '<p class="error-msg">Failed to load status.</p>';
    });
  }

  // ---- Boot ----
  showScreen("login");
  initLogin();
})();
