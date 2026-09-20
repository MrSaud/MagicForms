/**
 * Studio (/manage/): show full-viewport busy overlay on form submits and primary
 * navigation actions (buttons, exports, pagination, GET links styled as actions).
 * Skips: data-mf-no-busy, target=_blank, download= (save dialog often keeps the page; no pageshow),
 * workflow forms (per-button spinner elsewhere).
 */
(function () {
  var overlay = document.getElementById("mf-manage-busy-overlay");
  if (!overlay) return;

  function inManageActionScope(node) {
    if (!node) return false;
    return !!(node.closest && (node.closest(".mf-manage-main") || node.closest("header.mf-manage-header")));
  }

  function showBusy() {
    overlay.removeAttribute("hidden");
    document.body.setAttribute("aria-busy", "true");
  }

  function hideBusy() {
    overlay.setAttribute("hidden", "");
    document.body.removeAttribute("aria-busy");
  }

  document.addEventListener(
    "submit",
    function (ev) {
      var form = ev.target;
      if (!form || form.nodeName !== "FORM") return;
      if (form.getAttribute("data-mf-no-busy") === "true") return;
      if (!inManageActionScope(form)) return;
      if (form.classList.contains("mf-workflow-decision")) return;
      showBusy();
    },
    true
  );

  document.addEventListener(
    "click",
    function (ev) {
      if (ev.defaultPrevented || ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.altKey || ev.button !== 0) {
        return;
      }
      var a = ev.target.closest && ev.target.closest("a[href]");
      if (!a) return;
      if (a.getAttribute("data-mf-no-busy") === "true") return;
      if (a.hasAttribute("download")) return;
      if (a.target === "_blank") return;
      var href = a.getAttribute("href") || "";
      if (!href || href === "#" || href.charAt(0) === "#" || href.indexOf("javascript:") === 0) {
        return;
      }
      if (!a.closest(".mf-manage-main")) return;

      var busy =
        a.classList.contains("mf-button") || a.classList.contains("mf-pagination__link");
      if (!busy) return;

      showBusy();
    },
    true
  );

  document.addEventListener(
    "change",
    function (ev) {
      var el = ev.target;
      if (!el || el.nodeName !== "SELECT") return;
      if (el.getAttribute("data-mf-submit-form-on-change") !== "true") return;
      var form = el.form;
      if (!form || !inManageActionScope(form)) return;
      if (typeof form.requestSubmit === "function") {
        form.requestSubmit();
      } else {
        showBusy();
        form.submit();
      }
    },
    true
  );

  window.addEventListener("pageshow", hideBusy);
})();
