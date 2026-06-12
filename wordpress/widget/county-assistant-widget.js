/*
 * County Assistant — standalone chat widget (prototype)
 * ------------------------------------------------------
 * A dependency-free floating chat widget you can paste into a WordPress theme
 * footer or any HTML page. It renders a launcher button and a chat panel, calls
 * a backend endpoint, and persists the session id in localStorage.
 *
 * Configuration (set BEFORE this script loads):
 *   window.CountyAssistant = {
 *     endpoint: "https://your-apim.azure-api.net/county-assistant/chat", // or a WP proxy URL
 *     mode: "browser-direct" | "proxy",   // default "browser-direct"
 *     nonce: "<wp_rest nonce>",            // only for proxy mode
 *     greeting: "How can I help with county services?",
 *     title: "County Assistant"
 *   };
 *
 * The WordPress plugin injects an equivalent `CountyAssistantConfig` object; this
 * file reads either name.
 *
 * SECURITY: In "browser-direct" mode the endpoint must be a public, tightly-scoped
 * APIM product key route (rate-limited + content-safe). Prefer "proxy" mode (the
 * WordPress REST proxy) so no key is exposed to the browser. See
 * docs/wordpress-integration.md.
 */
(function () {
  "use strict";

  var cfg = window.CountyAssistant || window.CountyAssistantConfig || {};
  var ENDPOINT = cfg.endpoint || "";
  var MODE = cfg.mode || "browser-direct";
  var NONCE = cfg.nonce || "";
  var TITLE = cfg.title || "County Assistant";
  var GREETING = cfg.greeting || "Hi! I can help with county services. Ask me anything.";
  var SESSION_KEY = "county_assistant_session";
  var DISCLAIMER =
    "AI-generated using synthetic county data. Verify important details. For emergencies call 911.";

  if (!ENDPOINT) {
    console.warn("[CountyAssistant] No endpoint configured; widget disabled.");
    return;
  }

  function sessionId() {
    var id = localStorage.getItem(SESSION_KEY);
    if (!id) {
      id = (crypto.randomUUID && crypto.randomUUID()) || String(Date.now());
      localStorage.setItem(SESSION_KEY, id);
    }
    return id;
  }

  function el(tag, props, children) {
    var node = document.createElement(tag);
    if (props) Object.keys(props).forEach(function (k) {
      if (k === "class") node.className = props[k];
      else if (k === "text") node.textContent = props[k];
      else node.setAttribute(k, props[k]);
    });
    (children || []).forEach(function (c) { node.appendChild(c); });
    return node;
  }

  function addMessage(list, role, text) {
    var bubble = el("div", { class: "ca-msg ca-" + role });
    bubble.textContent = text;
    list.appendChild(bubble);
    list.scrollTop = list.scrollHeight;
    return bubble;
  }

  function renderCitations(list, citations) {
    if (!citations || !citations.length) return;
    var wrap = el("div", { class: "ca-citations" });
    wrap.appendChild(el("div", { class: "ca-citations-title", text: "Sources" }));
    citations.forEach(function (c) {
      var item = c.url
        ? el("a", { class: "ca-cite", href: c.url, target: "_blank", rel: "noopener", text: c.title })
        : el("span", { class: "ca-cite", text: c.title });
      wrap.appendChild(item);
    });
    list.appendChild(wrap);
    list.scrollTop = list.scrollHeight;
  }

  function buildUI() {
    var root = document.getElementById("county-assistant-root") || document.body;

    var launcher = el("button", { class: "ca-launcher", "aria-label": "Open " + TITLE });
    launcher.innerHTML = "&#128172;";

    var panel = el("div", { class: "ca-panel", role: "dialog", "aria-label": TITLE, hidden: "hidden" });
    var header = el("div", { class: "ca-header" }, [
      el("span", { class: "ca-title", text: TITLE }),
    ]);
    var closeBtn = el("button", { class: "ca-close", "aria-label": "Close", text: "\u00D7" });
    header.appendChild(closeBtn);

    var list = el("div", { class: "ca-messages" });
    var form = el("form", { class: "ca-form" });
    var input = el("input", {
      class: "ca-input", type: "text", placeholder: "Ask about county services…",
      "aria-label": "Your message", maxlength: "1000", autocomplete: "off",
    });
    var send = el("button", { class: "ca-send", type: "submit", text: "Send" });
    form.appendChild(input);
    form.appendChild(send);

    var footer = el("div", { class: "ca-disclaimer", text: DISCLAIMER });

    panel.appendChild(header);
    panel.appendChild(list);
    panel.appendChild(form);
    panel.appendChild(footer);
    root.appendChild(launcher);
    root.appendChild(panel);

    addMessage(list, "assistant", GREETING);

    function toggle(open) {
      if (open) { panel.removeAttribute("hidden"); input.focus(); }
      else { panel.setAttribute("hidden", "hidden"); }
    }
    launcher.addEventListener("click", function () { toggle(panel.hasAttribute("hidden")); });
    closeBtn.addEventListener("click", function () { toggle(false); });

    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var text = input.value.trim();
      if (!text) return;
      input.value = "";
      addMessage(list, "user", text);
      send.disabled = true;
      var pending = addMessage(list, "assistant", "…");

      sendMessage(text)
        .then(function (data) {
          pending.textContent = data.answer || "Sorry, I couldn't find an answer.";
          renderCitations(list, data.citations);
        })
        .catch(function () {
          pending.textContent = "The assistant is temporarily unavailable. Please try again shortly.";
        })
        .finally(function () { send.disabled = false; input.focus(); });
    });
  }

  function sendMessage(message) {
    var headers = { "Content-Type": "application/json" };
    if (MODE === "proxy" && NONCE) headers["X-WP-Nonce"] = NONCE;

    return fetch(ENDPOINT, {
      method: "POST",
      headers: headers,
      body: JSON.stringify({ message: message, session_id: sessionId() }),
    }).then(function (res) {
      return res.json().then(function (body) {
        if (!res.ok) throw new Error((body && body.error && body.error.message) || "error");
        return body;
      });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", buildUI);
  } else {
    buildUI();
  }
})();
