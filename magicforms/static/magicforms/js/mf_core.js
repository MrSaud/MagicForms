/*
 * MagicForms shared front-end helpers (loaded on every page before page scripts).
 *
 *   MF.csrfToken(root?)            CSRF token from a rendered {% csrf_token %} input or the cookie.
 *   MF.request(url, options)       fetch() wrapper: same-origin credentials, CSRF header, JSON body,
 *                                  resolves {ok, status, data} and never rejects on HTTP errors.
 *   MF.readJson(id)                Parse a {{ value|json_script:"id" }} block (null when missing).
 *   MF.fmt("%(n)s", {n: 1})        Python-style named interpolation for translated strings.
 *   MF.el(tag, className, text)    Tiny element factory.
 *   MF.busy.show(text?) / hide()   The studio's full-page busy overlay when present on the page.
 *   MF.setBusy(button, busy, text) Disable a button and swap its label while a request runs.
 */
(function () {
  "use strict";

  var NETWORK_ERROR = "network";

  function csrfToken(root) {
    var scope = root || document;
    var input = scope.querySelector('input[name="csrfmiddlewaretoken"]');
    if (input && input.value) return input.value;
    var m = document.cookie.match("(?:^|; )csrftoken=([^;]*)");
    return m ? decodeURIComponent(m[1]) : "";
  }

  function request(url, options) {
    var opts = options || {};
    var method = (opts.method || (opts.body !== undefined ? "POST" : "GET")).toUpperCase();
    var headers = { Accept: "application/json" };
    if (method !== "GET" && method !== "HEAD") headers["X-CSRFToken"] = csrfToken(opts.root);
    var init = { method: method, credentials: "same-origin", headers: headers };
    if (opts.body !== undefined) {
      if (opts.body instanceof FormData) {
        init.body = opts.body;
      } else {
        headers["Content-Type"] = "application/json";
        init.body = JSON.stringify(opts.body);
      }
    }
    return fetch(url, init).then(
      function (r) {
        return r
          .json()
          .catch(function () {
            return {};
          })
          .then(function (data) {
            return { ok: r.ok && data.ok !== false, status: r.status, data: data };
          });
      },
      function () {
        return { ok: false, status: 0, data: {}, error: NETWORK_ERROR };
      }
    );
  }

  function readJson(id) {
    var el = document.getElementById(id);
    if (!el) return null;
    try {
      return JSON.parse(el.textContent);
    } catch (e) {
      return null;
    }
  }

  function fmt(template, vars) {
    return String(template || "").replace(/%\((\w+)\)s/g, function (_, k) {
      return vars && vars[k] != null ? vars[k] : "";
    });
  }

  function el(tag, className, text) {
    var n = document.createElement(tag);
    if (className) n.className = className;
    if (text != null) n.textContent = text;
    return n;
  }

  var busy = {
    show: function (text) {
      var overlay = document.getElementById("mf-manage-busy-overlay");
      if (!overlay) return;
      if (text) {
        var t = overlay.querySelector(".mf-manage-busy-overlay__text");
        if (t) t.textContent = text;
      }
      overlay.removeAttribute("hidden");
      document.body.setAttribute("aria-busy", "true");
    },
    hide: function () {
      var overlay = document.getElementById("mf-manage-busy-overlay");
      if (!overlay) return;
      overlay.setAttribute("hidden", "");
      document.body.removeAttribute("aria-busy");
    },
  };

  function setBusy(button, isBusy, busyLabel) {
    if (!button) return;
    if (!button.getAttribute("data-mf-label")) button.setAttribute("data-mf-label", button.textContent);
    button.disabled = !!isBusy;
    button.classList.toggle("is-busy", !!isBusy);
    button.textContent = isBusy ? busyLabel || button.getAttribute("data-mf-label") : button.getAttribute("data-mf-label");
  }

  // Native <details> menus (.mf-tabs__more): close when clicking elsewhere or pressing Escape.
  document.addEventListener("click", function (ev) {
    document.querySelectorAll("details.mf-tabs__more[open]").forEach(function (d) {
      if (!d.contains(ev.target)) d.removeAttribute("open");
    });
  });
  document.addEventListener("keydown", function (ev) {
    if (ev.key !== "Escape") return;
    document.querySelectorAll("details.mf-tabs__more[open]").forEach(function (d) {
      d.removeAttribute("open");
    });
  });

  // Studio left rail: hide/show from the top-bar toggle; remembered per browser in localStorage.
  (function () {
    var KEY = "mf.studio.rail";
    var root = document.documentElement;
    function isHidden() {
      return root.getAttribute("data-mf-rail") === "hidden";
    }
    function paint(button) {
      var hidden = isHidden();
      var label = button.getAttribute(hidden ? "data-label-show" : "data-label-hide") || "";
      button.setAttribute("aria-pressed", hidden ? "true" : "false");
      if (label) {
        button.setAttribute("aria-label", label);
        button.setAttribute("title", label);
      }
    }
    function setHidden(hidden) {
      if (hidden) root.setAttribute("data-mf-rail", "hidden");
      else root.removeAttribute("data-mf-rail");
      try {
        if (hidden) window.localStorage.setItem(KEY, "hidden");
        else window.localStorage.removeItem(KEY);
      } catch (e) {}
    }
    function init() {
      var buttons = document.querySelectorAll("[data-mf-rail-toggle]");
      if (!buttons.length) return;
      buttons.forEach(paint);
      buttons.forEach(function (button) {
        button.addEventListener("click", function () {
          setHidden(!isHidden());
          buttons.forEach(paint);
        });
      });
    }
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
    else init();
  })();

  // Submission page: hide/show the side panel from the page head; remembered per browser.
  (function () {
    var KEY = "mf.submission.side";
    var root = document.documentElement;
    function isHidden() {
      return root.getAttribute("data-mf-side") === "hidden";
    }
    function paint(button) {
      var hidden = isHidden();
      button.setAttribute("aria-pressed", hidden ? "true" : "false");
      button.textContent = button.getAttribute(hidden ? "data-label-show" : "data-label-hide") || button.textContent;
    }
    function init() {
      var buttons = document.querySelectorAll("[data-mf-side-toggle]");
      if (!buttons.length) return;
      // Closed by default; only an explicit "shown" choice keeps it open.
      var shown = false;
      try {
        shown = window.localStorage.getItem(KEY) === "shown";
      } catch (e) {}
      if (shown) root.removeAttribute("data-mf-side");
      else root.setAttribute("data-mf-side", "hidden");
      buttons.forEach(paint);
      buttons.forEach(function (button) {
        button.addEventListener("click", function () {
          var hidden = !isHidden();
          if (hidden) root.setAttribute("data-mf-side", "hidden");
          else root.removeAttribute("data-mf-side");
          try {
            if (hidden) window.localStorage.removeItem(KEY);
            else window.localStorage.setItem(KEY, "shown");
          } catch (e) {}
          buttons.forEach(paint);
        });
      });
    }
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
    else init();
  })();

  window.MF = window.MF || {};
  window.MF.csrfToken = csrfToken;
  window.MF.request = request;
  window.MF.readJson = readJson;
  window.MF.fmt = fmt;
  window.MF.el = el;
  window.MF.busy = busy;
  window.MF.setBusy = setBusy;
  window.MF.NETWORK_ERROR = NETWORK_ERROR;
})();
